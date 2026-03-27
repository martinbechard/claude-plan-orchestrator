# Dashboard Error Stream shows general info messages instead of actual errors

## Summary

The Error Stream panel in the dashboard shows INFO-level messages like
"Dispatched worker PID 12345" and "Supervisor starting: max_workers=4"
which are not errors. This makes the panel useless — users see a wall of
routine messages and ignore it, missing actual errors when they occur.

The Error Stream should ONLY show real errors and warnings that need
attention: worker crashes, validation failures, quota exhaustion, plan
creation failures, permission denials, and items stuck in retry loops.

## Root Cause

The DashboardErrorHandler (a Python logging handler) is configured to
forward WARNING+ level records to DashboardState.add_error(). But many
INFO-level messages are also being added somewhere, or the handler
threshold is too low.

## Acceptance Criteria

- Does the Error Stream show ONLY WARNING and ERROR level messages?
  YES = pass, NO = fail
- Are routine messages like "Dispatched worker", "Supervisor starting",
  "Worker started" excluded from the Error Stream?
  YES = pass, NO = fail
- Do actual errors (worker crash, plan creation failure, validation
  FAIL, permission denial) appear in the Error Stream?
  YES = pass, NO = fail
- Is the panel empty when nothing is wrong?
  YES = pass, NO = fail
