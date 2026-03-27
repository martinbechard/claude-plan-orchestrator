# Design: Velocity Badge on Item Page (Active Worker Support)

## Summary

The item detail page already shows an average velocity badge computed from
completions history. However, when a worker is actively executing, the badge
should display the live velocity from the active worker's current_velocity()
method rather than only the historical average. This ensures the velocity
badge is meaningful during execution (not just after completion) and is
consistent with the dashboard timeline velocity mode.

## Architecture

### Current State

- item.py computes avg_velocity from completions tokens_per_minute (historical)
- _get_active_worker() accesses WorkerInfo but does not return velocity
- The template shows avg_velocity badge but has no live velocity path

### Changes Required

**langgraph_pipeline/web/routes/item.py**

1. In _get_active_worker(), add the worker's current_velocity() to the returned
   dict as a "current_velocity" field (rounded to int).
2. In item_detail(), when an active worker is present and has a non-zero
   current_velocity, use that as the displayed velocity instead of avg_velocity.
   This means: if active_worker and active_worker.current_velocity > 0, override
   avg_velocity with the live value.

**langgraph_pipeline/web/templates/item.html**

No template changes needed. The existing velocity badge markup already renders
avg_velocity correctly. The route handler will supply the right value (live
when active, historical when not).

### Design Decisions

- **Override at the route level, not the template**: Keeps the template simple.
  The route picks the best velocity value to display.
- **Fall back to completions average**: If the active worker has < 2 samples
  (current_velocity returns 0.0), fall back to the completions average so the
  badge still shows useful data.
- **Consistency with dashboard**: The dashboard uses WorkerInfo.current_velocity()
  for active items and completions.tokens_per_minute for finished items. This
  change mirrors that logic on the item page.

### Files to Modify

1. langgraph_pipeline/web/routes/item.py -- add current_velocity to active
   worker dict; override avg_velocity when worker is live
2. tests/ -- update any tests for _get_active_worker and item_detail

## Acceptance Criteria

- When a worker is actively running, the velocity badge shows the live
  current_velocity from the worker (not the completions average).
- For completed items, the badge continues to show the completions average.
- The velocity value is consistent with the dashboard timeline velocity mode.
