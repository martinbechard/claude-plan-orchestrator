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




## 5 Whys Analysis

**Title:** Optimize parallelism level by tracking real-time worker velocity to stay within API budget

**Clarity:** 3/5

The mechanics are detailed and specific, but the underlying business problem isn't explicitly stated—the feature jumps directly to the "how" without framing the "why."

**5 Whys:**

1. **Why track worker velocity metrics?** → To measure whether running parallel workers causes individual worker throughput to degrade, revealing if parallelism is actually efficient or self-defeating.

2. **Why does it matter if parallelism reduces per-worker throughput?** → Because API tokens cost money; if adding a second worker causes each to drop from 3k to 1.5k tokens/min, you've increased cost per task instead of reducing completion time.

3. **Why can't simple throughput metrics surface this problem?** → Because aggregate metrics hide dynamic bottlenecks—you need per-minute, per-worker data to see *when* and *why* slowdowns occur (quota throttling, contention), not just end-state averages.

4. **Why must this be real-time visualization rather than post-run analysis?** → Because the pipeline runs continuously; operators need to see velocity degradation *as it happens* to adjust worker count live, not wait for historical reports to optimize next time.

5. **Why is finding the optimal parallelism level a critical problem?** → Because the project operates under API budget constraints—running too many workers wastes spend, too few leaves capacity unused; there's a sweet spot, and they need visibility to find it.

**Root Need:** Determine the cost-effective parallelism level by observing how worker throughput degrades in real time, enabling operators to maximize task completion within API budget constraints.

**Summary:** The project needs real-time per-worker velocity data to find the parallelism level that delivers maximum throughput per dollar spent.
