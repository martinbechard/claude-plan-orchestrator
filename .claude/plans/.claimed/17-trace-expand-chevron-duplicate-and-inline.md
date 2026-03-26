# Trace detail: expand chevron duplicates and subruns not shown inline

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

## LangSmith Trace: 64dbf153-ea7a-4945-be70-a1441b9fad3e
