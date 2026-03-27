# Design: Timeline Sub-Second Precision Lost

Work item: tmp/plans/.claimed/08-timeline-sub-second-precision-lost.md

## Status

Previous implementation exists and is mostly complete. This plan validates
acceptance criteria and fixes any remaining gaps.

## Architecture

Two files contain the fix:

1. **langgraph_pipeline/web/routes/proxy.py** - _parse_iso() uses
   datetime.fromisoformat() to preserve microsecond precision. _compute_elapsed()
   produces float elapsed_start_s / elapsed_end_s for each child run. span_s (float)
   is passed to the template.

2. **langgraph_pipeline/web/templates/proxy_trace.html** - Gantt bar positioning uses
   the pre-computed elapsed floats instead of the integer secs() macro. Axis ticks use
   fmt_elapsed() which shows +Nms for sub-second spans and +Ns/+Nm Ns for longer spans.

## Remaining Concern

The secs() Jinja2 macro still exists and is used by the fmt_duration fallback macro.
This fallback only triggers when run.display_duration is not set, which should not
happen for enriched children. The macro can be removed or left as dead code cleanup.

## Key Files

| File | Role |
|---|---|
| langgraph_pipeline/web/routes/proxy.py | Timestamp parsing and elapsed computation |
| langgraph_pipeline/web/templates/proxy_trace.html | SVG Gantt chart rendering |

## Edge Cases

- span_s == 0: clamped to 0.001 via safe_span in template
- Missing end_time: ELAPSED_FALLBACK_DURATION_S = 1.0 used
- Missing start_time on root: falls back to epoch zero
