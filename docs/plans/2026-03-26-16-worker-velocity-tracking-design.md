# Worker Velocity Tracking — Design

Work item: .claude/plans/.claimed/16-worker-velocity-tracking.md

## Overview

Track token throughput (tokens/minute) per active worker and visualise it in the
timeline as bar colour intensity, so slowdowns under high parallelism are visible
at a glance. Final velocity is also persisted to the completions table for
historical analysis.

## Architecture

### Data flow

```
traces DB  →  proxy.get_worker_token_counts(run_id)
                          ↓
supervisor._refresh_worker_token_counts()  (every 5 s poll)
                          ↓
DashboardState.update_worker_tokens(pid, tokens_in, tokens_out)
                          ↓
DashboardState.snapshot()  →  SSE /api/state  →  dashboard.js
                          ↓
renderTimeline() with velocity colour mode
```

### Token data source

Tokens are already written to the `traces` table as
`json_extract(metadata_json, '$.input_tokens')` and `$.output_tokens`.
The root trace for a worker run carries the aggregate counts.

A new `proxy.get_worker_token_counts(run_id)` method returns
`(tokens_in, tokens_out)` by summing across all traces that match the
worker's root `run_id` or have it as an ancestor:

```sql
WITH RECURSIVE subtree(run_id) AS (
    SELECT run_id FROM traces WHERE run_id = ?
    UNION ALL
    SELECT t.run_id FROM traces t JOIN subtree s ON t.parent_run_id = s.run_id
)
SELECT
    COALESCE(SUM(json_extract(t.metadata_json, '$.input_tokens')), 0),
    COALESCE(SUM(json_extract(t.metadata_json, '$.output_tokens')), 0)
FROM traces t JOIN subtree s ON t.run_id = s.run_id
```

### WorkerInfo extension

Add two fields to the `WorkerInfo` dataclass:

```python
tokens_in: int = 0
tokens_out: int = 0
```

Add `update_worker_tokens(pid, tokens_in, tokens_out)` to `DashboardState`
(same pattern as `update_worker_run_id`).

### SSE payload extension

In `DashboardState.snapshot()`, compute velocity inline and include it per
active worker:

```python
elapsed_min = max(elapsed_s / 60.0, 0.001)
tokens_per_minute = (w.tokens_in + w.tokens_out) / elapsed_min
```

New fields in each `active_workers` entry:
- `tokens_in` (int)
- `tokens_out` (int)
- `tokens_per_minute` (float, 0 if tokens are 0)

### Supervisor refresh

Add `_refresh_worker_token_counts(active_workers)` called each poll iteration
after `_refresh_worker_run_ids()`. It iterates workers with a known `run_id`
and calls `proxy.get_worker_token_counts(run_id)` to update the dashboard state.
Only workers with a non-None `run_id` are queried.

### Completions table migration

Add column `tokens_per_minute REAL NOT NULL DEFAULT 0.0` to the `completions`
table via `ALTER TABLE … ADD COLUMN` with an `OperationalError` guard (same
pattern as existing migrations in `_init_db`).

`record_completion` gains an optional `tokens_per_minute: float = 0.0`
parameter. `list_completions` and `list_completions_by_slug` include the new
column. The supervisor passes the final velocity when calling `record_completion`
after worker reap.

### Timeline colour mode (frontend)

New localStorage key: `"dashboard.timeline.colorMode"` with values `"type"` (default)
and `"velocity"`.

A toggle button is added to the timeline toolbar (after the existing nav buttons)
labelled "Velocity" / "Type".

In velocity mode, `buildTimelineRow` applies a CSS class based on
`tokens_per_minute`:

| Range              | Class                            |
|--------------------|----------------------------------|
| No data (0)        | `timeline-bar--vel-none`         |
| < 1000 tok/min     | `timeline-bar--vel-low`          |
| 1000–5000 tok/min  | `timeline-bar--vel-medium`       |
| > 5000 tok/min     | `timeline-bar--vel-high`         |

Completion bars in velocity mode use velocity stored in the completion record.

A `fmtVelocity(tpm)` helper formats the value: `"2.4k tok/min"` or `"—"` for zero.

The elapsed/velocity label in each timeline row shows e.g. `"3m 42s  2.4k tok/min"`.

## Key files

| File | Change |
|------|--------|
| `langgraph_pipeline/web/dashboard_state.py` | Add `tokens_in/out` to `WorkerInfo`; add `update_worker_tokens()`; extend `snapshot()` |
| `langgraph_pipeline/web/proxy.py` | Add `get_worker_token_counts()`; extend `record_completion()` and `list_completions*()`; DB migration for `completions.tokens_per_minute` |
| `langgraph_pipeline/supervisor.py` | Add `_refresh_worker_token_counts()`; pass velocity to `record_completion` on reap |
| `langgraph_pipeline/web/static/dashboard.js` | Color mode toggle; `fmtVelocity`; velocity label; `buildTimelineRow` velocity colours |
| `langgraph_pipeline/web/static/style.css` | Velocity colour classes |
| `langgraph_pipeline/web/templates/dashboard.html` | Color mode toggle button in timeline toolbar |

## Design decisions

- **Query approach**: Option (a) from the backlog — read traces DB on each poll
  cycle. Avoids any changes to the worker or its output files.
- **Velocity for completions**: Compute final velocity at reap time from the
  `WorkerInfo.tokens_in/out` already refreshed during the run. Store it in
  `completions.tokens_per_minute`.
- **No schema breaking change**: `ALTER TABLE … ADD COLUMN` with an
  `OperationalError` guard preserves existing databases.
- **No chart yet**: The "velocity vs active_worker_count" chart is deferred
  as the backlog item marks it "Eventually".
