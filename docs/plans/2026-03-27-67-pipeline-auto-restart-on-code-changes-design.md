# Design: Pipeline auto-restart on web code changes (defect 67)

## Problem

When a worker commits changes to files under langgraph_pipeline/web/, the running
uvicorn web server continues serving stale code. New routes return 404, causing
validator failures until the pipeline is manually restarted.

The CodeChangeMonitor already detects file changes via SHA-256 hashing and can
trigger a full process restart via os.execv(). But this is too coarse-grained:
it restarts everything, including active workers. The web server needs an
independent restart path.

## Current architecture

- CodeChangeMonitor (shared/hot_reload.py): polls all .py files under
  langgraph_pipeline/ every 10 seconds, sets restart_pending event on change
- Web server (web/server.py): uvicorn runs in a daemon thread, managed via
  module-level globals (_server, _server_thread, _active_port)
- Restart path: cli.py checks restart_pending between work items, calls
  _perform_restart() which does os.execv() (full process replacement)

## Solution

### 1. Web server hot-restart function

Add a restart_web_server() function to web/server.py that:
1. Calls stop_web_server() to gracefully drain the current uvicorn instance
2. Calls importlib.reload() on the app module to pick up new route definitions
3. Calls start_web_server() with the same port/config to start a fresh instance

### 2. Classify file changes in CodeChangeMonitor

Extend CodeChangeMonitor to classify detected changes:
- Web-only changes: files matching langgraph_pipeline/web/**/*.py
- Pipeline changes: everything else

When only web files changed:
- Call restart_web_server() instead of setting restart_pending
- Active workers are unaffected (they run in subprocesses or separate threads)

When pipeline files changed:
- Existing behavior: set restart_pending for full process restart (which also
  restarts the web server implicitly)

### 3. Validator 404 retry

Add retry-on-404 logic to the validator's curl/HTTP check step. When a health
or route check returns 404, wait briefly and retry once. This handles the
transient window during web server restart.

## Key files to modify

- langgraph_pipeline/shared/hot_reload.py -- classify changes, add web restart path
- langgraph_pipeline/web/server.py -- add restart_web_server() function
- Validator agent or verification logic -- add 404 retry

## Design decisions

- Surgical web-only restart avoids disrupting active workers. The web server
  thread is independent of worker subprocesses.
- importlib.reload() is needed because uvicorn caches the ASGI app object.
  Simply stopping and starting uvicorn with the same module path would still
  serve the cached app. Reloading the module forces Python to re-execute
  route registrations.
- Single retry on 404 (not infinite) to avoid masking real missing routes.
  The retry window should be short (2-3 seconds) since uvicorn starts fast.

## Acceptance criteria

- After a worker adds a new route and commits, the web server serves it
  without manual restart
- Active workers continue running during web server restart
- The validator retries once if it gets a 404 on a curl check
