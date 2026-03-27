# Design: Dashboard Timeline Wall-Clock with Navigation (Review)

Work item: tmp/plans/.claimed/14-dashboard-timeline-wall-clock-with-navigation.md

## Architecture Overview

This feature was previously implemented and requires validation against the
acceptance criteria. The implementation is a pure frontend change spanning three
files: dashboard.js (timeline rendering, navigation state, toolbar wiring),
dashboard.html (toolbar markup), and style.css (timeline styles).

No backend changes are needed. All data arrives via SSE: active_workers carries
elapsed_s and item_type; recent_completions carries finished_at and duration_s.

## Key Files to Validate/Modify

| File | Scope |
|---|---|
| langgraph_pipeline/web/static/dashboard.js | Validate renderTimeline(), renderTimelineAxis(), computeBarPosition(), wireTimelineToolbar(), snap/zoom/pan logic, localStorage persistence |
| langgraph_pipeline/web/templates/dashboard.html | Validate toolbar markup (back/forward/zoom/live buttons, window range label) |
| langgraph_pipeline/web/static/style.css | Validate toolbar styles, gridlines, completion bar transparency, outcome borders, live-active highlight |

## Design Decisions

All design decisions from the original implementation remain valid:

- Wall-clock positioning via epoch-ms percentage of visible window
- Module-level window state vars (timelineWindowMs, timelineWindowStart/End, timelineLiveMode)
- Navigation: back/forward shift by half window, zoom halves/doubles, live snaps to now
- Sorting: active workers first (elapsed desc), then completions (finished_at desc)
- Active bars solid by item_type, completion bars transparent with outcome left border
- Gridlines as absolutely-positioned divs inside bar tracks
- Zoom level persisted in localStorage key "dashboard.timeline.windowMs"

## Validation Approach

Since the implementation already exists, the task is to validate each acceptance
criterion against the running code and fix any discrepancies found. The validator
agent runs automatically after each task to verify criteria.
