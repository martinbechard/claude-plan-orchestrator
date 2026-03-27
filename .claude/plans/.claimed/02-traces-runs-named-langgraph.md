# Traces page: all runs named "LangGraph" with slug "LangGraph"

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not rewrite
from scratch — check what exists first.

## Summary

Every root trace in the LangSmith proxy is named "LangGraph" and the slug
column also shows "LangGraph". This makes the traces list completely
unreadable — there is no way to tell which run corresponds to which work item.

## Acceptance Criteria

- Do root traces in the DB have names that match the actual work item slug
  (not "LangGraph")? Run: SELECT DISTINCT name FROM traces WHERE
  parent_run_id IS NULL ORDER BY created_at DESC LIMIT 10;
  YES (slugs visible) = pass, NO (all say "LangGraph") = fail
- Does the /proxy traces list page show the item slug in the Name column
  instead of "LangGraph"? YES = pass, NO = fail
- Can I filter traces by slug name and get meaningful results?
  YES = pass, NO = fail

## LangSmith Trace: db1c58ba-9348-44a0-9e56-33fc51c3e1cd
