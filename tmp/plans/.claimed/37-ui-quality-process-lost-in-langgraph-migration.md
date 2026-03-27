# UI quality review process lost during LangGraph migration

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: High

## Summary

The old pipeline had a process where UI designs were reviewed with 3 options
generated in parallel and judged before implementation. This process appears
to have been lost during the LangGraph migration. The current web UI pages
(dashboard, cost analysis, traces, completions, queue, item detail) were
built without any design review, resulting in inconsistent and amateurish
styling across pages.

## Investigation Required

1. Check git history for the old UI design competition process. Look for
   references to "design competition", "3 designs", "judge", "Phase 0",
   or "ux-designer" in old commits and docs/narrative/.
2. Determine if the process was codified in agent prompts, plan templates,
   or pipeline configuration that did not get migrated.
3. Check if the frontend-design skill was supposed to be invoked during
   web UI work items and why it was not.

## Expected Behavior

All web UI work items should go through a design quality process:
- Use the frontend-design skill for any UI component work
- For significant UI pages, generate multiple design options and select
  the best one before implementing
- Apply consistent styling across all pages (spacing, padding, typography,
  colours, pagination, empty states)

## Specific UI Issues Across Pages

- Pagination: inconsistent styling, no left padding, hard to read text
- Empty states: different styles on different pages
- Table styling: inconsistent column alignment and spacing
- Card layouts: some pages use cards, others don't
- Cost displays: still have tildes in some places
- Navigation active state: looks cheap (defect 11)
- Timeline bar colours: grey when should show types (fixed CSS, but
  indicates no design review caught it)

## Acceptance Criteria

- Is there a documented UI design review process in the planner or coder
  agent prompts? YES = pass, NO = fail
- Does the planner agent invoke frontend-design skill for UI work items?
  YES = pass, NO = fail
- Is there a style guide or reference page that enforces consistency?
  YES = pass, NO = fail

## LangSmith Trace: 30975008-d151-4452-925c-8811f28228a5
