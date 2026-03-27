# Design: Intake Analysis Silent Failure (Defect #14)

## Status: Review Required

This defect was previously implemented and marked complete. The plan validates
the existing implementation against acceptance criteria and fixes any gaps.

## Architecture Overview

The intake analysis flow involves these layers:

1. **claude_cli.py** - call_claude() invokes Claude CLI subprocess and returns
   ClaudeResult(text, failure_reason, cost data, raw_stdout).
2. **suspension.py** - _run_intake_analysis_inner() orchestrates the intake:
   checks quota, calls Claude, parses response, creates backlog item.
3. **dashboard_state.py** - add_error() records errors to the dashboard error stream.
4. **Slack messages** - Failure reasons are included in user-facing Slack messages.

## Current Implementation State

Based on code inspection, all four fixes from the defect spec are already in place:

- **Fix 1 (call_claude error propagation):** ClaudeResult namedtuple returns
  failure_reason with full stderr on non-zero exit, timeout details, JSON decode
  errors, and OS errors. No truncation.
- **Fix 2 (dashboard error reporting):** add_error() called in both quota-exhausted
  and LLM-failure branches of _run_intake_analysis_inner().
- **Fix 3 (Slack failure reason):** Slack fallback messages include the failure reason
  in the format: "_(Analysis unavailable: {failure_reason} -- created from raw text)_"
- **Fix 4 (quota gating):** probe_quota callback checked before calling call_claude.

## Key Files

| File | Role |
|------|------|
| langgraph_pipeline/shared/claude_cli.py | ClaudeResult and call_claude |
| langgraph_pipeline/slack/suspension.py | Intake analysis orchestration |
| langgraph_pipeline/web/dashboard_state.py | Error stream |
| tests/ (relevant test files) | Unit tests for the above |

## Validation Focus

The task is to validate that:

1. All acceptance criteria from the defect spec are satisfied end-to-end
2. Error messages are not truncated at any boundary
3. Dashboard errors appear for all failure modes (quota, timeout, API error, JSON error)
4. Slack messages include actionable failure reasons
5. Tests cover the failure paths adequately

Fix any gaps discovered during validation.
