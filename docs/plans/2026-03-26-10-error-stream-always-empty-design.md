# Design: Error Stream Always Empty Fix

## Problem

The dashboard Error Stream panel never shows entries. `add_error()` is only
called in two narrow paths in `supervisor.py` (worker crash and explicit
failure). Warnings and exceptions from scan failures, agent dispatch errors,
and uncaught supervisor-loop exceptions never reach `DashboardState.recent_errors`.

## Solution

Add a custom `logging.Handler` subclass (`DashboardErrorHandler`) that calls
`get_dashboard_state().add_error(...)` for any log record at WARNING level or
above. Install this handler once at startup in `cli.py` after logging is
configured. The handler targets the `langgraph_pipeline` logger so it captures
all pipeline-internal warnings without picking up noise from third-party
libraries.

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/web/dashboard_state.py` | Add `DashboardErrorHandler` class |
| `langgraph_pipeline/cli.py` | Install the handler after `_configure_logging()` |
| `tests/langgraph/web/test_dashboard_state.py` | Unit tests for the handler |

## Design Decisions

- **Scope: `langgraph_pipeline` logger only** — installing on the root logger
  would forward third-party library warnings (uvicorn, httpx, etc.) to the
  dashboard, producing noise. Targeting the named package logger limits scope
  to pipeline code.

- **Handler in `dashboard_state.py`** — keeps the handler co-located with
  `DashboardState` and `add_error()`. No new file needed.

- **Install in `cli.py` after `_configure_logging()`** — the handler must be
  added after `basicConfig()` runs so the logger hierarchy is stable.
  The call is guarded: if `get_dashboard_state()` is unavailable (e.g.
  in tests that patch it), the handler is still safe because `add_error()`
  is idempotent.

- **No message deduplication** — `add_error()` already caps at
  `MAX_RECENT_ERRORS = 50`. Dedup would add complexity for limited benefit.

- **Format** — the handler emits `"[LEVEL] logger_name: message"` so the
  dashboard shows the originating logger, not just the message text.

## Handler Sketch

```python
class DashboardErrorHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = f"[{record.levelname}] {record.name}: {self.format(record)}"
            get_dashboard_state().add_error(msg)
        except Exception:
            self.handleError(record)
```

Installed in `cli.py`:

```python
from langgraph_pipeline.web.dashboard_state import DashboardErrorHandler
logging.getLogger("langgraph_pipeline").addHandler(DashboardErrorHandler())
```
