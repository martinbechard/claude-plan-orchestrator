# Dashboard: Error Stream panel is always empty

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

The Error Stream panel in the dashboard never displays any entries, even when
the pipeline encounters errors.

## Observed Behavior

The panel is always empty and the error count badge never appears.

## Root Cause (suspected)

add_error() is called in supervisor.py only on worker crash (exit code) and on
explicit failure detection — lines 317 and 357. These are rare paths. More
common errors (e.g. scan failures, uncaught exceptions in the supervisor loop,
agent dispatch errors) do not call add_error() and are only logged to the
Python logger, never surfaced to the dashboard.

Additionally, the SSE snapshot correctly includes recent_errors from
DashboardState, and dashboard.js renderErrors() looks correct. So the pipeline
is not emitting errors to the state, rather than the UI failing to render them.

## Expected Behavior

Any exception or error logged by the supervisor at WARNING level or above
should appear in the Error Stream in real time.

## Suggested Fix

Add a logging handler (e.g. a custom logging.Handler subclass) that calls
get_dashboard_state().add_error(record.getMessage()) for records at WARNING+
level. Install this handler on the root logger or the langgraph_pipeline
logger in server.py or cli.py at startup. This ensures all supervisor
warnings/errors flow to the dashboard without manually sprinkling add_error()
calls everywhere.




## 5 Whys Analysis

Title: Error Stream panel remains empty because comprehensive error logging isn't connected to dashboard state

Clarity: 4

5 Whys:

1. **Why is the Error Stream panel always empty?**
   Because add_error() is only called in two specific code paths (worker crash at line 317 and explicit failure detection at line 357), but many errors that occur during normal operation—such as scan failures, uncaught exceptions in the supervisor loop, and agent dispatch errors—only get logged to the Python logger, never reaching the dashboard's DashboardState.

2. **Why aren't all errors triggering add_error()?**
   Because the error-surfacing mechanism was built by manually sprinkling add_error() calls at specific exception points, rather than using a centralized, automatic mechanism that captures all errors and warnings.

3. **Why was a manual, point-solution approach chosen instead of a centralized one?**
   Because the original implementation treated error handling as isolated concerns—specific failures that needed special handling—rather than as a cross-cutting system concern that spans the entire supervisor loop and worker lifecycle.

4. **Why wasn't error visibility designed as a system concern from the start?**
   Because the implementation focused on preventing failures (via try-catch and exit codes) rather than on *observability*—the user's ability to see what's happening inside the black box in real time.

5. **Why do users need to see errors in real time?**
   Because without end-to-end visibility into warnings, failures, and exceptions as they happen, users can't diagnose why runs behave unexpectedly, can't understand system health, and lose trust that they can rely on the pipeline.

**Root Need:** Users need comprehensive, real-time visibility into all errors and warnings occurring anywhere in the pipeline system so they can diagnose failures, understand system behavior, and maintain confidence in reliability.

**Summary:** The dashboard error stream was designed for catastrophic failures, not operational visibility—creating a false sense that the system is healthy when problems are silently accumulating in logs.

## LangSmith Trace: eadb0b1e-b1ff-4452-8dca-7e356ad8d335
