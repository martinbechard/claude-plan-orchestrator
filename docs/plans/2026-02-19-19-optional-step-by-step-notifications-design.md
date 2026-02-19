# Design: Optional Step-by-Step Notifications

## Overview

Per-task Slack notifications during plan execution are too noisy for small plans.
This feature makes per-task success notifications opt-in based on plan size, with
an automatic threshold and a manual override field in the backlog item.

Failure notifications are always sent regardless of settings.

## Architecture

### Decision flow

```
plan loaded -> count total tasks across all sections
            -> read meta.step_notifications override (if present)
            -> determine should_send_step_notifications:
               1. If meta.step_notifications is explicitly true/false -> use it
               2. Else if total_tasks > STEP_NOTIFICATION_THRESHOLD -> true
               3. Else -> false
            -> gate success notifications; always send failure notifications
```

### Where the logic lives

| Component | File | Change |
|-----------|------|--------|
| Threshold constant | plan-orchestrator.py | STEP_NOTIFICATION_THRESHOLD = 6 near other constants |
| Task counting + override | plan-orchestrator.py | Helper function in run_orchestrator() after plan load |
| Gate success notifications | plan-orchestrator.py | Wrap lines 5311-5317 in conditional |
| Parse override from backlog MD | auto-pipeline.py | New parse function for step_notifications field |
| Inject override into plan meta | auto-pipeline.py | After plan creation, patch meta if override found |
| Unit tests | tests/test_auto_pipeline.py | Test parse + inject logic |
| Unit tests | tests/test_plan_orchestrator.py | Test threshold + gating logic |

### Notification gating detail

In run_orchestrator(), after loading the plan and computing task count:

```python
STEP_NOTIFICATION_THRESHOLD = 6

def should_send_step_notifications(plan: dict) -> bool:
    meta = plan.get("meta", {})
    override = meta.get("step_notifications")
    if override is not None:
        return bool(override)
    total_tasks = sum(
        len(section.get("tasks", []))
        for section in plan.get("sections", [])
    )
    return total_tasks > STEP_NOTIFICATION_THRESHOLD
```

The boolean result is computed once at plan load and passed/stored for the
execution loop. The task-success notification block (lines 5311-5317) is wrapped:

```python
if send_step_notifications:
    slack.send_status(...)
```

The task-failure notification block (lines 5156-5161) is NOT gated -- failures
always send.

### Backlog item override parsing

In auto-pipeline.py, a new function parses the backlog markdown for a
step_notifications field anywhere in the document:

```python
def parse_step_notifications_override(filepath: str) -> Optional[bool]:
    """Parse step_notifications: true/false from a backlog .md file."""
```

This looks for a line matching `step_notifications: true` or
`step_notifications: false` (case-insensitive). Returns None if not found.

After plan creation succeeds, if an override was found, inject it into the plan
YAML meta section before validation.

### Backlog item field

Backlog items can include anywhere in the file:

```
step_notifications: true
```

or

```
step_notifications: false
```

If absent, the automatic threshold applies.

## Files to create/modify

| File | Action |
|------|--------|
| scripts/plan-orchestrator.py | Add constant, helper, gate success notifications |
| scripts/auto-pipeline.py | Add parse function, inject override into plan meta |
| tests/test_plan_orchestrator.py | Add tests for threshold and gating logic |
| tests/test_auto_pipeline.py | Add tests for parse and inject logic |

## What stays unchanged

- Final completion notification (sent to type-specific channel)
- 15-minute progress reporter (feature 18)
- Section completion notifications (informational, low frequency)
- Task failure notifications (always sent)
