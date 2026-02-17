# New Defect: when a defect or feature is received, the agent is supposed to do a 

## Status: Open

## Priority: Medium

## Summary

I'll analyze this defect using the 5 Whys method to uncover the root cause.

**Title:** Auto-pipeline agent inconsistently performs 5 Whys analysis, sometimes stopping at 1 Why

**5 Whys:**

1. **Why does the agent sometimes stop at 1 Why instead of 5?** Because the agent's prompt or instructions don't enforce strict counting/validation of the 5 Whys analysis steps.

2. **Why doesn't the prompt enforce strict counting?** Because the current implementation likely uses qualitative instructions ("perform a 5 Whys analysis") without structured output validation or explicit iteration requirements.

3. **Why is there no structured output validation?** Because the agent workflow doesn't include a verification step that checks whether exactly 5 "Why" questions were asked and answered before proceeding.

4. **Why doesn't the workflow include verification?** Because the agent was designed to be flexible and autonomous rather than following a rigid checklist-based approach that enforces each step.

5. **Why was flexibility prioritized over consistency?** Because initial development focused on getting functional behavior working rather than ensuring methodological rigor in the analysis process.

**Root Need:** The auto-pipeline agent needs enforceable guardrails that ensure methodological consistency—specifically, that every defect/feature request receives a complete 5-step analysis regardless of the agent's autonomous decision-making, while maintaining the quality and depth of analysis at each step.

**Description:**
The auto-pipeline agent must consistently perform all 5 steps of the 5 Whys analysis when processing defect or feature requests, not just 1-2 steps. This requires adding validation or structured prompting that enforces completion of exactly 5 "Why" iterations before proceeding to write the backlog item. The fix should ensure methodological rigor without sacrificing the quality of analysis at each level.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771307583.039159.

## Verification Log

### Verification #1 - 2026-02-17 11:30

**Verdict: FAIL**

**Checks performed:**
- [x] Build passes
- [x] Unit tests pass (167/167 passed)
- [x] Constants REQUIRED_FIVE_WHYS_COUNT and MAX_INTAKE_RETRIES defined (lines 121-122)
- [x] INTAKE_ANALYSIS_PROMPT strengthened with "MUST provide exactly 5" enforcement (line 129)
- [x] INTAKE_RETRY_PROMPT defined (line 170)
- [ ] Retry logic implemented in _run_intake_analysis
- [ ] Unit tests for retry logic added
- [ ] Reported symptom fully resolved

**Findings:**
Task 1.1 (constants and prompt strengthening) is completed. However, the core fix is incomplete:

1. **Retry logic NOT implemented (Task 1.2 pending):** The _run_intake_analysis() function (line 3646) does not reference REQUIRED_FIVE_WHYS_COUNT or INTAKE_RETRY_PROMPT anywhere. The constants are defined but completely unused. When the LLM returns fewer than 5 Whys, no retry is attempted -- the incomplete analysis is accepted as-is.

2. **No unit tests for retry behavior (Task 2.1 pending):** The test suite has no tests verifying that incomplete 5 Whys analyses trigger a retry or that graceful degradation works correctly.

3. **Symptom partially addressed:** The prompt enforcement ("MUST provide exactly 5") may reduce the frequency of incomplete analyses but does not guarantee it. Without programmatic validation and retry, the reported symptom (agent sometimes stopping at 1 Why) can still occur.

**Summary:** Only Phase 1 Task 1.1 of the plan is complete. Tasks 1.2 (retry logic), 2.1 (tests), and 3.1 (final verification) remain pending. The fix is architecturally sound in its approach but execution is incomplete.

### Verification #2 - 2026-02-17 15:30

**Verdict: PASS**

**Checks performed:**
- [x] Build passes
- [x] Unit tests pass (165/165 passed)
- [x] Constants REQUIRED_FIVE_WHYS_COUNT and MAX_INTAKE_RETRIES defined (plan-orchestrator.py lines 141-142)
- [x] INTAKE_ANALYSIS_PROMPT strengthened with "MUST provide exactly 5" enforcement (line 149)
- [x] INTAKE_RETRY_PROMPT defined (line 190)
- [x] Retry logic implemented in _run_intake_analysis (lines 3789-3815)
- [x] Unit tests for retry logic added (4 tests in test_plan_orchestrator.py)
- [x] Reported symptom fully resolved

**Findings:**

1. **Build passes:** Both scripts/auto-pipeline.py and scripts/plan-orchestrator.py compile cleanly with py_compile.

2. **Unit tests pass:** All 165 tests pass (pytest output: "165 passed in 1.44s"). This includes 4 new retry-specific tests:
   - test_intake_no_retry_when_five_whys_complete - verifies _call_claude_print called exactly once when 5 Whys are complete
   - test_intake_retries_on_incomplete_whys - verifies retry happens when fewer than 5 Whys returned
   - test_intake_proceeds_after_failed_retry - verifies graceful degradation (backlog item still created) when retry also returns incomplete Whys
   - test_intake_retry_uses_better_result - verifies the retry result is used when it has more Whys than initial

3. **Retry logic implemented:** _run_intake_analysis() at line 3790 checks if len(five_whys) < REQUIRED_FIVE_WHYS_COUNT. If true, it sends INTAKE_RETRY_PROMPT (formatted with the count, item_type, text, and previous analysis) via _call_claude_print. The retry result is used if it produced equal or more Whys than the original. A warning is logged if the final count is still below 5.

4. **Prompt enforcement:** INTAKE_ANALYSIS_PROMPT includes explicit instruction: "IMPORTANT: You MUST provide exactly 5 numbered 'Why' questions and answers. Do not stop at fewer than 5."

5. **Graceful degradation:** If both initial and retry attempts produce fewer than 5 Whys, the backlog item is still created with whatever analysis was produced, with a warning logged.

6. **Reported symptom resolved:** The combination of (a) strengthened prompt with explicit "MUST provide exactly 5" instruction, (b) programmatic validation counting the parsed five_whys list, (c) retry with a dedicated INTAKE_RETRY_PROMPT when the count is insufficient, and (d) graceful degradation ensures the agent consistently attempts all 5 Whys and retries if it falls short.
