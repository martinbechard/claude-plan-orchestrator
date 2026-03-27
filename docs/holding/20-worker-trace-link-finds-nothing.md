# Dashboard: "View Traces" link from active worker never finds any traces

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: High

## Summary

Clicking the trace link on an active worker card in the dashboard navigates
to /proxy?trace_id=<run_id> but the filtered trace list is always empty, even
when the worker has been running for a while and trace data exists in the DB.

## Likely Root Cause

Multiple possible causes to investigate:

1. The run_id stored in WorkerInfo may not match any run_id in the traces DB.
   The supervisor adds the worker to DashboardState with a PID-based or
   fabricated ID, while the LangGraph SDK generates its own UUIDs for trace
   runs. These are two independent ID spaces.

2. The trace_id filter on /proxy may not be implemented yet (depends on
   defect 05). If the filter parameter is ignored, the page shows the default
   unfiltered list which may not surface the correct trace.

3. Traces for a running worker may not be written to the DB until the worker
   completes. The LangSmith SDK may batch trace submissions or only POST
   the root run on completion, meaning no trace exists while the worker is
   still active.

4. The root run is named "LangGraph" (defect 02) and has no slug in its
   metadata, so even if the trace exists, there is no way to correlate it
   back to the worker's slug.

## Expected Behavior

Clicking the trace link on a running worker should show traces associated
with that worker, either by matching on run_id, thread_id, or item slug.

## Investigation Steps

1. Check what run_id value is stored in WorkerInfo and passed to the SSE
   payload — is it a real LangGraph run_id or a fabricated value?
2. Query the traces DB for any rows created around the time the worker
   started — do they exist? What is their run_id?
3. Check if the trace_id query parameter is actually wired up in the /proxy
   endpoint route and list_runs() method.

## Dependencies

- Defect 05: trace_id filter on /proxy endpoint
- Defect 02: root runs named "LangGraph" with no slug association
- Defect 06: drill-down from dashboard to traces
