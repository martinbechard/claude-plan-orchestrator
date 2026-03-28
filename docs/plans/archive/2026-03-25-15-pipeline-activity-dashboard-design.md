# Pipeline Activity Dashboard — Design

Feature 15 | 2026-03-25

## Overview

A live-updating dashboard at `/dashboard` showing the current pipeline state:
active workers, items being processed, queue, recent completions, running cost,
and an error stream. Uses Server-Sent Events (SSE) for live updates so the browser
receives state pushes without polling or WebSocket complexity.

Builds on the embedded web server added in Feature 13.

## Architecture

```
supervisor.py  ──feeds──►  DashboardState singleton (thread-safe)
                                    │
                          GET /api/stream (SSE)
                          sends JSON state snapshot every 2 s
                                    │
                          dashboard.html + dashboard.js
                          vanilla JS EventSource → DOM re-render
```

### Thread model

- `DashboardState` holds a `threading.Lock`. The supervisor loop (main thread)
  acquires the lock to mutate state; the SSE handler (uvicorn async event loop)
  acquires the lock to read a snapshot.
- The SSE endpoint runs as an async generator inside uvicorn; it `await asyncio.sleep(2)`
  between snapshots and terminates when the client disconnects.

## Key Files

| File | Action |
|------|--------|
| `langgraph_pipeline/web/dashboard_state.py` | Create — `DashboardState` dataclass + module-level singleton + helpers |
| `langgraph_pipeline/web/routes/dashboard.py` | Create — FastAPI router: `GET /dashboard` (HTML) + `GET /api/stream` (SSE) |
| `langgraph_pipeline/web/templates/dashboard.html` | Create — Jinja2 page extending `base.html`; `<template>` elements for stamping |
| `langgraph_pipeline/web/static/dashboard.js` | Create — `EventSource` consumer; `<template>` stamping for each panel |
| `langgraph_pipeline/web/server.py` | Update — import and mount `dashboard_router` unconditionally in `create_app()` |
| `langgraph_pipeline/supervisor.py` | Update — call DashboardState helpers at dispatch/reap/error sites |
| `tests/langgraph/web/test_dashboard_state.py` | Create — unit tests for DashboardState |

## DashboardState Design

```python
# langgraph_pipeline/web/dashboard_state.py

MAX_RECENT_COMPLETIONS = 20
MAX_RECENT_ERRORS = 50

@dataclass
class WorkerInfo:
    pid: int
    slug: str
    item_type: str   # "defect" | "feature" | "analysis"
    start_time: float  # time.monotonic()
    estimated_cost_usd: float

@dataclass
class CompletionRecord:
    slug: str
    item_type: str
    outcome: str   # "success" | "warn" | "fail"
    cost_usd: float
    duration_s: float
    finished_at: float  # time.time() for display

@dataclass
class DashboardState:
    _lock: threading.Lock
    active_workers: dict[int, WorkerInfo]    # keyed by PID
    recent_completions: list[CompletionRecord]  # newest first, capped at MAX_RECENT_COMPLETIONS
    session_cost_usd: float
    session_start: float      # time.monotonic()
    recent_errors: list[str]  # capped at MAX_RECENT_ERRORS

# Module-level singleton
_state: DashboardState = DashboardState(...)

def get_dashboard_state() -> DashboardState: ...
def reset_dashboard_state() -> None: ...  # test helper
```

Key methods on `DashboardState`:
- `add_active_worker(pid, slug, item_type, start_time)` — acquire lock, insert
- `remove_active_worker(pid, outcome, cost_usd, duration_s)` — acquire lock,
  pop from active, prepend to recent_completions (cap at MAX_RECENT_COMPLETIONS)
- `add_error(message)` — acquire lock, prepend, cap at MAX_RECENT_ERRORS
- `snapshot() -> dict` — acquire lock, return serialisable dict

The `snapshot()` dict shape fed to SSE:

```json
{
  "active_workers": [...],
  "recent_completions": [...],
  "queue_count": 3,
  "session_cost_usd": 1.2345,
  "session_elapsed_s": 3600,
  "active_count": 2,
  "total_processed": 17,
  "recent_errors": [...]
}
```

`queue_count` is computed inside `snapshot()` by calling `scan_backlog` (read-only,
no claim) or by counting `.md` files in BACKLOG_DIRS directly to avoid pulling the
full scan graph into the web layer.

## SSE Endpoint

```
GET /api/stream
Content-Type: text/event-stream

event: state
data: {"active_workers": [...], ...}

event: state
data: {...}
```

Implemented as a `StreamingResponse` wrapping an async generator that:
1. Sends the current snapshot immediately (so the browser has data on first connect).
2. Awaits `asyncio.sleep(SSE_INTERVAL_SECONDS)` (2 s).
3. Sends the next snapshot.
4. Exits when `request.is_disconnected()` returns True.

## Dashboard HTML/JS Design

`dashboard.html` extends `base.html` and contains four `<template>` elements:
- `#tpl-worker-card` — one card per active worker
- `#tpl-completion-row` — one row per recent completion
- `#tpl-error-row` — one row per recent error
- Session summary bar is rendered inline (no template needed)

`dashboard.js`:
- Opens `new EventSource('/api/stream')`
- On `state` event: calls `renderAll(data)` which stamps each template and
  replaces the relevant container's `innerHTML`
- No external libraries; no build step

## Supervisor Integration Points

`supervisor.py` imports `get_dashboard_state` from `langgraph_pipeline.web.dashboard_state`.

Callsites:
- `_try_dispatch_one()`: after successful `active_workers[pid] = ...`, call
  `get_dashboard_state().add_active_worker(pid, item_slug, item_type, time.monotonic())`
- `_reap_one_worker()`: after determining `outcome`, call
  `get_dashboard_state().remove_active_worker(pid, outcome, cost_usd, duration_s)`
- Error paths in `_reap_one_worker()`: call `get_dashboard_state().add_error(message)`
- `run_supervisor_loop()`: no change needed for start time — `DashboardState`
  records `session_start` at module initialisation time (reflects supervisor
  process start, close enough).

## Server Wiring

In `server.py`'s `create_app()`, unconditionally after the existing health endpoint:

```python
from langgraph_pipeline.web.routes.dashboard import router as dashboard_router
app.include_router(dashboard_router)
```

No config flag — the dashboard is always available when the web server runs.

## Design Decisions

**SSE over WebSocket** — one-way push only is needed; SSE requires zero extra
infrastructure and auto-reconnects. WebSocket would add bi-directional complexity
with no benefit.

**No queue scanning in supervisor.py** — `snapshot()` in `DashboardState` counts
the backlog directly (glob `*.md` over BACKLOG_DIRS). This avoids adding queue
state as yet another field that must be kept in sync.

**Unconditional router mount** — the root redirect already targets `/dashboard`.
Making the dashboard optional would require adding another config flag and a
conditional redirect; simpler to always mount it.

**Vanilla JS** — no build step, no bundler, in line with the no-build-step
constraint from the backlog item. `<template>` stamping keeps the JS minimal and
readable.

**Thread-safe singleton over dependency injection** — the supervisor is a plain
threaded loop, not an async coroutine. A module-level singleton with a lock is the
simplest pattern that works across the thread boundary without passing the state
object through every call site.
