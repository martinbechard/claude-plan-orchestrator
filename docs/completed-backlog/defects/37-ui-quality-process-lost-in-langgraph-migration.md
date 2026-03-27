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




## 5 Whys Analysis

Title: UI design quality process not enforced in LangGraph pipeline agents

Clarity: 4

5 Whys:

1. **Why was the UI design review process lost during the LangGraph migration?**
   - The old pipeline's design competition workflow (3 parallel designs → judging → implementation) was not codified into agent prompts or pipeline configuration, leaving it as an implicit manual step rather than an automated gate.

2. **Why wasn't this workflow codified into the new pipeline's agent logic?**
   - The migration focused on achieving functional completeness (agents working, items flowing through) and did not include an audit of quality processes from the old system that should be preserved as automation triggers.

3. **Why did migration prioritize functionality over preserving quality processes?**
   - The frontend-design skill existed but had no integration points in planner or coder agent prompts—it required explicit, manual triggering that fell out of the process when old procedural documentation wasn't ported over.

4. **Why was the frontend-design skill not integrated into the agent system prompts?**
   - There was no explicit requirement or acceptance criteria during migration to verify that all old quality gates were either (a) automated in the new agents or (b) consciously deprecated with justification.

5. **Why was there no quality-process audit during the LangGraph migration?**
   - The migration treated the old pipeline as a "legacy system to replace" rather than a "source of truth about what quality practices matter," so procedural knowledge about design review gates was lost rather than intentionally preserved or evolved.

Root Need: The LangGraph agents need explicit integration of quality gates (especially frontend-design skill invocation) in their prompts so that UI work items cannot bypass design review before implementation.

Summary: A manual, procedural quality step became invisible when migrated to automation-first agents without explicit prompting or orchestration logic.
