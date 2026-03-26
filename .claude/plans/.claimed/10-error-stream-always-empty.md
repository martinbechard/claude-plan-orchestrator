# Dashboard: Error Stream panel is always empty

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

## LangSmith Trace: 7d9a9599-2103-4ee4-9785-7a2a903dc1c1
