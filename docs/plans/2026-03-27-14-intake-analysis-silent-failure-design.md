# Design: Intake Analysis Silent Failure (Pipeline Node)

## Problem

The Slack intake handler (suspension.py) was already patched to surface
call_claude() failures via add_error() and Slack messages. However, the
pipeline intake_analyze() node in intake.py still silently swallows failures:

1. _call_llm() returns failure_reason as the "text" output on error (line 231).
   Callers like _run_five_whys_analysis() and _verify_defect_symptoms() treat
   error strings as valid analysis — writing "claude --print timed out after
   120s" into backlog items as if it were a 5 Whys analysis.

2. intake_analyze() never calls add_error() when analysis fails, so dashboard
   error stream gets nothing.

3. intake_analyze() does not gate on quota before calling Claude, wasting
   subprocess spawns when quota is exhausted.

## Architecture Overview

Single coordinated change in intake.py:

1. **_call_llm() returns a success/failure tuple** — change return type to
   include an explicit success flag so callers can distinguish valid text from
   error messages. Return (text, cost, failure_reason) instead of overloading
   the text field with errors.

2. **Callers handle failures** — _verify_defect_symptoms(),
   _run_five_whys_analysis(), and _has_five_whys() check the failure flag and
   propagate failure info instead of treating errors as analysis output.

3. **intake_analyze() adds error reporting** — call add_error() when analysis
   fails. Include the failure reason in log output.

4. **Quota gate** — check probe_quota_available() before attempting Claude calls
   in intake_analyze(), returning quota_exhausted early.

5. **Tests updated** — existing tests in test_intake.py (or new test file)
   verify failure propagation, add_error() calls, and quota gating.

## Key Files

| File | Change |
|------|--------|
| langgraph_pipeline/pipeline/nodes/intake.py | Fix _call_llm return type; add failure handling in callers; add add_error() calls; add quota gate |
| tests/langgraph/pipeline/nodes/test_intake.py | Add/update tests for failure paths, add_error, quota gating |

## Design Decisions

- **Tuple return over exception** — _call_llm is used in contexts where
  exceptions would be disruptive. A structured return keeps the interface simple.

- **No retry logic** — the pipeline orchestrator already handles retries at
  the task level. Adding retry in intake would create conflicting retry loops.

- **add_error() is best-effort** — wrapped in try/except so dashboard
  unavailability does not break the pipeline node.

## Acceptance Criteria

- Does _call_llm() distinguish success text from failure text? YES = pass
- Does intake_analyze() call add_error() when Claude calls fail? YES = pass
- Does intake_analyze() check quota before calling Claude? YES = pass
- Are error messages prevented from being appended to backlog files? YES = pass
- Do tests cover failure propagation and add_error() calls? YES = pass
