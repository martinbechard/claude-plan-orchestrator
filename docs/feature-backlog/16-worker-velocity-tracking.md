# Track worker velocity (tokens/minute) and visualize in timeline

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## RETURNED — Pipeline grabbed this before edits were complete

## Summary

Track the token throughput (tokens per minute) of each active worker to
understand whether running parallel workers degrades individual throughput.
Display velocity in the active workers timeline with a thermal colour
gradient so slowdowns are visible at a glance.

## Requirements

### Velocity metric
- For each active worker, track per-minute token deltas (not just a
  running average). Store a rolling window of minute-by-minute token
  counts so the colour reflects current throughput, not smoothed over
  the full run. This lets the user see velocity changes — e.g. a worker
  slowing down mid-run when another worker starts competing for quota.
- total_tokens = input_tokens + output_tokens from the worker's trace
  metadata (already available in execute_task traces).
- The metric needs to be exposed in the SSE /api/state payload per worker.

### Data source
- The supervisor poll loop (every 5s) can query the traces DB for the
  worker's run_id to get latest token counts.
- Compute delta from previous poll to get current-minute velocity.

### SSE payload extension
- Add to each active_worker entry in the SSE state:
  tokens_in, tokens_out, tokens_per_minute (floats, 0 if not yet available)

### Timeline colour mode toggle
- Add a colour mode toggle button in the timeline toolbar with two modes:
  - "Type" (default): bars coloured by item type (defect/feature/analysis)
    using the existing orange/cyan/yellow palette
  - "Velocity": bars use a thermal gradient based on current-minute
    throughput:
    - Blue (#2563eb): low velocity (< 500 tok/min)
    - Green (#16a34a): moderate (500-2000 tok/min)
    - Yellow (#eab308): high (2000-5000 tok/min)
    - Red (#dc2626): very high (> 5000 tok/min)
    - Grey: no data yet
    Interpolate between stops for smooth transitions.
- The toggle persists in localStorage (key "dashboard.timeline.colorMode")

### Bar text and tooltips
- Write the value directly inside the bar as dark text (#1a1a2e) so it
  contrasts against all gradient colours.
- In Type colour mode: show elapsed time inside the bar (e.g. "3m 42s").
- In Velocity colour mode: show velocity inside the bar (e.g. "2.4k/m").
- When text is clipped (bar too narrow), show a tooltip on hover with
  full details: elapsed time, velocity, slug, item type. Use the title
  attribute or a lightweight CSS tooltip.
- Both modes: tooltip always shows full details regardless of clipping.

### Historical analysis
- Store final velocity for each completion in the completions table (new
  column: tokens_per_minute REAL).
- On the completions history page, show a column for velocity so the user
  can compare throughput across different parallelism levels.
- Eventually: a chart showing velocity vs active_worker_count to directly
  answer "does parallelism hurt throughput?"

## Implementation Notes

- DashboardState.WorkerInfo needs new fields: tokens_in, tokens_out,
  prev_tokens (for delta calculation)
- Velocity = token_delta_since_last_poll / (poll_interval_s / 60)
- For the thermal gradient, compute an HSL hue from the velocity value
  mapped to the blue-green-yellow-red range, or use discrete CSS classes
