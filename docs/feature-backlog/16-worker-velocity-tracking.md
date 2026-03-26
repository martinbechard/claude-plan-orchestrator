# Track worker velocity (tokens/minute) and visualize in timeline

## Status: Open

## Priority: Medium

## Summary

Track the token throughput (tokens per minute) of each active worker to
understand whether running parallel workers degrades individual throughput.
Display velocity as bar colour intensity in the active workers timeline so
slowdowns are visible at a glance.

## Requirements

### Velocity metric
- For each active worker, compute tokens_per_minute = total_tokens /
  elapsed_minutes, updated on each SSE tick.
- total_tokens = input_tokens + output_tokens from the worker's trace
  metadata (already available in execute_task traces).
- The metric needs to be exposed in the SSE /api/state payload per worker.

### Data source
- The supervisor or worker process needs to periodically report token
  counts back to the dashboard state. Options:
  a. Read from the traces DB (query latest token counts for the worker's
     run_id on each poll cycle).
  b. Have the worker write incremental token counts to its result file or
     a sidecar file that the supervisor reads.
  c. Parse the Claude CLI streaming output for token usage updates.
- Option (a) is simplest if traces are written incrementally during
  execution (they are — the SDK sends start events with partial data).

### SSE payload extension
- Add to each active_worker entry in the SSE state:
  tokens_in, tokens_out, tokens_per_minute (floats, 0 if not yet available)

### Timeline visualization
- Add a colour mode toggle button in the timeline toolbar with two modes:
  - "Type" (default): bars coloured by item type (defect/feature/analysis)
    using the existing orange/cyan/yellow palette
  - "Velocity": bars coloured by throughput intensity:
    - High velocity (> 5000 tokens/min): bright/saturated
    - Medium velocity: normal
    - Low velocity (< 1000 tokens/min): desaturated/dim
    - No data yet: grey
- The toggle persists in localStorage (key "dashboard.timeline.colorMode")
- Show the numeric velocity next to the elapsed time label (e.g.
  "3m 42s  2.4k tok/min") regardless of which colour mode is active

### Historical analysis
- Store final velocity for each completion in the completions table (new
  column: tokens_per_minute REAL).
- On the completions history page, show a column for velocity so the user
  can compare throughput across different parallelism levels.
- Eventually: a chart showing velocity vs active_worker_count to directly
  answer "does parallelism hurt throughput?"

## Implementation Notes

- DashboardState.WorkerInfo needs new fields: tokens_in, tokens_out
- The supervisor poll loop (every 5s) can query the traces DB for the
  worker's run_id to get latest token counts
- Velocity = (tokens_in + tokens_out) / (elapsed_s / 60)
- For the timeline bar colour, use CSS opacity or HSL lightness scaled
  by velocity relative to the session's average velocity
