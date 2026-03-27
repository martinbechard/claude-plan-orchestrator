# Worker Velocity Tracking — Design

**Work item:** tmp/plans/.claimed/16-worker-velocity-tracking.md
**Status:** Review & fix gaps in existing implementation

## Current State

Most of the velocity tracking feature is already implemented:

- **WorkerInfo** (dashboard_state.py): Has tokens_in, tokens_out, token_history,
  current_velocity(), get_velocity_series() methods
- **SSE payload**: Includes tokens_in, tokens_out, tokens_per_minute,
  velocity_history per active worker
- **Supervisor**: _compute_final_velocity() records tokens_per_minute into completions
- **Completions table**: Has tokens_per_minute REAL column, displayed on completions page
- **Timeline**: Color mode toggle (Type/Velocity) persisted to localStorage, discrete
  CSS velocity classes applied to bars
- **Bar text & tooltips**: Shows elapsed + velocity in bar label, title attribute tooltip

## Gaps Between Spec and Implementation

### 1. Velocity thresholds do not match spec
- **Code:** 250 / 1000 / 2000 tok/min (3 bands + grey)
- **Spec:** 500 / 2000 / 5000 tok/min (4 bands + grey)
- **Fix:** Update JS constants and CSS to match spec thresholds

### 2. Missing yellow band and wrong colors
- **Code:** grey, blue (#2563eb), green (#16a34a), red (#dc2626) — 4 classes
- **Spec:** grey, blue (#2563eb), green (#16a34a), yellow (#eab308), red (#dc2626) — 5 classes
- **Fix:** Add vel-yellow class, shift thresholds

### 3. No smooth gradient interpolation
- **Code:** Discrete CSS classes with flat colors
- **Spec:** "Interpolate between stops for smooth transitions"
- **Fix:** Replace CSS classes with inline background-color computed from velocity
  using JS color interpolation between the 4 spec stops

### 4. Bar text differs by mode
- **Code:** Always shows "elapsed  velocity" in both modes
- **Spec:** Type mode shows elapsed only ("3m 42s"), Velocity mode shows velocity
  only ("2.4k/m")
- **Fix:** Conditionally set bar label text based on colorMode

### 5. Velocity format should use "/m" suffix
- **Code:** "2.4k tok/min"
- **Spec:** "2.4k/m" (compact format for bar labels)
- **Fix:** Add compact format function for bar labels; keep verbose format for tooltips

## Key Files to Modify

| File | Changes |
|------|---------|
| langgraph_pipeline/web/static/dashboard.js | Fix thresholds, add color interpolation, conditional bar labels |
| langgraph_pipeline/web/static/style.css | Update/add velocity CSS classes or remove if using inline styles |
| langgraph_pipeline/web/templates/dashboard.html | No changes expected |

## Design Decisions

1. **Inline styles for interpolation**: Since smooth gradients require computed colors,
   use inline background-color instead of discrete CSS classes. Keep CSS classes as
   fallback for no-JS/accessibility.

2. **Compact velocity format**: Use "2.4k/m" in bar labels for readability at small
   bar widths. Tooltips keep the verbose "2.4k tok/min" format.

3. **Velocity vs parallelism chart**: The spec marks this as "Eventually" — deferred
   to a future backlog item. Not in scope for this plan.
