# Work item page shows "No requirements" even when backlog item has acceptance criteria

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

The /item/<slug> page shows "No requirements document found" when there is
no design doc in docs/plans/. But the backlog .md file itself contains the
requirements and acceptance criteria. The page should display the backlog
item content as the requirements source when no design doc exists.

## Current Behavior

The page looks for docs/plans/*-<slug>-design.md. If not found, it shows
an empty state. The actual backlog item (in defect-backlog/, feature-backlog/,
or .claimed/) is never read.

## Expected Behavior

Requirements section should search in this priority order:
1. Design doc (docs/plans/*-<slug>-design.md) — show as primary content.
   When a design doc is shown, also include a "Original request" link
   that expands or navigates to the original backlog .md file so the
   user can see the raw requirements that started this work.
2. Backlog item (.claimed/<slug>.md or docs/*/backlog/<slug>.md) — show
   the raw markdown content as requirements
3. Completed backlog (docs/completed-backlog/**/<slug>.md) — show if the
   item was already archived
4. Only show "No requirements" if none of these exist

## Acceptance Criteria

- Does /item/34-remove-tilde-cost-prefix-third-attempt show the acceptance
  criteria from the backlog .md file? YES = pass, NO = fail
- When a design doc exists, does it take priority over the backlog file?
  YES = pass, NO = fail
- When neither exists, does it show "No requirements document found"?
  YES = pass, NO = fail

## LangSmith Trace: 17d46cd5-dc67-43d5-a664-9856fd91cc50
