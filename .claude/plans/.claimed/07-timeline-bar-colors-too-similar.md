# Timeline: bar colors for LLM, tool, and other runs are too similar

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

## LangSmith Trace: dd2de2fd-c5cb-4dcc-baef-3736eea85ed7
