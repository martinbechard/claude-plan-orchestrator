# langgraph_pipeline/web/server.py
# Embedded FastAPI web server for the supervisor with health and dashboard endpoints.
# Design: docs/plans/2026-03-25-13-embedded-web-server-infrastructure-design.md

"""Optional embedded HTTP server that runs in a daemon thread alongside the supervisor.

Provides a health endpoint and a base route structure for future UI features.
Gracefully degrades with a logged warning when fastapi or uvicorn are not installed.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

WEB_SERVER_DEFAULT_PORT = 7070

_STATIC_DIR = Path(__file__).parent / "static"

# ─── Module State ─────────────────────────────────────────────────────────────

_server: Optional[object] = None  # uvicorn.Server instance when running
_server_thread: Optional[threading.Thread] = None
_start_time: float = 0.0


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

    from langgraph_pipeline.web.routes.dashboard import router as dashboard_router

    app.include_router(dashboard_router)

    _STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    proxy_config = (config or {}).get("web", {}).get("proxy", {})
    if proxy_config.get("enabled"):
        from langgraph_pipeline.web.proxy import init_proxy
        from langgraph_pipeline.web.routes.proxy import router as proxy_router

        init_proxy(proxy_config)
        app.include_router(proxy_router)
        logger.info("Proxy router mounted at /proxy")

    return app


# ─── Lifecycle ────────────────────────────────────────────────────────────────


def start_web_server(
    port: int = WEB_SERVER_DEFAULT_PORT,
    config: Optional[dict] = None,
) -> None:
    """Start uvicorn in a daemon thread on the given port.

    Args:
        port: TCP port to bind to.
        config: Full orchestrator config dict forwarded to create_app().

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

    _start_time = time.monotonic()
    uvicorn_config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    _server = uvicorn.Server(uvicorn_config)

    def _run() -> None:
        _server.run()

    _server_thread = threading.Thread(target=_run, daemon=True, name="web-server")
    _server_thread.start()
    logger.info("Web server started on port=%d", port)


def stop_web_server() -> None:
    """Signal the uvicorn server to stop cleanly.

    Sets should_exit=True on the Server instance, which causes uvicorn to drain
    connections and exit. Safe to call even when the server was never started.
    """
    global _server

    if _server is None:
        return

    _server.should_exit = True
    _server = None
    logger.info("Web server stop signalled")
