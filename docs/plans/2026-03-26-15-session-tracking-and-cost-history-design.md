# Design: Session Tracking and Cost History

## Overview

Add a `sessions` table to the SQLite DB to track pipeline runs as discrete sessions
with start/end times, cost, and item count. Expose session history and daily cost
totals in the dashboard. Sessions are created automatically on pipeline startup and
closed on shutdown.

## Architecture

### New DB Table (`proxy.py`)

```sql
CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    label        TEXT,
    start_time   TEXT NOT NULL,
    end_time     TEXT,
    total_cost_usd REAL NOT NULL DEFAULT 0.0,
    items_processed INTEGER NOT NULL DEFAULT 0,
    notes        TEXT
)
```

New proxy helpers:
- `create_session(label=None) -> int` — INSERT, return row id
- `close_session(session_id, total_cost_usd, items_processed)` — UPDATE end_time + stats
- `list_sessions(limit=50) -> list[dict]` — ORDER BY start_time DESC
- `list_daily_totals(limit=30) -> list[dict]` — GROUP BY date(finished_at) on completions

### Session Lifecycle (`cli.py`)

On startup (after web server starts): call `proxy.create_session()`, store `session_id`
in a module-level variable. Pass it to the supervisor or run loop as needed.

On shutdown (signal handler / finally block): call `proxy.close_session(session_id,
session_cost_usd, items_processed)` before web server stops.

The supervisor accumulates `total_cost_usd` and `items_processed` already; expose
these via `DashboardState` for the shutdown path to read.

### DashboardState Changes (`dashboard_state.py`)

- Add `session_start_time: datetime` field (actual datetime, not elapsed seconds)
- Add `session_id: int | None` field
- `snapshot()` includes `session_start_time_iso` (ISO 8601 string)
- Keep existing `session_elapsed_s` for backward compat with timeline

### New Sessions Route (`routes/sessions.py`)

- `GET /sessions` — HTML page: session history table + daily totals table
- `GET /api/sessions` — JSON: `{sessions: [...], daily_totals: [...]}`

Register in `server.py`.

### Dashboard Frontend Changes

- `dashboard.js` / `dashboard.html`: Show "Session Cost: $X.XX (started HH:MM AM)"
  next to the existing session cost stat box
- Add link "Session History" in the nav or stat bar pointing to `/sessions`

### Sessions History Page (`sessions.html`)

Two sections:
1. **Sessions** table: label, start, end, duration, cost, items processed
2. **Daily Totals** table: date, total cost, items count

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/web/proxy.py` | Add `sessions` table + 4 helpers |
| `langgraph_pipeline/cli.py` | Create session on startup, close on shutdown |
| `langgraph_pipeline/web/dashboard_state.py` | Add `session_start_time`, `session_id` |
| `langgraph_pipeline/web/routes/sessions.py` | New: GET /sessions, GET /api/sessions |
| `langgraph_pipeline/web/server.py` | Register sessions router |
| `langgraph_pipeline/web/templates/sessions.html` | New: history page |
| `langgraph_pipeline/web/templates/dashboard.html` | Add start time to session cost stat |
| `langgraph_pipeline/web/static/dashboard.js` | Render session start time from snapshot |

## Design Decisions

- **Session cost at shutdown**: read from `DashboardState.session_cost_usd` accumulated
  in-memory; do not re-query completions (avoids double-counting race).
- **No supervisor.py changes needed**: supervisor already feeds cost into DashboardState;
  cli.py reads it on shutdown.
- **Single active session**: only one session has `end_time IS NULL`; close any orphaned
  open sessions (end_time IS NULL) during `create_session()` to handle crash-recovery.
- **Daily totals are read-only queries**: computed from `completions` table, no new writes.
- **session_start_time in snapshot**: ISO string so JS can format with toLocaleTimeString().
