# Design: Test Validation JSON Saved and Displayed (99-test-val-v2)

## Summary

Add a test comment marker to paths.py and verify that the validation results
JSON is saved and displayed on the item page after task completion.

## Key Files

- **langgraph_pipeline/shared/paths.py** -- add comment marker "# val json test"

## Design Decisions

- Single-task plan: the work item is a simple comment addition used to exercise
  the end-to-end validation pipeline.
- The coder agent adds the comment; the orchestrator's built-in validator
  automatically verifies that validation results appear on the item page.


## Acceptance Criteria

- Does the item page show Validation Results with verdict after completion?
  YES = pass, NO = fail
