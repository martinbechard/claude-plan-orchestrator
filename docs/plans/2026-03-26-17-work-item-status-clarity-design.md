# Design: Work Item Status Clarity

## Overview

The `/item/<slug>` detail page currently shows a coarse 4-value status (running/completed/queued/unknown).
Users cannot tell what pipeline stage an item is in while it is being processed. This design
expands the status into a full pipeline-stage waterfall and adds an active-worker indicator.

## Pipeline Stage Waterfall

Stage detection in `_derive_pipeline_stage(slug)` checks in this order:

1. Active worker in `DashboardState.active_workers` for this slug → **executing**
2. Item in `docs/completed-backlog/` → **completed**
3. Item in `.claude/plans/.claimed/` + plan YAML exists → **executing**
4. Item in `.claude/plans/.claimed/` + design doc exists → **planning**
5. Item in `.claude/plans/.claimed/` → **claimed**
6. Plan YAML exists in `.claude/plans/` → **executing**
7. Design doc exists in `docs/plans/*-<slug>-design.md` → **designing**
8. Item in backlog dir (`docs/*/backlog/`) → **queued**
9. Otherwise → **unknown**

Stages **stuck** and **validating** are detected as sub-cases:
- **stuck**: completions exist and all have `outcome != "success"` and item is still in claimed/backlog
- **validating**: not exposed separately at this time (hard to distinguish from executing without extra state)

## Active Worker Info

A new `_get_active_worker(slug)` helper scans `DashboardState.active_workers.values()` for
a `WorkerInfo` whose `slug` matches. Returns a dict with `pid`, `elapsed_s`, `run_id`, or `None`.

## Key Files to Modify

| File | Change |
|------|--------|
| `langgraph_pipeline/web/routes/item.py` | Replace `_derive_status` with `_derive_pipeline_stage`; add `_get_active_worker`; pass `pipeline_stage` and `active_worker` to template |
| `langgraph_pipeline/web/templates/item.html` | Replace `status-{{ status }}` with `status-{{ pipeline_stage }}`; add CSS for new stages; add active-worker banner |

## Template Changes

### Status badge
Replace `status` variable with `pipeline_stage`. Add CSS classes:
- `status-claimed` — amber
- `status-designing` — lavender/purple
- `status-planning` — blue (light)
- `status-executing` — orange
- `status-stuck` — red

Existing classes remain: `status-running`, `status-completed`, `status-queued`, `status-unknown`.

### Active-worker banner
When `active_worker` is not None, render a highlighted panel below the header badges:

```
Currently running  PID 12345  |  Running for 4m 32s  |  [View trace →]
```

The trace link goes to `/proxy?trace_id=<run_id>` and is shown only when `run_id` is not None.

## Design Decisions

- The old `_derive_status()` helper is removed and replaced entirely; no backward-compat alias needed.
- The template variable is renamed from `status` to `pipeline_stage` to make the change explicit.
- `stuck` is detected conservatively: completions exist, all non-success, item not in completed dir.
- Active worker elapsed time is formatted as "Xm Ys" in the route layer, not in the template.
- Plan task progress count ("X of Y tasks complete") is already rendered in the Plan Tasks card header; no change needed there.
