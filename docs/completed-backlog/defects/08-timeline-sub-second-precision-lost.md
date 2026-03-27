# Timeline: all child runs appear at same position when they span less than 1 second

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


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




## 5 Whys Analysis

Title: Microsecond-precision timeline needed for debugging fast-executing LangGraph pipelines
Clarity: 5

5 Whys:
1. Why do all child run bars appear at the same position when they complete within the same second? → Because the secs() Jinja2 macro extracts only HH:MM:SS from ISO timestamps, completely discarding the fractional seconds that differentiate operations within 1-second windows.

2. Why does the code only extract whole seconds instead of including fractional seconds? → Because the original template-based implementation treated sub-second precision as unnecessary overhead—it's simpler to parse three integer components in Jinja2 than to handle full datetime arithmetic with microsecond granularity.

3. Why was the design built assuming whole-second granularity would be sufficient? → Because the timeline feature was designed for typical enterprise pipelines where most child operations span multiple seconds, not for high-throughput LangGraph workflows where 10 children can complete in 4 milliseconds.

4. Why are we now encountering pipelines that execute at millisecond scale? → Because LangGraph enables orchestration of many small, fast operations (LLM calls, parsing, validation) that chain together with minimal overhead, creating legitimate use cases where sub-second precision is essential to understanding execution flow.

5. Why is it critical that users can see millisecond-level timing differences in the timeline? → Because without fine-grained visibility, the timeline becomes useless for its core purpose: identifying performance bottlenecks, concurrency issues, and sequential vs. parallel execution patterns—users cannot optimize what they cannot see.

Root Need: Users need high-resolution (microsecond-level) execution timing visualization to provide meaningful observability and enable performance optimization of fast-executing LangGraph orchestrations.

Summary: The timeline feature must support microsecond-precision to remain functional as an observability tool for modern, fast-executing LangGraph workflows.
