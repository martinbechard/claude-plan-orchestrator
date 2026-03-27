# Timeline: duplicate tick labels and show elapsed time instead of absolute time

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

The Gantt chart time axis shows duplicate tick values (e.g. "10:30:00" appearing
twice) when the run spans fewer seconds than the number of ticks. The absolute
HH:MM:SS labels are also less useful than elapsed-from-start labels like "+0s",
"+30s", "+1m 30s".

Additionally, child runs that have their own children should be expandable in
the timeline to show a nested breakdown.

## Observed Behavior

- Axis tick labels repeat the same timestamp on short runs (integer floor
  division of span_s / N_TICKS rounds to zero).
- Axis shows "10:30:00 / 10:30:12 / ..." instead of "+0s / +12s / ...".

## Root Cause

In proxy_trace.html, tick_s is computed with integer `//` division. When
span_s < N_TICKS the step is 0 and consecutive ticks land on the same second.
Labels are formatted as absolute HH:MM:SS derived from seconds-since-midnight
instead of elapsed offsets.

## Expected Behavior

- Axis ticks show elapsed time from the root run start: "+0s", "+30s", "+2m".
- No duplicate labels regardless of run duration.
- Child run rows that have grandchildren can be expanded to reveal them.

## Suggested Fix

1. Compute elapsed_start_s and elapsed_end_s per child in the Python route
   (proxy.py) using datetime subtraction, avoiding the secs() macro.
2. Pass span_s (float) from Python and use float division in Jinja2 for ticks.
3. Format axis labels as elapsed offset ("+Xs" or "+Xm Ys").
4. Pre-fetch grandchildren in the route and pass grandchildren_by_parent dict
   to the template; render each child with a details/summary toggle when
   grand_count > 0.




## 5 Whys Analysis

Title: Timeline display obfuscates performance bottleneck identification in short-duration runs

Clarity: 4

5 Whys:
1. Why are duplicate labels and absolute timestamps problematic for users analyzing the timeline? Because users investigating run performance need to understand relative timing within the execution (e.g., "this step took 30s and happened 2m in") rather than absolute wall-clock time (what hour of the day it occurred).

2. Why does relative timing matter more than absolute timestamps for debugging and optimization? Because understanding run dynamics requires seeing the sequence and causality of operations—when each step starts and ends relative to others—rather than simply recording when in the day something happened.

3. Why is understanding operation sequencing and causality critical? Because identifying performance bottlenecks requires answering questions like "which operations are slow," "which ones block others," and "how do dependencies flow through the execution graph."

4. Why does the current absolute-time display prevent effective bottleneck identification? Because converting from absolute timestamps to relative timing requires mental math, and duplicate labels create ambiguity about which ticks represent which time offsets, making timing patterns hard to discern at a glance.

5. Why is quick, intuitive bottleneck visibility essential for this user base? Because performance optimization decisions depend on identifying where time is actually spent—without clear visibility, users cannot make informed prioritization decisions about what to optimize or how to restructure workflows.

Root Need: Enable intuitive visualization of operation timing and sequencing relative to run start so users can quickly identify which steps are slow and understand execution flow without cognitive overhead.

Summary: Users need elapsed-time labels instead of absolute timestamps to intuitively see where time is spent and optimize run performance.
