# Optional Step-by-Step Notifications

## Status: Open

## Priority: Medium

## Summary

Per-task Slack notifications (sent on each task success/failure during plan execution) are
too noisy for small plans. Make step-by-step notifications opt-in based on plan size, with
an automatic threshold and a manual override flag in the backlog item.

Historical analysis of 42 completed plans shows a median of 6 tasks per plan. Plans with
6 or fewer tasks should suppress per-task notifications by default, since the 15-minute
progress reporter (feature 18) and the final completion notification provide sufficient
visibility.

## Requirements

### Automatic threshold

- Plans with 6 or fewer tasks: suppress per-task notifications (only send final
  completion/failure notification)
- Plans with 7 or more tasks: send per-task notifications as they do today
- The threshold value (6) should be a named constant (e.g. STEP_NOTIFICATION_THRESHOLD)

### Manual override via backlog item

- A backlog item can include a field like "step_notifications: true" (or false) to
  explicitly enable or disable per-task notifications regardless of plan size
- If the field is absent, the automatic threshold applies
- This allows flagging high-priority or complex items for detailed tracking even if
  they happen to have few steps

### Failure notifications are always sent

- Per-task FAILURE notifications should always be sent regardless of the threshold or
  override setting -- failures always need immediate visibility

### What stays unchanged

- The final completion notification (sent to the type-specific channel: features, defects,
  reports) is always sent
- The 15-minute progress reporter (feature 18) is independent and always runs

## Analysis

Historical plan step counts (42 plans):

- 2-3 steps: 10 plans (24%)
- 4-5 steps: 10 plans (24%)
- 6 steps: 3 plans (7%)
- 7+ steps: 19 plans (45%)

A cutoff of 6 silences per-step notifications for approximately 55% of plans, covering
all small defect fixes and moderate features. The remaining 45% of plans (7+ steps) retain
per-step tracking.

## Files Affected

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Add threshold constant, check plan task count and override flag before sending per-task success notifications |
| scripts/auto-pipeline.py | Pass step_notifications override from backlog item metadata into plan YAML |
| docs/templates/ | Update backlog item templates to document the step_notifications field |

## Dependencies

- Feature 18 (periodic progress reporter) should ideally land first so there is an
  alternative visibility mechanism before silencing per-step notifications. However, this
  is a soft dependency -- the feature works standalone.

## Verification Log

### Task 1.1 - FAIL (2026-02-19 16:45)
  - Validator 'validator' failed to execute: No status file written by Claude

### Task 1.1 - FAIL (2026-02-19 16:47)
  - Validator 'validator' failed to execute: No status file written by Claude

### Task 2.1 - FAIL (2026-02-19 16:53)
  - Validator 'validator' failed to execute: No status file written by Claude

### Task 2.1 - FAIL (2026-02-19 16:55)
  - Validator 'validator' failed to execute: No status file written by Claude

### Task 3.1 - FAIL (2026-02-19 17:01)
  - Validator 'validator' failed to execute: No status file written by Claude
