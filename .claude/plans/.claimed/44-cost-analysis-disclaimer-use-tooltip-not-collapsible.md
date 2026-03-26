# Cost analysis page: use tooltip/info bubble for disclaimer, not collapsible region

## Status: Open

## Priority: Medium

## Summary

Item 36 was implemented using a collapsible region for the disclaimer text.
This is wrong — a collapsible region takes up vertical space and requires
a click to expand a full-width section. The correct pattern is a small info
icon (i) next to the page title that shows a tooltip or popover on hover
with the disclaimer text.

## What Was Done Wrong

The agent used a details/summary collapsible which:
- Takes up a full row of vertical space even when collapsed
- Expands into a block-level region pushing content down
- Looks like a section header, not supplementary information

## What Should Be Done

Replace with a small info icon (e.g. a circled "i" character or SVG icon)
positioned inline next to the "Cost Analysis" heading. On hover, show a
lightweight tooltip with the two disclaimer lines:
- "API-Equivalent Estimates — subscription charges may differ."
- "Cost is recorded at the agent task level only."

Use CSS-only tooltip (::after pseudo-element on hover) or a minimal JS
tooltip. Do NOT use a collapsible/accordion/details element.

## Acceptance Criteria

- Is there a small info icon next to the page title? YES = pass, NO = fail
- Does hovering over the icon show the disclaimer text in a tooltip?
  YES = pass, NO = fail
- Does the tooltip disappear when the mouse leaves? YES = pass, NO = fail
- Is there NO collapsible/details/summary element for the disclaimer?
  YES = pass, NO = fail
- Does the disclaimer take zero vertical space when not hovered?
  YES = pass, NO = fail

## LangSmith Trace: 9442f151-e6fe-4564-9fc8-64c59e20cdd2
