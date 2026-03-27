# langgraph_pipeline/web/server.py
# Embedded FastAPI web server for the supervisor with health and dashboard endpoints.
# Design: docs/plans/2026-03-25-13-embedded-web-server-infrastructure-design.md

"""Optional embedded HTTP server that runs in a daemon thread alongside the supervisor.

Provides a health endpoint and a base route structure for future UI features.
Gracefully degrades with a logged warning when fastapi or uvicorn are not installed.
"""

import json
import logging
import re
import socket
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

WEB_SERVER_DEFAULT_PORT = 7070
WEB_SERVER_PORT_SCAN_MAX = 7170

_STATIC_DIR = Path(__file__).parent / "static"

# ─── Module State ─────────────────────────────────────────────────────────────

_server: Optional[object] = None  # uvicorn.Server instance when running
_server_thread: Optional[threading.Thread] = None
_start_time: float = 0.0
_active_port: Optional[int] = None  # set when server is running; read by configure_tracing()


# ─── Port Utilities ───────────────────────────────────────────────────────────


def find_free_port(start: int) -> int:
    """Scan from ``start`` to WEB_SERVER_PORT_SCAN_MAX for a free TCP port.

    Args:
        start: First port number to try.

    Returns:
        The first available port number.

    Raises:
        RuntimeError: If no free port is found in the scan range.
    """
    for port in range(start, WEB_SERVER_PORT_SCAN_MAX + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("", port))
            return port
        except OSError:
            continue
    raise RuntimeError(
        f"No free port found in range {start}–{WEB_SERVER_PORT_SCAN_MAX}"
    )


def write_port_to_config(port: int, config_path: Path) -> None:
    """Write ``web.port`` back to the YAML config file, preserving comments.

    If a ``web:`` section already exists, inserts or updates ``  port: N`` under it.
    If no ``web:`` section exists, appends the block at the end of the file.

    Args:
        port: The port number to write.
        config_path: Path to the orchestrator-config.yaml file.
    """
    if not config_path.exists():
        return

    text = config_path.read_text(encoding="utf-8")

    port_line = f"  port: {port}"

    # Check if a web: section exists
    web_section_match = re.search(r"^web\s*:", text, re.MULTILINE)
    if web_section_match:
        # Check if port: already exists inside the web: section
        port_in_web_match = re.search(
            r"^(web\s*:(?:[^\n]*\n)(?:[ \t]+[^\n]*\n)*)[ \t]+port\s*:[ \t]*\d+",
            text,
            re.MULTILINE,
        )
        if port_in_web_match:
            # Update the existing port: line
            text = re.sub(
                r"(^web\s*:(?:[^\n]*\n)(?:[ \t]+[^\n]*\n)*)[ \t]+port\s*:[ \t]*\d+",
                lambda m: m.group(1) + port_line,
                text,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            # Insert port: right after the web: line
            text = re.sub(
                r"(^web\s*:[^\n]*\n)",
                lambda m: m.group(1) + port_line + "\n",
                text,
                count=1,
                flags=re.MULTILINE,
            )
    else:
        # Append new web: block at end of file
        if not text.endswith("\n"):
            text += "\n"
        text += f"\nweb:\n{port_line}\n"

    config_path.write_text(text, encoding="utf-8")


# ─── App Factory ──────────────────────────────────────────────────────────────


def create_app(config: Optional[dict] = None):
    """Build and return the FastAPI application with all routes configured.

    When ``config`` contains a ``web.proxy.enabled: true`` key, the TracingProxy
    is initialised and the /proxy router is mounted.

    Args:
        config: Full orchestrator config dict (may be None when running without config).

    Raises:
        ImportError: If fastapi is not installed.
    """
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="Plan Orchestrator", docs_url=None, redoc_url=None)

    @app.get("/")
    def root():
        """Redirect root to the dashboard placeholder."""
        return RedirectResponse(url="/dashboard")

    @app.get("/health")
    def health():
        """Return server health and supervisor uptime."""
        uptime = time.monotonic() - _start_time if _start_time else 0.0
        return JSONResponse({"status": "ok", "supervisor": {"uptime_seconds": uptime}})

    from langgraph_pipeline.web.routes.analysis import router as analysis_router
    from langgraph_pipeline.web.routes.completions import router as completions_router
    from langgraph_pipeline.web.routes.cost import router as cost_router
    from langgraph_pipeline.web.routes.dashboard import router as dashboard_router
    from langgraph_pipeline.web.routes.item import router as item_router
    from langgraph_pipeline.web.routes.queue import router as queue_router

    app.include_router(dashboard_router)
    app.include_router(analysis_router)
    app.include_router(completions_router)
    app.include_router(cost_router)
    app.include_router(queue_router)
    app.include_router(item_router)

    _STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Always init the proxy — it captures traces locally whenever the web server
    # is running.  forward_to_langsmith defaults to False so no quota is consumed
    # unless the user explicitly opts in via web.proxy.forward_to_langsmith: true.
    proxy_config = (config or {}).get("web", {}).get("proxy", {})
    from langgraph_pipeline.web.proxy import init_proxy
    from langgraph_pipeline.web.routes.proxy import router as proxy_router

    init_proxy(proxy_config)
    app.include_router(proxy_router)
    logger.info("TracingProxy active (forward_to_langsmith=%s)", proxy_config.get("forward_to_langsmith", False))

    # LangSmith-compatible shim endpoints.
    # The SDK routes here when LANGCHAIN_ENDPOINT points at this server.
    # Newer SDK versions probe GET /info first, then use POST /runs/multipart
    # for batch ingestion. We implement all three to avoid dropped traces.
    from fastapi import Request

    @app.get("/info")
    async def langsmith_info():
        """Return server capability info so the LangSmith SDK uses multipart ingestion."""
        return JSONResponse({
            "version": "0.1.0",
            "batch_ingest_config": {
                "use_multipart_endpoint": True,
                "size_limit": 100,
                "size_limit_bytes": 20971520,
                "scale_up_nthreads_limit": 16,
                "scale_up_qsize_trigger": 1000,
                "scale_down_nempty_trigger": 4,
            },
        })

    @app.post("/runs/multipart")
    async def runs_multipart(request: Request):
        """Accept a LangSmith multipart batch and store each run via the proxy.

        The SDK (via requests_toolbelt MultipartEncoder) sends each run as multiple
        parts: 'post.<uuid>' for the base run info, plus optional 'post.<uuid>.inputs',
        'post.<uuid>.outputs', 'post.<uuid>.extra', etc.  We parse the raw body with
        Python's email module (more robust than FastAPI form parsing for this format)
        and merge sub-parts before storing each run.
        """
        from langgraph_pipeline.web.proxy import get_proxy
        import email as _email

        proxy = get_proxy()
        if proxy is None:
            return JSONResponse({}, status_code=202)
        try:
            content_type = request.headers.get("content-type", "")
            body = await request.body()
            logger.debug("runs_multipart: received %d bytes, content-type=%s", len(body), content_type)

            # Build a fake email message so the stdlib multipart parser handles it.
            msg = _email.message_from_bytes(
                b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body
            )

            # Collect all parts, grouped by run_id.
            # runs[run_id] = merged dict of all fields for that run.
            runs: dict[str, dict] = {}

            for part in msg.get_payload():
                if isinstance(part, str):
                    continue
                disp = part.get("Content-Disposition", "")
                name = None
                for item in disp.split(";"):
                    item = item.strip()
                    if item.lower().startswith("name="):
                        name = item[5:].strip('"').strip("'")
                        break
                if not name:
                    continue

                data = part.get_payload(decode=True)
                if not data:
                    continue
                try:
                    value = json.loads(data)
                except (json.JSONDecodeError, ValueError):
                    continue

                # Name formats: "post.<uuid>", "post.<uuid>.inputs", "patch.<uuid>", etc.
                tokens = name.split(".", 2)
                if len(tokens) < 2 or tokens[0] not in ("post", "patch"):
                    continue
                run_id = tokens[1]
                field = tokens[2] if len(tokens) > 2 else None

                if run_id not in runs:
                    runs[run_id] = {"_operation": tokens[0]}
                if field is None:
                    runs[run_id].update(value)
                else:
                    runs[run_id][field] = value

            logger.debug("runs_multipart: parsed %d run(s)", len(runs))
            for run_id, run_data in runs.items():
                try:
                    extra = run_data.get("extra") or {}
                    proxy.record_run(
                        run_id=run_id,
                        parent_run_id=run_data.get("parent_run_id"),
                        name=run_data.get("name", ""),
                        inputs=run_data.get("inputs"),
                        outputs=run_data.get("outputs"),
                        metadata=extra.get("metadata"),
                        error=run_data.get("error"),
                        start_time=run_data.get("start_time"),
                        end_time=run_data.get("end_time"),
                    )
                    inv = extra.get("invocation_params") or {}
                    meta = extra.get("metadata") or {}
                    model = (
                        inv.get("model") or inv.get("model_name") or
                        meta.get("ls_model_name") or meta.get("model") or ""
                    )
                    parent_run_id = run_data.get("parent_run_id")
                    if model and parent_run_id:
                        proxy.propagate_model_to_root(parent_run_id, model)
                except Exception as exc:
                    logger.debug("runs_multipart: failed to record run %s: %s", run_id, exc)
        except Exception as exc:
            logger.warning("runs_multipart: failed: %s", exc)
        return JSONResponse({}, status_code=202)

    @app.post("/runs")
    async def runs_create(request: Request):
        """Accept a LangSmith run-create payload and store it via the proxy."""
        from langgraph_pipeline.web.proxy import get_proxy
        proxy = get_proxy()
        if proxy is not None:
            try:
                body = await request.json()
                extra = body.get("extra") or {}
                proxy.record_run(
                    run_id=body.get("id", ""),
                    parent_run_id=body.get("parent_run_id"),
                    name=body.get("name", ""),
                    inputs=body.get("inputs"),
                    outputs=body.get("outputs"),
                    metadata=extra.get("metadata"),
                    error=body.get("error"),
                    start_time=body.get("start_time"),
                    end_time=body.get("end_time"),
                )
                inv = extra.get("invocation_params") or {}
                meta = extra.get("metadata") or {}
                model = (
                    inv.get("model") or inv.get("model_name") or
                    meta.get("ls_model_name") or meta.get("model") or ""
                )
                parent_run_id = body.get("parent_run_id")
                if model and parent_run_id:
                    proxy.propagate_model_to_root(parent_run_id, model)
            except Exception as exc:
                logger.debug("runs_create: failed to record run: %s", exc)
        return JSONResponse({}, status_code=200)

    @app.patch("/runs/{run_id}")
    async def runs_update(run_id: str, request: Request):
        """Accept a LangSmith run-update payload and update the stored run."""
        from langgraph_pipeline.web.proxy import get_proxy
        proxy = get_proxy()
        if proxy is not None:
            try:
                body = await request.json()
                proxy.record_run(
                    run_id=run_id,
                    parent_run_id=None,
                    name="",
                    inputs=None,
                    outputs=body.get("outputs"),
                    metadata=None,
                    error=body.get("error"),
                    start_time=None,
                    end_time=body.get("end_time"),
                )
            except Exception as exc:
                logger.debug("runs_update: failed to update run %s: %s", run_id, exc)
        return JSONResponse({}, status_code=200)

    @app.post("/api/worker-stats")
    async def worker_stats(request: Request):
        """Accept token/cost updates from a running worker and update DashboardState."""
        try:
            body = await request.json()
            pid = int(body.get("pid", 0))
            tokens_in = int(body.get("tokens_in", 0))
            tokens_out = int(body.get("tokens_out", 0))
            cost_usd = float(body.get("cost_usd", 0.0))
            if pid > 0:
                from langgraph_pipeline.web.dashboard_state import get_dashboard_state
                dashboard = get_dashboard_state()
                dashboard.update_worker_tokens(pid, tokens_in, tokens_out)
                with dashboard._lock:
                    worker = dashboard.active_workers.get(pid)
                    if worker is not None:
                        worker.estimated_cost_usd = cost_usd
                        worker.record_token_sample()
        except Exception as exc:
            logger.debug("worker_stats: %s", exc)
        return JSONResponse({"ok": True}, status_code=202)

    return app


# ─── Lifecycle ────────────────────────────────────────────────────────────────


def start_web_server(
    port: int = WEB_SERVER_DEFAULT_PORT,
    config: Optional[dict] = None,
    config_path: Optional[Path] = None,
) -> None:
    """Start uvicorn in a daemon thread on the given port.

    Args:
        port: TCP port to bind to.
        config: Full orchestrator config dict forwarded to create_app().
        config_path: Path to orchestrator-config.yaml; used for port write-back
            when the port was auto-discovered by find_free_port().

    Logs a warning and returns without raising if fastapi or uvicorn is not installed.
    """
    global _server, _server_thread, _start_time

    try:
        import uvicorn
    except ImportError:
        logger.warning(
            "Web server requested but uvicorn is not installed; "
            "install fastapi and uvicorn to enable the web interface"
        )
        return

    try:
        app = create_app(config)
    except ImportError:
        logger.warning(
            "Web server requested but fastapi is not installed; "
            "install fastapi and uvicorn to enable the web interface"
        )
        return

    global _active_port
    _active_port = port
    _start_time = time.monotonic()
    uvicorn_config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    _server = uvicorn.Server(uvicorn_config)

    def _run() -> None:
        _server.run()

    _server_thread = threading.Thread(target=_run, daemon=True, name="web-server")
    _server_thread.start()
    logger.info("Web server started on port=%d", port)


def get_active_port() -> Optional[int]:
    """Return the port the web server is listening on, or None if not running."""
    return _active_port


def stop_web_server() -> None:
    """Signal the uvicorn server to stop cleanly.

    Sets should_exit=True on the Server instance, which causes uvicorn to drain
    connections and exit. Safe to call even when the server was never started.
    """
    global _server, _active_port

    if _server is None:
        return

    _server.should_exit = True
    _server = None
    _active_port = None
    logger.info("Web server stop signalled")
