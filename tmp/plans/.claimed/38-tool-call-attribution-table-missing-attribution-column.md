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

## LangSmith Trace: 1c56fccd-56af-4d16-b019-0de1fcaedfac


## 5 Whys Analysis

Title: Tool call cost visibility needed for agent cost optimization

Clarity: 4

5 Whys:

1. Why is the Tool Call Cost Attribution table missing the estimated cost per tool call column?
   - The table was implemented with structure and tool call identifiers, but the actual cost attribution logic that calculates per-call costs was not included in the implementation.

2. Why wasn't the cost attribution calculation included when building the table?
   - The developer built the data collection and table display but didn't implement the methodology for attributing a portion of total agent costs back to individual tool calls.

3. Why wasn't the cost attribution calculation methodology implemented during development?
   - The requirements and design didn't specify how to calculate attribution (e.g., proportional to response size, equal distribution, time-based), leaving it ambiguous how costs should be apportioned.

4. Why wasn't the attribution methodology clearly defined in the requirements?
   - Requirements focused on tracking tool call data and total costs but didn't articulate the specific formula or heuristic needed to break down costs to the tool call level.

5. Why do users need to see estimated costs broken down per tool call?
   - Users need to identify which specific tool calls are driving costs in their agent workflows so they can optimize expensive operations and make informed decisions about tool selection and agent design.

Root Need: Users need transparent, actionable cost attribution per tool call to optimize agent efficiency and make cost-aware tool selection decisions.

Summary: Missing cost attribution prevents users from understanding which tool calls drive costs, blocking cost optimization insights that the analysis page promises to provide.
