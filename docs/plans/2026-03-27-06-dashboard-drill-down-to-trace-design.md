# Design: Dashboard Drill Down from Active Workers / Recent Completions to Trace Page

## Status: Review Required

This feature was previously implemented. This plan validates the existing implementation
against the acceptance criteria and fixes any gaps.

## Architecture Overview

The drill-down feature connects three existing subsystems:

1. **Supervisor** (langgraph_pipeline/supervisor.py) - Dispatches workers, stores run_id
   in WorkerInfo and completions DB row
2. **Dashboard State** (langgraph_pipeline/web/dashboard_state.py) - WorkerInfo already
   has run_id field; SSE snapshot exposes it to the frontend
3. **Dashboard UI** (langgraph_pipeline/web/templates/dashboard.html) - Renders trace
   links in Active Workers cards and Recent Completions table rows

## Key Files

| File | Role |
|------|------|
| langgraph_pipeline/web/dashboard_state.py | WorkerInfo and CompletionRecord with run_id field |
| langgraph_pipeline/supervisor.py | Worker dispatch, run_id assignment, completion recording |
| langgraph_pipeline/web/templates/dashboard.html | UI rendering of trace links |
| langgraph_pipeline/web/proxy.py | Completions DB schema (run_id column), record_completion() |
| langgraph_pipeline/web/routes/dashboard.py | SSE /api/stream endpoint |
| langgraph_pipeline/web/routes/proxy.py | /proxy endpoint with trace_id filter |

## What Already Exists

- WorkerInfo.run_id: Optional[str] field
- CompletionRecord.run_id: Optional[str] field
- Completions table: run_id TEXT column
- Dashboard HTML: Trace column in completions table, trace link in worker cards
- /proxy?trace_id= filter support
- Supervisor refreshes run_ids for workers that start without one

## Validation Scope

1. Verify Active Workers rows render a clickable link to /proxy?trace_id=<run_id>
2. Verify Recent Completions rows render a clickable link to /proxy?trace_id=<run_id>
3. Verify run_id is populated when supervisor dispatches a worker
4. Verify run_id persists to completions DB when worker finishes
5. Verify links degrade gracefully when run_id is null (worker still starting)

## Design Decisions

- No new DB migrations needed - run_id column already exists
- No new API endpoints needed - SSE payload already includes run_id
- Focus is on validation and fixing any rendering or data-flow gaps
