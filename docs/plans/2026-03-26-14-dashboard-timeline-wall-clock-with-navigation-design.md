# Design: Dashboard Timeline — Wall-Clock Time Axis with Navigation

Work item: .claude/plans/.claimed/14-dashboard-timeline-wall-clock-with-navigation.md

## Architecture Overview

Pure frontend change to the dashboard timeline view. The existing timeline toggle
already shows active workers as Gantt-style bars; this feature rewrites the axis
and bar positioning to use real wall-clock time instead of elapsed duration, and
adds navigation controls (scroll back/forward, zoom in/out, live mode).

No backend or API changes are required. All data already arrives via SSE:
`active_workers` carries `elapsed_s` (seconds since start) and `item_type`;
`recent_completions` carries `finished_at` (ISO or Unix epoch) and `duration_s`.

## Key Files to Modify

| File | Change |
|---|---|
| `langgraph_pipeline/web/static/dashboard.js` | Rewrite `renderTimeline()` and `renderTimelineAxis()` for wall-clock positioning; add timeline nav state (`timelineWindowStart`, `timelineWindowEnd`, `timelineWindowMs`, `timelineLiveMode`); wire toolbar buttons; persist zoom in localStorage |
| `langgraph_pipeline/web/templates/dashboard.html` | Add compact toolbar (back/forward/zoom-out/zoom-in/live buttons + window label) above the axis inside `#timeline-container` |
| `langgraph_pipeline/web/static/style.css` | Add styles for toolbar, nav buttons, live-active state, gridlines, completion bar transparency and left-border outcome indicator |

## Design Decisions

### Wall-clock positioning
Each bar is placed by converting start/end epoch-ms values to a percentage of
the visible window:
- Active worker: `barStartMs = now - elapsed_s * 1000`, `barEndMs = now`
- Completion: `barEndMs = finishedAtToMs(finished_at)`, `barStartMs = barEndMs - duration_s * 1000`

Bars entirely outside the window are excluded; partially visible bars are clipped
at the window edges using `clampedStart = max(barStartMs, windowStart)`.

### Window state (module-level vars)
- `timelineWindowMs` — zoom level in ms (default 10 min, min 1 min; persisted in `localStorage["dashboard.timeline.windowMs"]`)
- `timelineWindowStart` / `timelineWindowEnd` — current epoch-ms bounds
- `timelineLiveMode` — if true, the window right edge tracks `Date.now()` on each SSE tick

### Navigation controls
Four buttons + live + label in a compact toolbar row above the axis:
- Back (◄): shift window left by half the window width; disables live mode
- Forward (►): shift window right; re-enables live mode if right edge reaches now
- Zoom out (−): double window width (max 24 h), pivot on window centre
- Zoom in (+): halve window width (min 1 min), pivot on window centre
- Live: snap right edge to now and re-enable live mode; highlighted when active

### Sorting
Active workers first (by `elapsed_s` descending), then completions (by
`finished_at` descending). Entries whose bar is fully outside the window are
excluded by `computeBarPosition()` returning null.

### Visual differentiation
- Active bars: solid colour by item_type (`.timeline-bar--defect/feature/analysis`)
- Completion bars: slightly transparent + left border by outcome colour
  (`.timeline-bar--completion` + `.timeline-bar-border--success/warn/fail`)

### Gridlines
Faint vertical lines at each axis tick position rendered as absolutely-positioned
`div.timeline-gridline` inside each `.timeline-bar-track`.
