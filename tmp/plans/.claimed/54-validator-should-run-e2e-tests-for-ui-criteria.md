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
