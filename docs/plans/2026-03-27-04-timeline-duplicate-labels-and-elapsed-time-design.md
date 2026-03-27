# Design: Timeline Duplicate Labels and Elapsed Time

## Work Item
tmp/plans/.claimed/04-timeline-duplicate-labels-and-elapsed-time.md

## Architecture Overview

This defect was previously implemented. The backlog item is marked "Review Required",
meaning a prior implementation exists but needs validation against acceptance criteria.

### Key Files

| File | Role |
|------|------|
| langgraph_pipeline/web/routes/proxy.py | Route with elapsed time computation via _compute_elapsed() |
| langgraph_pipeline/web/templates/proxy_trace.html | Gantt chart template with elapsed labels and grandchild expansion |
| tests/langgraph/web/test_proxy_routes.py | Route tests (may need updates) |

### Current Implementation State

**proxy.py (route)**
- _compute_elapsed() computes elapsed_start_s / elapsed_end_s via Python datetime subtraction
- proxy_trace() passes span_s (float), grandchild_counts, and grandchildren_by_parent to template
- Grandchildren are batch-fetched and enriched with elapsed times

**proxy_trace.html (template)**
- fmt_elapsed() macro formats offsets as "+Xms", "+Xs", or "+Xm Ys"
- Tick labels use fmt_elapsed(tick_offset) with float division
- safe_span = [span_s, 0.001] | max prevents division-by-zero
- Grandchild bars rendered inline in SVG with indentation
- Expandable details/summary sections below chart for grandchild details

### Acceptance Criteria

1. Axis ticks show elapsed time from root run start: "+0s", "+30s", "+2m"
2. No duplicate labels regardless of run duration
3. Child run rows with grandchildren can be expanded to reveal them

## Design Decisions

- Use Python datetime subtraction for elapsed times (avoids secs() macro integer issues)
- Float division for tick computation (prevents zero-step on short spans)
- Batch-fetch grandchildren in route to avoid N+1 queries in template
- Single validation task since implementation already exists
