# Dashboard: drill down from active workers / recent completions to trace page

## Status: Open

## Priority: Medium

## Summary

The Active Workers and Recent Completions panels have no link to the trace
detail for that work item. Users need to click through from a worker or
completion directly to the Traces page, pre-filtered to that item's trace_id.

## Observed Behavior

- Active Workers rows show PID, slug, type, elapsed — no trace link.
- Recent Completions rows show slug, outcome, cost, duration — no trace link.

## Expected Behavior

- Each active worker row has a link (or button) that opens /proxy?trace_id=<run_id>
  filtered to that worker's root trace.
- Each recent completion row has the same link.
- If the trace does not exist yet (worker still running), the link goes to the
  filtered list which may be empty — that is acceptable.

## Suggested Fix

1. When the supervisor dispatches a worker, store the root run_id (or thread_id)
   alongside the WorkerInfo in DashboardState (and in the completions DB row).
2. Expose run_id in the /api/state SSE payload and in the completions API response.
3. In dashboard.html, render each worker/completion row with an anchor tag
   pointing to /proxy?trace_id=<run_id> (once item 05 adds that filter).
4. In the completions table schema, add a run_id column so historical
   completions can also link to their trace.

## Dependencies

Depends on defect-backlog/05 (trace_id filter on /proxy endpoint).

## LangSmith Trace: b09b6a79-2268-4716-9a14-11dfbecd19aa
