# Embedded Web Server Infrastructure — Design

Feature 13 | 2026-03-25

## Overview

Add an optional embedded HTTP server to the orchestrator supervisor. When
activated via `--web` CLI flag or `web.enabled: true` in
`orchestrator-config.yaml`, the supervisor starts a FastAPI + uvicorn server
in a daemon thread. The server provides a health endpoint and a base HTML
layout that later features (14 LangSmith proxy, 15 dashboard, 16 cost
analysis) can mount onto.

## Architecture

```
cli.py  ──parse --web / --web-port──►  supervisor.run_supervisor_loop()
                                              │
                                    web_enabled?  yes
                                              │
                              langgraph_pipeline/web/server.py
                              ┌───────────────────────────────┐
                              │ create_app()                  │
                              │   GET /          → redirect   │
                              │   GET /health    → JSON       │
                              │   /static        → files      │
                              │ start_web_server()            │
                              │   thread: uvicorn.run(app)    │
                              │ stop_web_server()             │
                              │   server.should_exit = True   │
                              └───────────────────────────────┘
```

## Key Files

| File | Action |
|------|--------|
| `langgraph_pipeline/web/__init__.py` | Create — package marker |
| `langgraph_pipeline/web/server.py` | Create — `create_app()`, `start_web_server()`, `stop_web_server()` |
| `langgraph_pipeline/web/templates/base.html` | Create — minimal Jinja2 shell with nav |
| `langgraph_pipeline/web/static/style.css` | Create — minimal CSS reset + nav styles |
| `langgraph_pipeline/cli.py` | Update — add `--web` and `--web-port` args; pass to `_run_scan_loop` → `run_supervisor_loop` |
| `langgraph_pipeline/supervisor.py` | Update — accept `web_enabled`/`web_port`; call `start_web_server` / `stop_web_server` around the dispatch loop |
| `.claude/orchestrator-config.yaml` | Update — add commented-out `web:` section |
| `tests/langgraph/web/test_server.py` | Create — unit tests for `create_app()` and `/health` endpoint |

## Design Decisions

**FastAPI + uvicorn** — already in the Python web ecosystem, async-friendly,
ships Jinja2 and static-file support. A graceful degradation path: if
`fastapi` or `uvicorn` are not installed the supervisor logs a warning and
continues normally.

**Daemon thread** — using `threading.Thread(daemon=True)` with
`uvicorn.Config(app)` and a `uvicorn.Server` instance. `Server.should_exit`
is set to `True` when `stop_web_server()` is called, which causes uvicorn to
drain connections and stop. The supervisor's `shutdown_event` triggers this
call.

**Configuration precedence** — CLI flags override config file values. The
`web` section in `orchestrator-config.yaml` is loaded by
`load_orchestrator_config()` and passed down to the supervisor.

**Default port** — 7070 (constant `WEB_SERVER_DEFAULT_PORT` in `server.py`).

**Endpoints**:
- `GET /` → `RedirectResponse("/dashboard")` (placeholder until feature 15)
- `GET /health` → `{"status": "ok", "supervisor": {"uptime_seconds": ...}}`
- Static files mounted at `/static` from `langgraph_pipeline/web/static/`

**Jinja2 templates** — mounted via `Jinja2Templates` from
`langgraph_pipeline/web/templates/`. The `base.html` shell blocks are
`title`, `content`, and `extra_head` so future features extend it cleanly.

**No frontend build step** — plain CSS only; no bundlers, no transpilation.

## Supervisor Integration Points

`run_supervisor_loop()` gains two optional keyword parameters:
- `web_enabled: bool = False`
- `web_port: int = WEB_SERVER_DEFAULT_PORT`

When `web_enabled` is True, `start_web_server(app, port)` is called before
the dispatch loop, and `stop_web_server()` is called in the `finally` block.

## Test Strategy

Unit tests use the FastAPI `TestClient` (ships with `httpx`) to test:
- `create_app()` returns a FastAPI instance
- `GET /health` returns 200 with `{"status": "ok"}`
- `GET /` returns a redirect to `/dashboard`
- Graceful degradation: when FastAPI is unavailable, `start_web_server()`
  returns without raising (mocked import failure)
