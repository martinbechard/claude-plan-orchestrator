# Design: Worker Trace Link Finds Nothing (Defect 20)

## Problem

Clicking "View Traces" on an active worker card navigates to
/proxy?trace_id=<run_id> but the filtered trace list is always empty.

## Architecture Overview

The trace link flow spans several components:

1. **Worker spawn** (supervisor.py) - reads run_id from item file via
   read_trace_id_from_file(), stores in DashboardState
2. **Refresh loop** (_refresh_worker_run_ids) - periodically re-reads
   item files for workers with run_id=None
3. **SSE stream** - dashboard_state.snapshot() includes run_id in
   active_workers payload
4. **Dashboard JS** (dashboard.js:272-278) - renders trace link as
   /proxy?trace_id=<run_id>
5. **Proxy endpoint** (proxy.py:144-210) - accepts trace_id param,
   calls proxy.list_runs(trace_id=trace_id)

## Status: Review Required

This defect was previously implemented. The fix involved:
- read_trace_id_from_file() in langsmith.py reads UUID from item file
- _refresh_worker_run_ids() polls for late-arriving trace IDs
- Proxy endpoint wired to filter by trace_id

The task is to verify the full chain works end-to-end and fix any
remaining gaps.

## Key Files

- langgraph_pipeline/supervisor.py - worker dispatch and refresh
- langgraph_pipeline/web/dashboard_state.py - WorkerInfo with run_id
- langgraph_pipeline/web/routes/proxy.py - trace_id filtering
- langgraph_pipeline/web/static/dashboard.js - trace link generation
- langgraph_pipeline/shared/langsmith.py - read_trace_id_from_file()

## Design Decisions

- Since the implementation already exists, the task focuses on
  verification and fixing any remaining issues
- The trace ID sharing mechanism uses the item file as the coordination
  point between worker and supervisor (LangSmith Trace: UUID marker)
- The refresh loop handles the timing gap where trace ID may not exist
  at dispatch time
