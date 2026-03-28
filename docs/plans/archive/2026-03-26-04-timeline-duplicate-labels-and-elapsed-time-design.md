# Design: Timeline Duplicate Labels and Elapsed Time Fix

## Work Item
.claude/plans/.claimed/04-timeline-duplicate-labels-and-elapsed-time.md

## Problem Summary

The Gantt chart in `proxy_trace.html` has two related bugs:

1. **Duplicate tick labels**: `tick_s = ns.min_s + (i * span_s // N_TICKS)` uses integer floor
   division. When `span_s < N_TICKS` (e.g. a 3-second run with 5 ticks), the step is 0 and
   consecutive ticks land on the same second, producing identical labels.

2. **Absolute time labels**: Labels are formatted as HH:MM:SS derived from seconds-since-midnight
   instead of elapsed offsets from the run start (`+0s`, `+30s`, `+2m`).

A third feature request is also included: child runs that have grandchildren should be
expandable in the timeline to show a nested breakdown.

## Architecture

All changes are confined to:
- `langgraph_pipeline/web/routes/proxy.py` — Python route enrichment
- `langgraph_pipeline/web/templates/proxy_trace.html` — Jinja2 template rendering

No new files are needed.

## Key Design Decisions

### Elapsed time via Python datetime subtraction (not Jinja2 secs() macro)

The `secs()` macro converts timestamps to seconds-since-midnight by parsing `HH:MM:SS`.
This is fragile: it produces wrong results for runs crossing midnight and accumulates
truncation errors. Instead, the route computes elapsed seconds as floats using Python
`datetime` subtraction and passes pre-computed values to the template.

New fields added to each enriched child dict:
- `elapsed_start_s: float` — seconds from root run start to child start
- `elapsed_end_s: float` — seconds from root run start to child end (or start+1 if running)

The route also passes `span_s: float` (total span of all children) to the template context.

### Float division for tick and bar positioning

All Jinja2 arithmetic that previously used `//` (integer floor division) is changed to `/`
(float division). This eliminates duplicate ticks when `span_s < N_TICKS`.

### Elapsed axis label format

Tick labels change from `HH:MM:SS` to `+Xs` or `+Xm Ys`:
- `offset < 60`: show `+{offset}s`
- `offset >= 60`: show `+{minutes}m {seconds}s`

### Grandchildren expandability

The route pre-fetches grandchild counts for each child in a single batch query
(using the existing `count_children_batch` proxy method). Children with grandchildren
are rendered with an HTML `<details>/<summary>` toggle that links to the child's own
trace detail page (or loads it inline). Given SVG cannot host interactive HTML elements,
the expandable section is rendered as a separate HTML block below the Gantt chart rather
than embedded in the SVG.

## Files to Modify

| File | Change |
|------|--------|
| `langgraph_pipeline/web/routes/proxy.py` | `proxy_trace()`: compute elapsed times per child, batch-fetch grandchild counts, pass `span_s` and enriched children to template |
| `langgraph_pipeline/web/templates/proxy_trace.html` | Replace `secs()` macro usage with pre-computed elapsed fields; float division for bars and ticks; elapsed label format; grandchildren toggle below chart |

## Test Impact

- `tests/langgraph/web/test_proxy_routes.py` — update or add assertions for new template context fields
- No new test files needed
