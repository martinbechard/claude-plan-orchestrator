# Design: Timeline Duplicate Labels and Elapsed Time (Review Pass)

## Work Item
tmp/plans/.claimed/04-timeline-duplicate-labels-and-elapsed-time.md

## Status

This defect was previously implemented. All three acceptance criteria appear to be
in place in the current codebase:

1. **Elapsed time labels** -- The template uses a fmt_elapsed() macro that renders
   +Xms / +Xs / +Xm Ys labels. The route passes pre-computed elapsed_start_s and
   elapsed_end_s via _compute_elapsed().

2. **No duplicate tick labels** -- Tick positioning uses float division (i * CHART_W / N_TICKS
   and i * safe_span / N_TICKS) instead of the original integer floor division.

3. **Grandchildren expandable** -- Child runs with grandchildren render nested bars in the
   SVG and HTML details/summary toggles below the chart.

## Architecture

All changes are confined to two files:
- langgraph_pipeline/web/routes/proxy.py -- route enrichment
- langgraph_pipeline/web/templates/proxy_trace.html -- Jinja2 rendering

No new files needed.

## Key Design Decisions

### Pre-computed elapsed fields in Python
The route computes elapsed_start_s / elapsed_end_s via datetime subtraction in
_compute_elapsed(), avoiding the fragile secs() macro that broke on midnight crossings.

### Float division for tick spacing
All Jinja2 arithmetic uses / (float division), eliminating duplicate ticks when
span_s < N_TICKS.

### Elapsed axis label format
The fmt_elapsed() macro handles three ranges: sub-second (+Xms), sub-minute (+Xs),
and minute-plus (+Xm Ys).

### Grandchildren in SVG + expandable HTML
Grandchild bars render inline in the SVG (indented with connector lines), with
a separate HTML details/summary section below the chart for inputs/outputs.

## Validation Focus

Since this was previously implemented, the plan task should:
1. Verify elapsed labels render correctly for short runs (< 5s), medium runs, and long runs
2. Confirm no duplicate tick labels appear at any run duration
3. Confirm grandchild expand/collapse works
4. Fix any issues found during validation

## Files to Modify

| File | Change |
|------|--------|
| langgraph_pipeline/web/routes/proxy.py | Fix if validation finds issues |
| langgraph_pipeline/web/templates/proxy_trace.html | Fix if validation finds issues |
| tests/langgraph/web/test_proxy_routes.py | Add/fix assertions if needed |
