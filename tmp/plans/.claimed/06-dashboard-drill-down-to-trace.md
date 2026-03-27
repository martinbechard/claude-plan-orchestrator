# Dashboard: drill down from active workers / recent completions to trace page

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


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

## LangSmith Trace: 40801cd2-c6e4-453c-a634-3fbfc12bd5d1


## 5 Whys Analysis

**Title:** Operator visibility gap between operational metrics and execution traces

**Clarity:** 4

The request is well-structured with clear current/expected behaviors and a concrete implementation path. It could be slightly clearer on the user impact (why this matters operationally).

**5 Whys:**

1. Why do users lack the ability to drill down from dashboard panels to traces?
   - Because Active Workers and Recent Completions display operational summaries (PID, elapsed, outcome, cost) but don't include links to the execution traces that generated those metrics.

2. Why don't the panels include trace links?
   - Because the supervisor's WorkerInfo and completions database don't capture and expose the root run_id (or thread_id) that would map each operation back to its trace in LangSmith.

3. Why isn't run_id being captured during worker dispatch?
   - Because the supervisor was designed to track operational state (PID, status, resource usage) for worker lifecycle management, but trace context wasn't initially considered part of that responsibility.

4. Why was trace context omitted from the original supervisor design?
   - Because trace infrastructure (LangSmith integration, /proxy endpoint) was built as a separate feature phase; tracing wasn't a first-class requirement when worker tracking was architected.

5. Why is this gap becoming a priority now?
   - Because operators are hitting a "dead end" investigating issues: they see what's running and what failed on the dashboard, but can't drill into execution traces to understand *why* without manual trace ID lookup, creating friction in debugging workflows.

**Root Need:** Operators require seamless navigation from high-level operational status (active workers, recent outcomes) into detailed execution traces to close the observability loop and reduce time-to-diagnosis for issues.

**Summary:** The dashboard needs bidirectional traceability: from metrics to traces and vice versa, enabling operators to move fluidly between system state and execution context.
