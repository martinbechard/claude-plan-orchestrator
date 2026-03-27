# Timeline: bar colors for LLM, tool, and other runs are too similar

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Low

## Summary

The three bar color categories in the Gantt timeline (LLM calls, tool calls,
other) use shades that are hard to distinguish at a glance, especially for
users with color vision differences.

## Observed Behavior

- LLM: #16a34a (mid green)
- Tool: #2563eb (mid blue)
- Other: #64748b (slate grey)

The green and blue are both saturated mid-tones and blend together on small
bars. The grey reads as inactive/disabled rather than a distinct category.

## Expected Behavior

Colors should be immediately distinguishable without relying on the legend.
Suggested palette:

- LLM calls: #7c3aed (violet) — distinct, high contrast on white
- Tool calls: #0891b2 (cyan/teal) — clearly different from violet
- Other / chain: #f59e0b (amber) — warm, stands out from both cool tones

Text contrast colors should also be updated to match.

## Suggested Fix

Update the bar_color() and text_color() macros in proxy_trace.html to use
the new palette. Update the legend rect fills to match.

## LangSmith Trace: fc1fd8a2-4aad-462d-ac2c-94b8f449c7a8
