# Design: Worker Trace Link Finds Nothing (Defect 20)

## Problem

Clicking "View Traces" on an active worker card navigates to
/proxy?trace_id=<run_id> but the filtered trace list is always empty.

## Architecture Overview

The trace link flow involves six components:

1. **Worker process** - creates a LangSmith RunTree with a UUID, writes
   "## LangSmith Trace: <uuid>" marker to the item file
2. **Supervisor** - reads the trace UUID from the item file at dispatch
   (_try_dispatch_one) and polls for late arrivals (_refresh_worker_run_ids)
3. **DashboardState** - holds WorkerInfo.run_id, serialized via snapshot()
4. **SSE stream** (/api/stream) - sends worker data including run_id to frontend
5. **Frontend** (dashboard.js) - renders trace link as /proxy?trace_id=<run_id>
6. **Proxy endpoint** - queries traces DB with (run_id = ? OR parent_run_id = ?)

## Prior Implementation

Task 1.1 was previously completed and verified at code level:
- _refresh_worker_run_ids() polls item files to capture LangSmith trace IDs
- list_runs() uses (run_id = ? OR parent_run_id = ?) for child trace visibility
- All 1313 tests pass

However, the validation noted: "Runtime trace link behavior cannot be verified
without a running server." The item is back as "Review Required."

## Remaining Risk Areas

1. **Timing gap**: The worker may not write the trace marker to the item file
   until after the supervisor has already polled. The refresh mechanism exists
   but may not poll frequently enough or may stop polling too early.

2. **ID mismatch**: If the trace marker is never written (e.g., worker crashes
   before creating the RunTree), run_id stays None and the link is hidden. But
   if the marker is written with a different format or the regex doesn't match,
   run_id stays None silently.

3. **Database timing**: Traces may not be persisted to SQLite until the
   LangSmith callback flushes. The proxy query may find no rows even with a
   correct run_id if the trace hasn't been flushed yet.

## Approach

Since the code-level implementation was verified as present, this review should:

1. Re-verify the existing implementation against all acceptance criteria in
   the work item, with particular attention to edge cases
2. Check that _refresh_worker_run_ids is called in the supervisor's main loop
   with sufficient frequency
3. Verify the regex pattern in read_trace_id_from_file handles all UUID formats
4. Confirm the proxy list_runs query actually returns results when given a
   valid trace_id that exists in the DB
5. Add or fix any unit tests that cover the trace link flow end-to-end

## Key Files

| File | Role |
|------|------|
| langgraph_pipeline/supervisor.py | Worker dispatch, _refresh_worker_run_ids |
| langgraph_pipeline/web/dashboard_state.py | WorkerInfo model, update_worker_run_id |
| langgraph_pipeline/shared/langsmith.py | read_trace_id_from_file, regex pattern |
| langgraph_pipeline/web/proxy.py | list_runs with trace_id filter |
| langgraph_pipeline/web/routes/proxy.py | /proxy endpoint handler |
| langgraph_pipeline/web/static/dashboard.js | Frontend trace link rendering |

## Design Decisions

- Single task with coder agent since this is a re-verification of existing code
- The validator will check test results and acceptance criteria automatically
- No new components needed; focus is on correctness of existing implementation
