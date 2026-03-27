# Design: Intake Analysis Silent Failure (Pipeline Node)

## Problem

The pipeline intake_analyze() node in intake.py silently swallows Claude CLI
failures. The _call_llm() wrapper was updated to return a 3-tuple
(text, cost, failure_reason), and _verify_defect_symptoms() handles it correctly.
However, three other callers still unpack only 2 values from the 3-tuple,
causing ValueError at runtime:

- _run_five_whys_analysis() line 405: output, cost = _call_llm(prompt)
- _validate_design() line 344: output, _cost = _call_llm(...)
- _has_acceptance_checklist() line 356: output, _cost = _call_llm(...)

Additionally, intake_analyze() never reports errors to the dashboard via
add_error(), and does not gate on quota before spawning Claude subprocesses.

## Architecture Overview

Single coordinated change in intake.py:

1. **Fix all _call_llm() callers** to unpack the 3-tuple (text, cost,
   failure_reason) and handle failure_reason before using the text output.
   Specifically: _run_five_whys_analysis(), _validate_design(),
   _has_acceptance_checklist().

2. **Prevent error strings from being appended** to backlog item files.
   _run_five_whys_analysis() must check failure_reason before returning
   raw_output that gets passed to _append_analysis_to_item().

3. **intake_analyze() adds error reporting** via add_error() when any
   analysis step fails, so the dashboard error stream receives the detail.

4. **Quota gate** in intake_analyze() checks probe_quota_available() before
   attempting Claude calls, returning quota_exhausted early.

5. **Tests** verify failure propagation, add_error() calls, quota gating,
   and that error strings are never appended as analysis.

## Key Files

| File | Change |
|------|--------|
| langgraph_pipeline/pipeline/nodes/intake.py | Fix 3-tuple unpacking in all _call_llm callers; add add_error() calls; add quota gate |
| tests/langgraph/pipeline/nodes/test_intake.py | Add/update tests for failure paths, add_error, quota gating |

## Design Decisions

- **Tuple return over exception** -- _call_llm is used in contexts where
  exceptions would be disruptive. The structured 3-tuple return is already
  in place; we just need all callers to use it correctly.

- **No retry logic** -- the pipeline orchestrator already handles retries at
  the task level. Adding retry in intake would create conflicting retry loops.

- **add_error() is best-effort** -- wrapped in try/except so dashboard
  unavailability does not break the pipeline node.

## Acceptance Criteria

- Does _call_llm() return a 3-tuple (text, cost, failure_reason)? YES = pass
- Do ALL callers of _call_llm() unpack and check failure_reason? YES = pass
- Does intake_analyze() call add_error() when Claude calls fail? YES = pass
- Does intake_analyze() check quota before calling Claude? YES = pass
- Are error messages prevented from being appended to backlog files? YES = pass
- Do tests cover failure propagation, add_error(), and quota gating? YES = pass
