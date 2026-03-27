# Dashboard timeline: wall-clock time axis with navigation and zoom

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

Rewrite the dashboard timeline view to use actual wall-clock time on the X
axis instead of elapsed duration. Show both active workers and recent
completions as bars positioned by real start/end times. Add navigation
controls to scroll back in time and zoom in/out.

## Requirements

### Time-based X axis
- X axis shows local wall-clock time (HH:MM format)
- Active worker bars: start at (now - elapsed_s), extend to now
- Completion bars: start at (finished_at - duration_s), end at finished_at
- Bars outside the visible window are excluded; partially visible bars are
  clipped at window edges

### Default window and zoom
- Default window: last 10 minutes
- Zoom in: halve window width (minimum 1 minute)
- Zoom out: double window width
- Persist zoom level in localStorage key "dashboard.timeline.windowMs"

### Navigation controls (compact toolbar above the timeline)
- Back button: shift window left by half the window width
- Forward button: shift window right by half the window width
- Zoom out / zoom in buttons
- Live button: snap back to live mode (window right edge = now)
- Display current window range as text: "10:30 - 10:40 (10m)"

### Live mode
- Default: live mode on, window right edge tracks now on each SSE tick
- Pressing back disables live mode (window freezes)
- Pressing Live re-enables it
- Visual indicator: Live button highlighted when active

### Show both active workers and completions
- Active workers: solid bars extending to right edge (now), coloured by
  item_type (defect/feature/analysis)
- Completions: slightly transparent bars with left border indicating
  outcome colour (green=success, amber=warn, red=fail)
- Sort: active workers first (by elapsed desc), then completions (by
  finished_at desc)

### localStorage
- View preference (table vs timeline) already saved — keep it
- Additionally save window width (zoom level)

## Implementation Notes

- Vanilla JS only, no libraries
- Reuse existing template elements (timeline-container, timeline-axis,
  timeline-rows, tpl-timeline-row)
- Rewrite renderTimeline() and renderTimelineAxis() in dashboard.js
- Add timeline navigation state as module-level vars (windowStart,
  windowEnd, windowWidth, isLive)
- Add toolbar HTML to dashboard.html inside timeline-container
- Add faint vertical gridlines at each tick position in the bar track
- Use existing colour classes (.timeline-bar--defect, etc.)
