# Design: Timeline Sub-Second Precision Lost

Work item: tmp/plans/.claimed/08-timeline-sub-second-precision-lost.md

## Status

Previous implementation exists and is mostly complete. The Python-side elapsed time
computation (elapsed_start_s / elapsed_end_s floats) is in place and Gantt bars use
it correctly. The legacy secs() Jinja2 macro and its dependent fmt_duration() macro
remain in the template as dead/fallback code with integer-only precision.

## Architecture

Two files contain the fix:

1. **langgraph_pipeline/web/routes/proxy.py** - _parse_iso() uses
   datetime.fromisoformat() to preserve microsecond precision. _compute_elapsed()
   produces float elapsed_start_s / elapsed_end_s for each child run. span_s (float)
   is passed to the template. _format_duration() provides display_duration with
   sub-second precision (e.g. "0.04s").

2. **langgraph_pipeline/web/templates/proxy_trace.html** - Gantt bar positioning uses
   the pre-computed elapsed floats instead of the integer secs() macro. Axis ticks use
   fmt_elapsed() which shows +Nms for sub-second spans and +Ns/+Nm Ns for longer spans.

## Remaining Issues

1. The secs() macro (lines 38-44) extracts only HH:MM:SS integers -- dead code that
   should be removed to avoid confusion
2. The fmt_duration() Jinja macro (lines 46-55) uses secs() and shows integer seconds --
   also dead code since display_duration is always set by Python-side _enrich_run()
3. Line 90 falls back to fmt_duration() when display_duration is falsy -- this path
   would show wrong values for sub-second runs; should fall back to a dash instead

## Key Files

| File | Role |
|---|---|
| langgraph_pipeline/web/routes/proxy.py | Timestamp parsing and elapsed computation |
| langgraph_pipeline/web/templates/proxy_trace.html | SVG Gantt chart rendering |

## Design Decisions

1. Remove secs() and fmt_duration() macros entirely -- Python-side handles all duration
   computation with full precision
2. Keep fmt_elapsed() macro for axis tick labels (already handles sub-second correctly)
3. Replace fmt_duration() fallback on line 90 with a simple dash

## Edge Cases

- span_s == 0: clamped to 0.001 via safe_span in template
- Missing end_time: ELAPSED_FALLBACK_DURATION_S = 1.0 used
- Missing start_time on root: falls back to epoch zero
