# Design: Cost Analysis Disclaimer — Tooltip Instead of Collapsible

## Problem

The cost disclaimer in `analysis.html` uses a `<details>/<summary>` collapsible element.
This occupies a full row even when collapsed and expands as a block-level section.
It should be an inline info icon with a hover tooltip that takes zero vertical space
when not hovered.

## Current State

`langgraph_pipeline/web/templates/analysis.html` lines 100–106:

- `.cost-info-toggle` styles target `details`/`summary` elements
- The `<details class="cost-info-toggle">` opens a block-level panel on click
- `.cost-info-panel` is an absolutely positioned div inside `<details>`

## Target State

Replace the `<details>/<summary>` block with a `<span class="cost-info-icon">` that:

- Renders a circled ⓘ character inline next to the "Cost Analysis" heading
- Shows a tooltip `<span class="cost-info-tooltip">` on `:hover` using CSS
- Uses `position: relative` on the wrapper and `position: absolute` on the tooltip
- Requires no JavaScript

## Key File

**`langgraph_pipeline/web/templates/analysis.html`**

Changes:
1. Replace `.cost-info-toggle` / `.cost-info-panel` CSS with `.cost-info-icon` / `.cost-info-tooltip` CSS
2. Replace `<details class="cost-info-toggle">` block with `<span class="cost-info-icon">` + inner tooltip span

## Design Decisions

- CSS-only tooltip via `:hover` on `.cost-info-icon` toggling visibility/opacity of `.cost-info-tooltip`
- Keep the same yellow/amber color scheme as the existing `.cost-info-panel`
- No JS required; accessibility note not needed for a hover decoration
- `white-space: nowrap` on tooltip to prevent wrapping across two short lines
- The tooltip disappears automatically when mouse leaves (no click-to-close needed)
