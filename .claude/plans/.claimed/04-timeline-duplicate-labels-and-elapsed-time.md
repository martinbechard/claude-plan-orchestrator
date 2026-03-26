# Timeline: duplicate tick labels and show elapsed time instead of absolute time

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

## LangSmith Trace: bb4a20af-3ff3-44e6-a5ea-f88a3b486284
