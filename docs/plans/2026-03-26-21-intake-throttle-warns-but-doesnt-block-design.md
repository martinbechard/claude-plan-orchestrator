# Design: Intake Throttle Blocking Wait

## Problem

`intake_analyze()` in `intake.py` calls `_check_throttle()` but only prints a warning
when the limit is reached — it then continues processing regardless. The throttle is
advisory only, not enforced.

Additionally, `MAX_INTAKES_PER_HOUR` limits (10 defect / 20 feature / 10 analysis) are
too low for legitimate burst sessions. A separate throttle system exists in `poller.py`
with its own constants (`MAX_DEFECTS_PER_HOUR = 20`, `MAX_FEATURES_PER_HOUR = 20`) that
are inconsistent with `intake.py`.

## Solution

### Shared shutdown event singleton

`intake_analyze()` is a LangGraph node receiving only `PipelineState` — it has no direct
access to the `threading.Event` created in `cli.py`. The fix introduces a module-level
singleton in `langgraph_pipeline/shared/shutdown.py`:

- `get_shutdown_event() -> threading.Event` — returns the shared event (creates a default
  if none has been registered, so tests work without wiring)
- `register_shutdown_event(event: threading.Event) -> None` — called by `cli.py` after
  creating its own shutdown event, so signal handlers and the throttle wait loop use the
  same object

`cli.py` calls `register_shutdown_event(shutdown_event)` immediately after
`shutdown_event = threading.Event()`.

### Blocking throttle wait in intake_analyze

When `_check_throttle(item_type)` returns True, `intake_analyze()` enters a wait loop
modelled on `_run_quota_probe_loop()` in `cli.py`:

```
log: "Throttle limit reached for {item_type} — pausing intake. Waiting for window to clear."
loop:
    shutdown_event.wait(THROTTLE_WAIT_INTERVAL_SECONDS)
    if shutdown_event.is_set():
        return {}
    if not _check_throttle(item_type):
        log: "Throttle cleared for {item_type} — resuming."
        break
```

`THROTTLE_WAIT_INTERVAL_SECONDS = 60` is a new constant in `intake.py`.

### Updated limits

`intake.py` `MAX_INTAKES_PER_HOUR` raised to 50 for all types:

```python
MAX_INTAKES_PER_HOUR: dict[str, int] = {
    "defect": 50,
    "feature": 50,
    "analysis": 50,
}
```

`poller.py` constants harmonised:

```python
MAX_DEFECTS_PER_HOUR = 50
MAX_FEATURES_PER_HOUR = 50
```

## Files Modified

| File | Change |
|------|--------|
| `langgraph_pipeline/shared/shutdown.py` | New — shared shutdown event singleton |
| `langgraph_pipeline/cli.py` | Call `register_shutdown_event()` after creating shutdown event |
| `langgraph_pipeline/pipeline/nodes/intake.py` | Update limits; add blocking wait loop |
| `langgraph_pipeline/slack/poller.py` | Update `MAX_DEFECTS_PER_HOUR` / `MAX_FEATURES_PER_HOUR` to 50 |
| `tests/langgraph/pipeline/nodes/test_intake.py` | Add tests for blocking behavior and updated limits |

## Design Decisions

- **Singleton over state threading**: `threading.Event` is not JSON-serialisable and
  cannot be stored in `PipelineState` for LangGraph checkpointing. A module-level
  singleton avoids serialisation issues while keeping the signal handler and wait loop on
  the same object.
- **Default event for tests**: `get_shutdown_event()` creates a new `threading.Event()`
  if none is registered, so existing unit tests need no changes beyond the new throttle
  blocking tests.
- **`return {}` on shutdown**: if the shutdown event is set while waiting, the node
  returns an empty dict (no state change) and the outer scan loop exits cleanly on its
  next iteration check.
- **Consistent limits across subsystems**: `poller.py` guards new Slack-sourced backlog
  creation; `intake.py` guards pipeline-internal processing. Both should use the same
  limit so operators have one number to reason about.
