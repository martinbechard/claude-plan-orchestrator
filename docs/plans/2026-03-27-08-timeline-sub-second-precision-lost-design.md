# Design: Timeline Sub-Second Precision Lost

Work item: tmp/plans/.claimed/08-timeline-sub-second-precision-lost.md

## Status

Previous implementation exists (marked "Review Required"). The Python-side elapsed
time computation and template rendering are in place. The legacy secs() and
fmt_duration() Jinja2 macros have been removed. This plan validates the existing
implementation and fixes any remaining issues.

## Architecture

Two files contain the fix:

1. **langgraph_pipeline/web/routes/proxy.py** - _parse_iso() uses
   datetime.fromisoformat() to preserve microsecond precision. _compute_elapsed()
   produces float elapsed_start_s / elapsed_end_s for each child run. span_s (float)
   is passed to the template. _format_duration() provides display_duration with
   sub-second precision (e.g. "0.04s").

2. **langgraph_pipeline/web/templates/proxy_trace.html** - Gantt bar positioning uses
   the pre-computed elapsed floats. Axis ticks use fmt_elapsed() which shows +Nms for
   sub-second spans and +Ns/+Nm Ns for longer spans.

## Key Files

| File | Role |
|---|---|
| langgraph_pipeline/web/routes/proxy.py | Timestamp parsing and elapsed computation |
| langgraph_pipeline/web/templates/proxy_trace.html | SVG Gantt chart rendering |
| tests/langgraph/web/test_proxy.py | Unit tests for proxy routes |

## Design Decisions

1. Python-side handles all duration computation with full microsecond precision
2. Template receives pre-computed floats - no parsing logic in Jinja2
3. fmt_elapsed() macro for axis tick labels handles sub-second correctly
4. Removed dead secs() and fmt_duration() macros to avoid confusion

## Edge Cases

- span_s == 0: clamped to 0.001 via safe_span in template
- Missing end_time: ELAPSED_FALLBACK_DURATION_S = 1.0 used
- Missing start_time on root: falls back to epoch zero
