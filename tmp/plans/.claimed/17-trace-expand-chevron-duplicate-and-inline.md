# Trace detail: expand chevron duplicates and subruns not shown inline

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

On the trace detail page, clicking the expand chevron on a run row has two
problems:

1. The chevron duplicates — the collapsed right-arrow and the expanded
   down-arrow appear side by side instead of one replacing the other.
2. The expanded content only shows a link to navigate to the subrun. It
   should instead inline the subrun details (name, duration, inputs/outputs,
   error) directly in the expanded area without requiring navigation.

## Observed Behavior

- Click chevron: two chevrons appear (▶ ▼) next to each other.
- Expanded content shows only a hyperlink to /proxy/{child_run_id}.
- User must click away to another page to see subrun details.

## Expected Behavior

- Single chevron toggles between ▶ (collapsed) and ▼ (expanded).
- Expanded area shows the subrun details inline:
  - Name, duration, start/end elapsed offset
  - Inputs/outputs JSON (collapsible)
  - Error message if present
  - Nested sub-subruns if any (recursive expand)
- No navigation away from the page required for basic inspection.

## Root Cause

The CSS for details/summary chevrons uses both a ::before pseudo-element
and the native HTML summary ::marker / disclosure widget. Both render,
producing the duplicate. The expanded content was implemented as a link
rather than an inline detail panel.

## Fix

1. Hide the native summary marker:
     summary { list-style: none; }
     summary::-webkit-details-marker { display: none; }
   Keep only the ::before pseudo-element for the chevron.

2. Replace the subrun link with inline content: fetch and render the
   child run's name, duration, inputs_json, outputs_json, error directly
   in the expanded panel. The data should be pre-loaded in the route
   (grandchildren_by_parent dict from defect 16) so no additional API
   call is needed.

## Dependencies

- Defect 16: tool calls / grandchildren not fetched (same data pipeline)




## 5 Whys Analysis

**Title:** Seamless nested trace inspection requires smooth expand controls and inline details

**Clarity:** 4

**5 Whys:**

1. Why does clicking the expand chevron not reveal the full subrun details? Because the UI has two problems: a duplicate chevron that creates visual confusion, and expanded content that shows only a navigation link instead of inline details.

2. Why would a user want to see subrun details inline instead of navigating to another page? Because they're actively investigating the parent trace and need to understand how the subrun relates to it — its inputs, outputs, duration, and any errors.

3. Why is understanding a subrun in the context of its parent trace important? Because subruns don't exist in isolation; their behavior and performance are meaningful only in relation to the parent run's execution flow and inputs.

4. Why does navigating away from the trace to view subrun details create friction? Because it breaks the developer's mental model of execution flow, requires scrolling back to where they were, and forces them to hold context in memory rather than seeing relationships visually.

5. Why is uninterrupted, context-preserving investigation the root need? Because efficient debugging depends on rapid iteration through traces without cognitive overhead — every context-switch costs time and increases error risk in diagnosis.

**Root Need:** Developers must explore nested call hierarchies efficiently without breaking their investigation flow or losing the relational context between parent and child executions.

**Summary:** Users need expand-in-place UI patterns that reveal nested trace details inline, preserving context and allowing rapid exploration of execution flow.

## LangSmith Trace: df140811-9dea-4ac3-9c11-8ad497fee366
