# Design: Item Page - Last Run Trace and Velocity Badge

## Summary

Add two missing pieces of information to the /item/{slug} detail page:
1. A prominent link to the most recent trace near the status header
2. An average velocity badge (tokens/min) next to the pipeline stage badge

## Architecture

### Data Sources

- **Last run trace**: Already fetched via `_load_root_traces(slug)` in `item.py` -- the
  first element (sorted by `created_at DESC`) is the most recent. No new query needed.
- **Average velocity**: Already stored in the `completions` table as `tokens_per_minute`.
  The `_load_completions(slug)` call returns this field. Compute the average across all
  completions that have a non-null `tokens_per_minute` value.
- **Dashboard consistency**: The dashboard timeline velocity mode uses the same
  `tokens_per_minute` from completions, so averaging the same column ensures consistency.

### Key Files to Modify

1. **`langgraph_pipeline/web/routes/item.py`**
   - Compute `avg_velocity` from completions list (average of non-null `tokens_per_minute`)
   - Extract `last_trace` (first element of traces list, or None)
   - Pass both to the template context

2. **`langgraph_pipeline/web/templates/item.html`**
   - Add last-trace link in the header area (near slug/stage badges)
   - Add velocity badge next to the pipeline stage badge
   - Format velocity as "X tok/min" or "X.Xk tok/min" for large values

### Design Decisions

- **No new database queries**: All data is already fetched by existing functions.
  This is a pure presentation change plus a small computation in the route handler.
- **Average, not current**: Use the average across all completed runs for the velocity
  badge. When a worker is actively running, the active worker banner already shows
  live info. The badge reflects historical performance.
- **Consistent formatting**: Use the same tok/min formatting already used in the
  completions table on this page.
- **Graceful empty state**: When no traces exist or no velocity data, simply omit the
  badge/link rather than showing "N/A".


## Acceptance Criteria

- Does the item detail page show a link to the most recent trace near
  the top (not just in the traces table at the bottom)?
  YES = pass, NO = fail
- Does the item detail page show average tokens/min as a tag next to
  the pipeline stage badge? YES = pass, NO = fail
- Is the velocity value consistent with what the dashboard timeline
  shows for the same item? YES = pass, NO = fail
