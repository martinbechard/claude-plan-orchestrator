# Intake throttle warns but does not actually block processing

## Status: Open

## Priority: High

## RETURNED FROM COMPLETED — Only 1 of 3 Tasks Done

Previous attempt completed task 1.1 (shutdown event module) after 3 escalation
cycles ($1.74). Then Claude stopped responding (likely quota exhaustion). Runs
2-5 all had $0.00 cost — Claude returned empty every time. Pipeline archived
after 5 warn outcomes despite tasks 1.2 and 2.1 never attempted.

Tasks remaining:
- 1.2: Implement blocking throttle wait in intake.py and update limits to 50
- 2.1: Update poller.py MAX_DEFECTS_PER_HOUR and MAX_FEATURES_PER_HOUR to 50

## Summary

The intake_analyze throttle in intake.py prints a warning when the per-type
limit is reached but continues processing anyway. The throttle exists to
prevent runaway processes but is currently ineffective — it is advisory only.

Additionally the limit of 20 features/hour is too low for legitimate burst
work sessions.

## Current Behavior

_check_throttle() returns True when the limit is hit, intake_analyze() prints
a warning, then continues with processing as normal. The item is fully
processed regardless of the throttle state.

## Expected Behavior

1. Raise limits to 50 per hour for both features and defects.
2. When the throttle is triggered, the pipeline should wait (block) until
   the count drops below the limit before proceeding.
3. Use shutdown_event.wait() with a reasonable interval (e.g. 60 seconds)
   so the pipeline remains responsive to shutdown signals while waiting.
4. Log a clear message when entering the throttle wait and when resuming.

## Fix

In intake_analyze(), when _check_throttle() returns True:
- Enter a blocking loop: log that processing is paused due to throttle,
  then call shutdown_event.wait(60) in a loop, re-checking _check_throttle()
  each iteration until it returns False or shutdown is requested.

Update constants:
- MAX_INTAKES_PER_HOUR: defect=50, feature=50, analysis=50

Also update poller.py:
- MAX_DEFECTS_PER_HOUR = 50
- MAX_FEATURES_PER_HOUR = 50

## LangSmith Trace: e872c747-2a3d-4fed-b8b5-f41d437e4195
