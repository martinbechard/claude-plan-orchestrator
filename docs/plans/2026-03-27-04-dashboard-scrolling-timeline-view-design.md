# Design: Dashboard Scrolling Timeline View (04)

## Status: Review Required

This feature was previously implemented and marked complete, then returned because
"no visible implementation" was found. Code inspection shows the implementation
**does exist** across three files:

- **dashboard.html** (lines 42-70): Toggle button, timeline container, toolbar, axis, rows
- **dashboard.js** (694 lines): Full timeline rendering with zoom/scroll/live mode, color modes, localStorage persistence, bar positioning
- **style.css** (lines 622-800+): Complete timeline styling including bar colors, gridlines, axis ticks, completion state

## Architecture

The timeline is a pure-frontend feature. No backend changes are needed.

### Data Flow

```
SSE /api/stream (every 2s)
  -> dashboard.js: renderAll(data)
    -> renderTimeline(workers, completions)
      -> computeBarPosition() for each entry
      -> buildTimelineRow() with type/velocity coloring
    -> applyView() shows/hides table vs timeline
```

### Key Components

1. **Toggle button** in Active Workers section header ("Timeline" / "Table")
2. **Timeline toolbar**: scroll left/right, zoom in/out, live mode, color mode toggle
3. **Timeline axis**: time ticks showing HH:MM, auto-scaled to window
4. **Timeline rows**: one per active worker + recent completions, with colored bars
5. **localStorage persistence**: view preference, window size, color mode

### Acceptance Criteria from Backlog

- Toggle button switches between table and timeline views
- Timeline shows one row per active worker with growing bar
- Bar color by item type (defect/feature/analysis) with distinct palette
- Completion flash with outcome color then disappear
- localStorage persists toggle preference

## Plan

Since the implementation exists, this is a verification and fix task:

1. Validate all acceptance criteria against the existing code
2. Fix any gaps found (the "no visible implementation" return suggests a possible
   rendering bug, missing CSS include, or conditional that hides the view)

## Key Files

| File | Role |
|------|------|
| langgraph_pipeline/web/templates/dashboard.html | Timeline HTML structure |
| langgraph_pipeline/web/static/dashboard.js | SSE consumer and timeline rendering |
| langgraph_pipeline/web/static/style.css | Timeline styles |
| langgraph_pipeline/web/dashboard_state.py | SSE state with active_workers data |
