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
`langgraph_pipeline/web/dashboard_state.py`. It forwards log records to
`get_dashboard_state().add_error(msg)`. The handler is installed in `cli.py`
on the `langgraph_pipeline` logger after `_configure_logging()`.

### Key Files

| File | Status |
|------|--------|
| `langgraph_pipeline/web/dashboard_state.py` | `DashboardErrorHandler` class exists |
| `langgraph_pipeline/cli.py` (line 808-809) | Handler installed on startup |
| `tests/langgraph/web/test_dashboard_state.py` | Unit tests exist |

## Known Gap

The handler has no explicit level filter (`setLevel(logging.WARNING)`). It
relies on the `langgraph_pipeline` logger's effective level to filter DEBUG/INFO
records. When `--verbose` is used the root logger is set to DEBUG, and since the
`langgraph_pipeline` logger inherits that level, DEBUG and INFO messages would
flow through to the error stream.

The handler should call `self.setLevel(logging.WARNING)` in its `__init__` so it
only forwards WARNING+ records regardless of the logger's level.

## Validation Task

1. Add `self.setLevel(logging.WARNING)` to `DashboardErrorHandler.__init__`
2. Verify existing tests pass
3. Confirm the handler filters DEBUG/INFO even when logger level is DEBUG
