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




## 5 Whys Analysis

Title: Work item page should display backlog item requirements when design doc doesn't exist
Clarity: 4
5 Whys:
1. **Why does the page show "No requirements" when the backlog file exists?** Because the implementation hardcodes a single source (design docs in docs/plans/) and has no fallback logic to check the originating backlog files where requirements actually live.

2. **Why was only the design doc path implemented, with no fallback?** Because the original mental model treated design documents as the authoritative requirements source, viewing backlog files as upstream inputs rather than displayable requirements.

3. **Why is there a gap between where requirements originate and where the page looks for them?** Because the workflow assumes linear progression (backlog → design doc → display), but users navigate to items before design docs are created, especially for smaller defects or quick fixes that don't warrant separate design documentation.

4. **Why do work items need to be viewable before formal design docs are created?** Because the workflow is iterative and non-linear in practice—items are triaged, prioritized, and assigned before design specs are written. Users need visibility into acceptance criteria and requirements *during* that earlier phase.

5. **Why is this now a pain point requiring a fix?** Because the current "No requirements" state creates friction: users see empty pages for work they could start on immediately, forcing them to switch contexts to the backlog to understand what's actually needed.

Root Need: Users need a single authoritative place (/item/<slug>) to see all requirements and acceptance criteria for a work item, in whatever form those requirements exist (design doc or backlog file), so they can understand scope and begin work without context switching.

Summary: The page should display requirements from whatever source exists (prioritizing design docs when available) rather than failing silently when a formal design doc hasn't been created.
