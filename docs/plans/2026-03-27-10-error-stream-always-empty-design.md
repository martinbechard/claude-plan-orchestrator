# Design: Error Stream Always Empty (Validation)

## Status

Previously implemented. Requires validation that the fix works end-to-end.

## Problem

The dashboard Error Stream panel never showed entries because `add_error()` was
only called in two narrow supervisor paths (worker crash and explicit failure).
Warnings and exceptions from scan failures, agent dispatch errors, and uncaught
supervisor-loop exceptions never reached `DashboardState.recent_errors`.

## Existing Implementation

A `DashboardErrorHandler` (custom `logging.Handler` subclass) was added in
`langgraph_pipeline/web/dashboard_state.py`. It forwards WARNING+ log records to
`get_dashboard_state().add_error(msg)`. The handler is installed in `cli.py`
on the `langgraph_pipeline` logger after `_configure_logging()`.

### Data Flow

```
Pipeline code -> logger.warning/error
  -> DashboardErrorHandler.emit() [level >= WARNING]
    -> get_dashboard_state().add_error(formatted_msg)
      -> DashboardState.recent_errors (list, max 50, prepended)
        -> snapshot() includes recent_errors
          -> SSE /api/stream sends JSON every 2s
            -> dashboard.js renderErrors() updates DOM
```

### Key Files

| File | Role |
|------|------|
| `langgraph_pipeline/web/dashboard_state.py` | `DashboardErrorHandler` class + `add_error()` method |
| `langgraph_pipeline/cli.py` (lines 808-809) | Handler installed on startup |
| `langgraph_pipeline/supervisor.py` (lines 360, 418, 433) | Manual `add_error()` calls for worker failures |
| `langgraph_pipeline/web/routes/dashboard.py` | SSE endpoint includes `recent_errors` in snapshot |
| `langgraph_pipeline/web/static/dashboard.js` | `renderErrors()` renders error rows in UI |
| `tests/langgraph/web/test_dashboard_state.py` | Unit tests for handler and error capping |

## Design Decisions

1. **Handler-based approach**: Using a `logging.Handler` subclass captures all
   pipeline warnings/errors automatically without sprinkling `add_error()` calls
   throughout the codebase.

2. **Scoped to `langgraph_pipeline` logger**: Avoids noise from third-party
   libraries (httpx, uvicorn, etc.) that would clutter the error stream.

3. **Level filter on handler**: `self.setLevel(logging.WARNING)` ensures only
   WARNING+ records flow to the dashboard, even when `--verbose` sets the logger
   to DEBUG.

4. **Thread-safe**: `add_error()` acquires `DashboardState._lock` before mutating
   the list, safe for concurrent supervisor and SSE threads.

## Validation Plan

Single task: validate the existing implementation against acceptance criteria from
the work item. Fix any gaps found during validation.
