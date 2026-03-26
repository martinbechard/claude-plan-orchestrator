# Design: Dashboard Scrolling Timeline View

Work item: .claude/plans/.claimed/04-dashboard-scrolling-timeline-view.md

## Architecture Overview

A toggle in the Active Workers section header switches between the existing card
grid and a new timeline (Gantt-style) view. The timeline is driven by the same
SSE `active_workers` payload already used for the cards — no backend changes
needed. The toggle preference is persisted in `localStorage`.

The timeline renders as a CSS flexbox chart: one row per active worker, with a
bar whose width is a percentage of the longest `elapsed_s` among current workers.
The time axis re-scales on every SSE tick. A completion flash animates briefly
before a worker disappears.

## Key Files to Modify

| File | Change |
|---|---|
| `langgraph_pipeline/web/templates/dashboard.html` | Add toggle button next to "Active Workers" heading; add timeline container div; add `tpl-timeline-row` template |
| `langgraph_pipeline/web/static/style.css` | Add timeline layout, bar, axis, and flash-animation styles |
| `langgraph_pipeline/web/static/dashboard.js` | Add `renderTimeline()`, toggle logic, localStorage persistence, completion flash |

## Design Decisions

### CSS flexbox over SVG
The spec recommends flexbox for simplicity and responsiveness. Bar widths are
`calc(elapsed_s / max_elapsed_s * 100%)`, updated on each SSE tick.

### Distinct colour palette for timeline bars
The card/badge palette (red, blue, purple) is reused for badges elsewhere. The
timeline bars use a separate warm palette so they read as a chart, not badges:
- defect: `#f97316` (orange)
- feature: `#06b6d4` (cyan)
- analysis: `#eab308` (amber-yellow)

### Completion flash
When a worker finishes, `renderWorkers` / `renderTimeline` diff the current
worker set. Workers present in the previous tick but absent in the new one are
briefly shown in their outcome colour (green / amber / red) with a fade-out CSS
animation before removal.

Because the SSE `state` event carries `recent_completions`, the flash logic can
match a departing worker slug against the latest completion to determine outcome
colour.

### Time axis labels
The axis shows 0, 25%, 50%, 75%, 100% tick labels in elapsed time, derived from
`maxElapsed`. Labels update on every tick. The axis is rendered as a flex row of
absolute-positioned spans above the bar area.

### localStorage key
`dashboard.workers.view` — values `"table"` (default) or `"timeline"`.

### Toggle placement
A small `<button id="workers-view-toggle">` sits in the `<h2>` row, floated
right via flexbox on the section header. Label alternates: "Timeline" / "Table".
