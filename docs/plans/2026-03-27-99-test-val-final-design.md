# Design: Fix validation results display on item page

## Problem

Validation results are not displaying on the item page despite the validator node
writing validation-*.json files to the worker-output directory. The root cause is
a missing `import json` in `langgraph_pipeline/web/routes/item.py`, which causes
`_load_validation_results()` to raise a `NameError` that is silently caught by the
caller.

## Root Cause Analysis

The `_load_validation_results` function at item.py:482 uses `json.loads()` but the
`json` module is never imported. When the function runs, it throws `NameError: name
'json' is not defined`, and because the template renders validation_results as an
empty list when the load fails, users see no validation section.

## Fix

### File: langgraph_pipeline/web/routes/item.py

Add `import json` to the imports section.

### File: langgraph_pipeline/shared/paths.py

Add the test marker comment `# val results test` as specified in the work item
acceptance criteria trigger.

## Verification

After the fix, the item page should:
- Show a "Validation Results" section when validation-*.json files exist
- Display the verdict (PASS/WARN/FAIL) and message for each result


## Acceptance Criteria

- After completion, does the item page show a Validation Results section?
  YES = pass, NO = fail
- Does it show the verdict (PASS/WARN/FAIL) and message?
  YES = pass, NO = fail
