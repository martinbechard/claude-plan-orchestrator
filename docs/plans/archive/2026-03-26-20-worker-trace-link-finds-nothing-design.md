---
id: '20'
title: Dashboard "View Traces" link from active worker never finds any traces
type: defect-fix
---

# Design: Fix Worker Trace Link Finding Nothing

## Root Cause Analysis

Two independent bugs cause the trace list to always be empty:

### Bug 1 — race condition: run_id is None at dispatch for new items

`supervisor.py` reads the trace ID from the item file immediately after spawning the
worker process (`read_trace_id_from_file`, line 494). For items processed for the
first time, `langsmith.py` has not yet had a chance to write the `## LangSmith Trace:`
line to the file. The result: `run_id = None`, the dashboard hides the "View Traces"
link, and it stays hidden for the worker's entire lifetime because the supervisor never
re-reads the file.

### Bug 2 — root run not in DB while worker is running

`list_runs()` in `proxy.py` always applies `parent_run_id IS NULL`, selecting only
root-level runs. The root run (`RunTree`) is only posted to the proxy when `.end()` is
called (worker completes). While the worker is active, only child runs (LLM calls,
tool calls) exist in the DB; those have non-NULL `parent_run_id`, so the query returns
nothing even when the trace ID is correct.

The composed SQL while a worker runs:
```sql
SELECT * FROM traces
WHERE parent_run_id IS NULL       -- excludes all in-flight child runs
  AND run_id LIKE '{trace_id}%'   -- root run doesn't exist yet
```

## Fix Design

### Fix 1 — periodic run_id refresh in supervisor (`supervisor.py`)

Add a helper to `DashboardState` that lets the supervisor update a worker's `run_id`
after dispatch. In the existing `_poll_workers` loop, for any active worker whose
`WorkerInfo.run_id` is `None`, re-read the item file and call the update helper.
This closes the window once the subprocess writes the trace ID (typically within a
few seconds of start).

Files:
- `langgraph_pipeline/web/dashboard_state.py` — add `update_worker_run_id(pid, run_id)` method
- `langgraph_pipeline/supervisor.py` — call `update_worker_run_id` in `_poll_workers` for workers with no run_id

### Fix 2 — relax `parent_run_id IS NULL` when trace_id filter is provided (`proxy.py`)

When `trace_id` is given, the caller wants a specific trace. Include both the root run
(if already posted) and its child runs so the page is non-empty while the worker is
active:

```sql
WHERE (run_id = ? OR parent_run_id = ?)
```

This replaces the `run_id LIKE ?` + `parent_run_id IS NULL` combination when
`trace_id` is set. The wildcard prefix match is replaced with an exact match (a
trace_id is always a full UUID) plus a parent match, and the root-only constraint is
dropped for this specific filter case.

Files:
- `langgraph_pipeline/web/proxy.py` — modify `list_runs()`: when `trace_id` is provided, remove `parent_run_id IS NULL` from conditions and use `(run_id = ? OR parent_run_id = ?)` instead of `run_id LIKE ?`

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/web/proxy.py` | Fix `list_runs()` trace_id filter (Bug 2) |
| `langgraph_pipeline/web/dashboard_state.py` | Add `update_worker_run_id()` (Bug 1) |
| `langgraph_pipeline/supervisor.py` | Call update in poll loop (Bug 1) |
| `tests/langgraph/web/test_proxy.py` | Update/add tests for new list_runs behavior |
| `tests/langgraph/test_supervisor.py` | Tests for run_id refresh in poll loop |

## Out of Scope

- Defect 02 (root run named "LangGraph") — slug-based correlation is a separate fix
- Defect 06 (drill-down from dashboard) — separate feature
- In-progress traces arriving late (LangSmith batching) — separate concern
