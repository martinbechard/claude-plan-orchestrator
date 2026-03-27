# Tool Call Cost Attribution table has no attribution column

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

The "Tool Call Cost Attribution" section on the cost analysis page has a
table but it is missing the actual attribution column — the estimated cost
per tool call — which is the entire purpose of the section. Without it the
table just lists tool calls with no cost insight.

## Acceptance Criteria

- Does the Tool Call Cost Attribution table have a column showing the
  estimated cost per tool call in dollars? YES = pass, NO = fail
- Is the attribution calculated (e.g. proportional to result size relative
  to parent agent cost)? YES = pass, NO = fail
- Does the column header clearly say "Est. Cost" or similar?
  YES = pass, NO = fail
