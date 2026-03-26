# Design: Timeline Sub-Second Precision Lost

Work item: .claude/plans/.claimed/08-timeline-sub-second-precision-lost.md

## Problem

When all child runs complete within the same wall-clock second, every Gantt bar
renders at x=0. Two bugs cause this:

1. `_parse_iso()` in `routes/proxy.py` truncates timestamps to 19 characters
   before calling `strptime`, discarding fractional seconds entirely.
2. `proxy_trace.html` uses the `secs()` Jinja2 macro for Gantt bar placement,
   which also discards sub-second precision.

The Python route already computes `elapsed_start_s`, `elapsed_end_s` (float
seconds from root start), and `span_s` and passes them to the template — but
the template ignores them and recalculates using integer secs().

## Fix Architecture

### 1. Fix `_parse_iso()` — `langgraph_pipeline/web/routes/proxy.py`

Replace the truncating `strptime` call with `datetime.fromisoformat()`, which
handles the full ISO-8601 string including fractional seconds. Python 3.7+
supports this natively for the format LangSmith emits.

Before (loses fractional seconds):
```python
return datetime.strptime(ts[:19], _ISO_FMT).replace(tzinfo=timezone.utc)
```

After (preserves microseconds):
```python
return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
```

This also fixes `_format_duration()` (and thus `display_duration`) for fast
runs, since it delegates to `_parse_iso`.

### 2. Refactor Gantt chart — `proxy_trace.html`

Remove the integer `secs()` and `fmt_duration` macros from the Gantt section.
Replace the bar-position calculation with the pre-computed Python values:

```jinja2
{% set bar_x = LABEL_W + (child.elapsed_start_s / span_s * CHART_W) | int %}
{% set bar_w = [((child.elapsed_end_s - child.elapsed_start_s) / span_s * CHART_W) | int, 4] | max %}
```

`span_s` is already passed from the route. Use `child.display_duration` for the
bar label (already computed by Python's `_format_duration` with corrected
`_parse_iso`).

### 3. Elapsed-format axis ticks

Replace the absolute HH:MM:SS tick labels with relative elapsed labels:
- Sub-second spans (span_s < 1): `+Nms` format (e.g. "+0ms", "+4ms")
- Longer spans: `+Ns` or `+Nm Ns` format

The axis ticks are always relative to the root run start (offset = 0 for first
tick), computed as `tick_elapsed = i * span_s / N_TICKS`.

## Files to Modify

| File | Change |
|---|---|
| `langgraph_pipeline/web/routes/proxy.py` | Fix `_parse_iso()` to use `fromisoformat` |
| `langgraph_pipeline/web/templates/proxy_trace.html` | Replace secs()-based Gantt with elapsed_start_s/elapsed_end_s/span_s; elapsed axis ticks |

## Files NOT Modified

- `langgraph_pipeline/web/proxy.py` — no change, data layer is correct
- `tests/langgraph/web/test_proxy.py` — update `_parse_iso` tests if any exist

## Edge Cases

- `span_s == 0`: clamp to a small positive value (e.g. 0.001) to avoid division
  by zero in template. The route already handles this by using `max(..., 1)` but
  that's for integer seconds; for float we use `max(span_s, 0.001)`.
- Children with no `end_time`: already handled by `_compute_elapsed` using
  `ELAPSED_FALLBACK_DURATION_S = 1.0`.
- Root run with no `start_time`: already handled by falling back to epoch zero.
