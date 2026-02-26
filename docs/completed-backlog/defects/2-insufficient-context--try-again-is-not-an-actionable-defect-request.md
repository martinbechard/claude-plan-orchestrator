# Insufficient context — "try again" is not an actionable defect request

## Status: Open

## Priority: Medium

## Summary

The request "try again" does not contain enough information to identify a defect, reproduce an issue, or take any corrective action. The requester should be asked to clarify: (1) what action was attempted, (2) what the expected result was, and (3) what actually happened. If this pattern recurs, consider adding input validation to the defect submission process to require minimum context fields.

## 5 Whys Analysis

  1. **Why did the user say "try again"?** — Because a previous action or attempt failed or produced an unsatisfactory result, and they want it repeated or retried.
  2. **Why did the previous attempt fail or produce an unsatisfactory result?** — Unknown — the request contains no reference to what was tried, what failed, or what the expected outcome was.
  3. **Why is there no context about what failed?** — Because the user likely assumed the recipient (human or AI) would have shared context from a prior interaction or conversation that is not available here.
  4. **Why is that prior context not available?** — Because this appears to be a new session or the request was submitted without linking to the original conversation, defect, or task where the failure occurred.
  5. **Why wasn't the request submitted with proper context or linked to the original issue?** — Because there is no enforced structure or validation requiring defect submissions to include a description of the problem, expected behavior, and steps to reproduce.

**Root Need:** The requester experienced a failure in a prior interaction and wants it resolved, but the request cannot be acted upon without knowing what was attempted, what went wrong, and what the expected outcome should be.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771992023.870439.

## Verification Log

### Task 1.1 - FAIL (2026-02-26 00:09)
  - Validator 'validator' failed to execute: No status file written by Claude

### Verification #1 - 2026-02-26 00:11

**Verdict: PASS**

**Checks performed:**
- [x] Build passes (Python compilation of auto-pipeline.py and plan-orchestrator.py succeeds)
- [x] Unit tests pass (pytest tests/ runs with no failures)
- [x] Vague messages like "try again" are now rejected by input validation

**Findings:**

1. **Python compilation**: Both scripts/auto-pipeline.py and scripts/plan-orchestrator.py compile without errors.

2. **Unit tests**: All tests in tests/ pass (pytest exits cleanly with no failures).

3. **Reported symptom — vague "try again" creating an unactionable defect**: The codebase now has **two validation gates** that prevent this:

   - **Minimum length gate** (plan-orchestrator.py:5594): Messages shorter than MINIMUM_INTAKE_MESSAGE_LENGTH (20 chars) are rejected immediately. "try again" is only 9 characters, so it would be caught here before even reaching the LLM. The system responds with INTAKE_CLARIFICATION_TEMPLATE asking for more detail.

   - **Clarity threshold gate** (plan-orchestrator.py:5119): Even if a message passes the length check, the LLM rates its clarity on a 1-5 scale. Messages scoring below INTAKE_CLARITY_THRESHOLD (3) trigger a clarification request instead of creating a backlog item. "try again" is explicitly cited as an example of a clarity-1 message in the prompt template (line 267).

   Both gates respond with the same INTAKE_CLARIFICATION_TEMPLATE that asks the user to provide more context (what action was attempted, what happened, what was expected).

   The defect's suggestion to "consider adding input validation to the defect submission process to require minimum context fields" has been fully implemented via these two complementary mechanisms.
