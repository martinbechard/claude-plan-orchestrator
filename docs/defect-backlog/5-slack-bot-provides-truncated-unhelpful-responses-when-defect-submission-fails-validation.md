# Slack bot provides truncated, unhelpful responses when defect submission fails validation

## Status: Open

## Priority: Medium

## Summary

When defects are submitted via Slack, the bot must provide complete, untruncated responses that: (1) analyze whether the submission is truly a defect, (2) explain the classification decision, and (3) provide a clear reference to the created backlog item with its ID and title. The response should handle Slack's message length limits appropriately by summarizing or splitting messages if needed, ensuring users always receive actionable confirmation of their submission.

## 5 Whys Analysis

  1. **Why is the user frustrated?** Because the Slack bot's response was truncated ("when I terminante the auto-pipeline, I get some random hallucinated cost -this m") and didn't provide useful feedback about the defect submission.

**Root Need:** Users need reliable, complete confirmation when submitting defects through Slack that validates the submission, classifies it appropriately, and provides a clear reference to what was created.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771305584.251029.

## Verification Log

### Verification #1 - 2026-02-17 01:25

**Verdict: FAIL**

**Checks performed:**
- [x] Build passes (py_compile on auto-pipeline.py and plan-orchestrator.py)
- [ ] Unit tests pass (6 failures out of 167 tests)
- [x] _truncate_for_slack exists and handles message length limits
- [x] _run_intake_analysis provides comprehensive notifications with item reference
- [ ] Tests covering the defect's symptoms pass

**Findings:**

1. **Build (py_compile):** Both scripts/auto-pipeline.py and scripts/plan-orchestrator.py compile without syntax errors. PASS.

2. **Unit tests:** 161 passed, 6 failed. The 6 failures are all in tests/test_slack_notifier.py and are directly related to this defect's fix:

   - test_create_backlog_feature (line 1178): TypeError - test expects create_backlog_item to return a string (filepath), but it now returns a dict with keys filepath/filename/item_number. The assertion "os.path.exists(result)" fails because result is a dict, not a string.
   - test_create_backlog_defect (line 1242): Same signature mismatch - assertion "defect-backlog in result" fails on a dict.
   - test_create_backlog_numbering (line 1294): Same TypeError as above.
   - test_intake_analysis_clear_request (line 1879): Mock create_backlog_item returns a string "docs/feature-backlog/1-test.md" but _run_intake_analysis now accesses item_info['item_number'] and item_info['filename'] on the result, causing "string indices must be integers, not 'str'" TypeError. Intake falls to exception handler with status="failed".
   - test_intake_analysis_unstructured_response (line 1954): Same mock return type mismatch, same "string indices must be integers" error, intake.status == "failed" instead of "done".
   - test_intake_empty_response_creates_fallback (line 2066): Same mock return type mismatch causing the same error.

3. **Truncation handling (code review):** The _truncate_for_slack static method at line 2808 properly handles Slack Block Kit's 2900-char limit (SLACK_BLOCK_TEXT_MAX_LENGTH = 2900). Messages exceeding the limit are truncated with an omission indicator. This is called via _build_block_payload before every send_status call. PASS.

4. **Comprehensive notifications (code review):** _run_intake_analysis at line 3614 now builds notifications that include: item reference with number and filename (e.g., "#1 - filename.md"), classification, and root need. The fallback paths (empty LLM response, exception) also include item references. This addresses the original symptom of truncated, unhelpful responses. PASS (code logic).

5. **Root cause of test failures:** The create_backlog_item method was refactored to return a dict instead of a string, but the 6 test mocks still return strings. The tests need updating to match the new return type.

**Summary:** The production code correctly addresses the defect (truncation handling + comprehensive notifications with item references), but 6 unit tests are broken due to a return-type mismatch between the updated create_backlog_item (returns dict) and the test mocks (return string). The defect fix is incomplete until the tests are updated.

### Verification #2 - 2026-02-17 01:35

**Verdict: FAIL**

**Checks performed:**
- [x] Build passes (py_compile on auto-pipeline.py and plan-orchestrator.py)
- [ ] Unit tests pass (3 failures out of 167 tests)
- [x] _truncate_for_slack exists and handles message length limits
- [x] _run_intake_analysis provides comprehensive notifications with item reference
- [ ] Tests covering the defect's symptoms pass

**Findings:**

1. **Build (py_compile):** Both scripts/auto-pipeline.py and scripts/plan-orchestrator.py compile without syntax errors. PASS.

2. **Unit tests:** 164 passed, 3 failed (improved from 6 failures in Verification #1). The 3 remaining failures are all in tests/test_slack_notifier.py and are caused by mocks returning a string instead of the dict that _run_intake_analysis now expects:

   - test_intake_analysis_clear_request (line 1925): mock_create returns string "docs/feature-backlog/1-test.md" instead of dict. When _run_intake_analysis calls item_info['item_number'] on the string, it gets "string indices must be integers, not 'str'" TypeError, falls to exception handler, intake.status becomes "failed" instead of "done".
   - test_intake_analysis_unstructured_response (line 1975): Same mock return type mismatch. intake.status == "failed" instead of "done".
   - test_intake_empty_response_creates_fallback (line 2103): Same mock return type mismatch. intake.status == "failed" instead of "done".

   The 3 create_backlog_item direct-call tests that failed in Verification #1 have been fixed (commit d5fa592).

3. **Truncation handling:** The _truncate_for_slack static method at line 2808 properly truncates to SLACK_BLOCK_TEXT_MAX_LENGTH (2900 chars, line 95) with an omission indicator. It is called via _build_block_payload before every send_status call. PASS.

4. **Comprehensive notifications:** _run_intake_analysis (line 3614) builds notifications that include: item reference with number and filename (e.g., "#1 - filename.md"), classification, and root need. The fallback paths (empty LLM response at line 3637, exception handler at line 3694) also include item references. The original symptom of truncated, unhelpful responses is addressed in production code. PASS.

5. **Root cause of remaining failures:** The 3 _run_intake_analysis test mocks at lines 1890, 1951, and 2080 still return a string path instead of a dict with keys {filepath, filename, item_number}. This causes TypeError when the production code accesses item_info['item_number']. The mocks need to be updated to return e.g. {"filepath": "docs/feature-backlog/1-test.md", "filename": "1-test.md", "item_number": 1}.

**Summary:** Progress from Verification #1: 3 of the 6 broken tests have been fixed (the create_backlog_item direct-call tests). However, 3 _run_intake_analysis tests still fail because their mock_create functions return a string instead of the dict that the production code now expects. The production code itself correctly addresses the defect. The fix remains incomplete until these 3 test mocks are updated.

### Verification #3 - 2026-02-17 03:30

**Verdict: FAIL**

**Checks performed:**
- [x] Build passes (py_compile on auto-pipeline.py and plan-orchestrator.py)
- [ ] Unit tests pass (3 failures out of 167 tests)
- [x] _truncate_for_slack exists and handles message length limits
- [x] _run_intake_analysis provides comprehensive notifications with item reference
- [ ] Tests covering the defect's symptoms pass (3 intake analysis tests still fail)

**Findings:**

1. **Build (py_compile):** Both scripts/auto-pipeline.py and scripts/plan-orchestrator.py compile without syntax errors. PASS.

2. **Unit tests:** 164 passed, 3 failed. No change from Verification #2 - the same 3 intake analysis tests still fail with the same root cause (mock return type mismatch):

   - test_intake_analysis_clear_request (line 1888): mock_create returns string "docs/feature-backlog/1-test.md". _run_intake_analysis calls item_info['item_number'] on the string, causing TypeError "string indices must be integers, not 'str'". Intake falls to exception handler, status="failed" instead of "done".
   - test_intake_analysis_unstructured_response (line 1949): Same mock return type mismatch, same TypeError, status="failed" instead of "done".
   - test_intake_empty_response_creates_fallback (line 2078): Same issue. stdout: "[INTAKE] LLM returned empty response" then "[INTAKE] Error in intake analysis: string indices must be integers, not 'str'". Status "failed" instead of "done".

3. **Truncation handling:** _truncate_for_slack (line 2808) and SLACK_BLOCK_TEXT_MAX_LENGTH = 2900 (line 95) remain intact. Messages are truncated with omission indicator before Slack delivery. PASS.

4. **Comprehensive notifications:** _run_intake_analysis (lines 3637-3714) correctly builds notifications with item references (#{item_number} - filename), classification, and root need on all three code paths (normal success at 3686, empty LLM at 3647, exception fallback at 3705). Production code fully addresses the original symptom. PASS.

5. **No progress since Verification #2:** The 3 failing tests need their mock_create functions (at lines 1890, 1951, 2080 in test_slack_notifier.py) updated to return dicts like {"filepath": "docs/feature-backlog/1-test.md", "filename": "1-test.md", "item_number": 1} instead of plain strings.

**Summary:** No change from Verification #2. Production code correctly addresses the defect (truncation handling + comprehensive notifications with item references). The 3 remaining test failures are due to stale mock return types in test_slack_notifier.py. The fix is blocked on updating these 3 test mocks to return dicts matching the new create_backlog_item signature.
