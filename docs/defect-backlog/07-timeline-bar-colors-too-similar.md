# Timeline: bar colors for LLM, tool, and other runs are too similar

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


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




## 5 Whys Analysis

Title: Color palette in timeline trace visualization lacks sufficient visual differentiation for quick user comprehension

Clarity: 4

5 Whys:
1. Why are the bar colors hard to distinguish? - The current palette uses green (#16a34a) and blue (#2563eb), both saturated mid-tones that appear similar on small bars, plus slate grey (#64748b) which reads as inactive rather than a distinct category.

2. Why do these colors blend together visually? - Because they occupy similar brightness and saturation ranges in perceptual color space, and lack sufficient hue separation to remain distinguishable at small scales or for users with color vision differences (protanopia, deuteranopia, tritanopia).

3. Why is this a problem in a timeline interface? - Because users analyzing traces need to rapidly categorize and understand the distribution of LLM calls, tool calls, and other operations without looking away from the visual flow to consult the legend.

4. Why is rapid categorization critical during trace analysis? - Because debugging and performance optimization require users to quickly identify patterns (e.g., "too many sequential tool calls," "LLM blocked by tools"), cognitive load spikes when visual cues require interpretation, and this cognitive friction slows down the analysis workflow.

5. Why does this friction matter for the orchestrator's effectiveness? - Because the timeline is the primary visual interface for understanding execution flow—if users can't instantly recognize operation types, they lose the ability to quickly spot inefficiencies, bottlenecks, or unexpected execution patterns, reducing the orchestrator's value as a debugging and optimization tool.

Root Need: The timeline visualization must enable instant, effortless visual categorization of operation types regardless of bar size, viewing conditions, or color vision ability—so users can rapidly analyze execution patterns without cognitive overhead or legend lookup.

Summary: The underlying need is to remove friction from trace analysis by making operation categories visually self-evident at a glance.
