# Embedded web server infrastructure

## Status: Open

## Priority: High

## Summary

Add an optional embedded web server to the orchestrator supervisor. When
activated (via `--web` CLI flag or `web.enabled: true` in
orchestrator-config.yaml), the supervisor starts a lightweight HTTP server
on a configurable port (default 7070) in a background thread. The server
serves a base layout and a health/status JSON endpoint, and acts as the
mount point for all subsequent UI features.

## Motivation

Features 14 (LangSmith proxy), 15 (pipeline dashboard), and 16 (tool call
timing analysis) all require an HTTP server to exist. This item delivers the
shared infrastructure so those features can be developed independently.

## Requirements

1. **Framework**: FastAPI with uvicorn (async-friendly, already used in the
   Python ecosystem; lightweight enough for a dev tool). Falls back cleanly
   if not installed — the supervisor starts normally with a warning.

2. **Lifecycle**: started in a daemon thread inside `run_supervisor_loop()`
   when web is enabled. Shut down via uvicorn's programmatic shutdown when
   the supervisor's shutdown_event fires. Does not block the supervisor loop.

3. **Configuration**:
   - CLI: `--web` flag enables it; `--web-port PORT` overrides default.
   - Config file: `web.enabled: true`, `web.port: 7070`.
   - CLI takes precedence over config file.

4. **Base endpoints**:
   - `GET /` — redirects to `/dashboard` (placeholder until feature 15).
   - `GET /health` — returns `{"status": "ok", "supervisor": {...}}` JSON.
   - Static file serving from `langgraph_pipeline/web/static/`.

5. **Base layout**: a minimal HTML shell (`langgraph_pipeline/web/templates/base.html`)
   with a nav bar linking Dashboard, Proxy Traces, Cost Analysis. Rendered
   via Jinja2 (bundled with FastAPI). No frontend build step required.

## Files

- `langgraph_pipeline/web/__init__.py`
- `langgraph_pipeline/web/server.py` — `create_app()`, `start_web_server()`, `stop_web_server()`
- `langgraph_pipeline/web/templates/base.html`
- `langgraph_pipeline/web/static/style.css`
- Update `langgraph_pipeline/cli.py` — add `--web` / `--web-port` args, pass to supervisor
- Update `langgraph_pipeline/supervisor.py` — call `start_web_server()` when enabled
- Update `.claude/orchestrator-config.yaml` — document `web:` section (commented out by default)
- `tests/langgraph/web/test_server.py` — unit tests for app creation and health endpoint

## Out of Scope

Does not implement any dashboard or proxy logic — those are features 14–16.

## LangSmith Trace: cfcf9c64-a565-446a-aae9-90fc458d63b3
