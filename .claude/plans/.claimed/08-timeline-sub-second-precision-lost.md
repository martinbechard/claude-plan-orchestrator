# Timeline: all child runs appear at same position when they span less than 1 second

## Status: Open

## Priority: High

## Summary

When child runs all complete within the same wall-clock second, every bar
renders at x=0 in the Gantt chart — they all appear to start at the same time.
This makes the timeline completely useless for fast pipelines.

## Reproduction

Run ID 019d288e-61b7-7402-9de3-72465a7810f7 has 10 children, all with
start_time between 05:11:53.016586 and 05:11:53.020070 (4 ms total span).
The timeline shows all bars stacked at the left edge.

## Root Cause

The secs() Jinja2 macro in proxy_trace.html extracts only HH:MM:SS from the
ISO timestamp string (positions 11-19), discarding the fractional seconds
entirely:

    (ts[11:13] | int) * 3600 + (ts[14:16] | int) * 60 + (ts[17:19] | int)

When all runs fall within the same second, cs == ns.min_s for every child, so
bar_x = LABEL_W + 0 for all bars. The span_s is also 0, clamped to 1, making
the axis show a 1-second range that none of the actual runs use.

## Expected Behavior

The timeline should use millisecond (or microsecond) precision. A run that
takes 4 ms should show proportional bar widths across the chart, not a pile
of zero-width bars at the left edge.

## Suggested Fix

Replace the secs() macro with Python-side timestamp parsing in the route
(proxy.py). Use datetime.fromisoformat() to get a float seconds value with
microsecond precision. Pass elapsed_start_s and elapsed_end_s (float) for
each child run to the template, along with span_s (float). The template then
does pure pixel arithmetic:

    bar_x = LABEL_W + (child.elapsed_start_s / span_s * CHART_W) | int
    bar_w = max(((child.elapsed_end_s - child.elapsed_start_s) / span_s * CHART_W) | int, 4)

Axis tick labels should also switch to elapsed format (+0ms, +1ms, +4ms) for
sub-second spans, or +0s/+30s for longer spans.

This fix also resolves the duplicate tick label issue described in the
related item (same secs() macro root cause).

## LangSmith Trace: f7024d0b-96b1-4604-8726-4a40a5ae4222
