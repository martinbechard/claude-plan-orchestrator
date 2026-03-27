# Validator should create and run e2e tests for UI acceptance criteria

## Summary

The validator consistently reports "cannot verify at validation time —
requires runtime confirmation" for any acceptance criterion that involves
the web UI (e.g. "does the page show X", "does the filter work"). Instead
of giving up, the validator should:

1. Start the web server if not already running
2. Create a Playwright test that checks the UI criterion
3. Run the test
4. Report PASS/FAIL based on the test result

This requires:
- A Playwright test creation agent (e2e-test-agent) that can write
  targeted tests for specific acceptance criteria
- The validator to detect UI criteria and delegate to the e2e agent
- Playwright installed and configured in the project

## What We Have

- The web server runs on port 7070 during pipeline execution
- The planner references an "e2e-test-agent" but it doesn't exist
- The e2e-analyzer agent exists but only analyzes results, doesn't create tests
- No Playwright tests exist yet for the pipeline dashboard

## Acceptance Criteria

- Does an e2e-test-agent exist that can create Playwright tests?
  YES = pass, NO = fail
- When the validator encounters a UI criterion, does it create and run
  an e2e test instead of reporting "cannot verify"?
  YES = pass, NO = fail
- Does the e2e test actually navigate to the page and check the criterion?
  YES = pass, NO = fail
- Are test results included in the validation findings?
  YES = pass, NO = fail

## LangSmith Trace: 7174e3f6-200c-467d-b2c1-f21d627bb549


## 5 Whys Analysis

**Title:** Validator needs e2e testing capability for UI acceptance criteria

**Clarity:** 4/5  
Clear on *what* (create Playwright tests), *where* (validator), and *acceptance criteria*, but could better explain *why* runtime UI validation is critical to the pipeline's purpose.

**5 Whys:**

1. **Why does the validator report "cannot verify" for UI criteria?**
   - Because the validator only performs static analysis (code inspection, spec comparison) without running the application to test actual user-visible behavior.

2. **Why was the validator designed to only perform static analysis?**
   - Because it was built as a "dry run" validator to verify code and specs align without needing runtime execution—simpler, faster, and no infrastructure dependencies.

3. **Why is static-only validation now insufficient?**
   - Because the planner generates acceptance criteria based on user-visible behavior ("does the page show X", "does the filter work"), which can only be verified by actually running the application and testing the UI.

4. **Why does the planner create user-centric acceptance criteria instead of code-level criteria?**
   - Because user-visible behavior is the most meaningful validation target—a feature could pass code review and spec alignment but still be broken or missing at runtime where users actually interact with it.

5. **Why must the pipeline automatically verify runtime behavior instead of relying on manual testing?**
   - Because the orchestrator runs unattended and makes automated go/no-go decisions about feature completion; without runtime verification, static "PASS" verdicts become unreliable and the pipeline loses its value as an autonomous validation system.

**Root Need:** The automated pipeline must validate user-centric acceptance criteria through runtime testing, not just static analysis, to ensure "PASS" verdicts reflect actual feature functionality and maintain pipeline credibility.

**Summary:** Static validation is insufficient for a fully automated pipeline that must verify user-visible acceptance criteria—runtime testing is essential to close the gap.
