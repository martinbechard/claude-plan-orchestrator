# Design: Tool Calls Missing from Traces (Defect 16)

## Problem

Tool calls (Read, Edit, Bash, etc.) are stored in the traces DB as grandchildren —
children of graph node runs (execute_plan, create_plan, etc.), which are themselves
children of the root run. The `proxy_trace` route calls `proxy.get_children(run_id)`
with only the root run_id, so tool calls are never fetched or displayed.

## Architecture Overview

The fix has two layers: backend (fetch grandchildren) and frontend (render them).

### Backend — `langgraph_pipeline/web/routes/proxy.py`

In `proxy_trace()`, after computing `grandchild_counts`, fetch actual grandchildren
for each child that has them:

```python
grandchildren_by_parent: dict[str, list[dict]] = {}
for child_id in child_ids:
    if grandchild_counts.get(child_id, 0) > 0:
        raw_gc = proxy.get_children(child_id)
        grandchildren_by_parent[child_id] = [
            _compute_elapsed(_enrich_run(gc), root_start) for gc in raw_gc
        ]
```

Update `span_s` to include grandchild end times:

```python
all_items = enriched_children + [
    gc for gcs in grandchildren_by_parent.values() for gc in gcs
]
span_s = max(c["elapsed_end_s"] for c in all_items) if all_items else 0.0
```

Pass `grandchildren_by_parent` to the template alongside the existing variables.

### Frontend — `langgraph_pipeline/web/templates/proxy_trace.html`

**SVG Gantt chart — total row count:**

Use a Jinja2 namespace to count total rows (parent + grandchild rows):

```jinja
{% set ns = namespace(total_rows=children | length) %}
{% for child in children %}
  {% set ns.total_rows = ns.total_rows + (grandchildren_by_parent.get(child.run_id, []) | length) %}
{% endfor %}
{% set SVG_H = PAD_TOP + ns.total_rows * ROW_H + AXIS_H %}
```

**SVG Gantt chart — rendering rows:**

Use a running row counter via namespace:

```jinja
{% set ns = namespace(cur_row=0) %}
{% for child in children %}
  {# render child bar at row ns.cur_row #}
  {% set ns.cur_row = ns.cur_row + 1 %}
  {% for gc in grandchildren_by_parent.get(child.run_id, []) %}
    {# render gc bar indented at row ns.cur_row, smaller height #}
    {% set ns.cur_row = ns.cur_row + 1 %}
  {% endfor %}
{% endfor %}
```

Grandchild bars are rendered with:
- A visual indent (`GC_INDENT = 16` px, applied to label x position and bar x origin)
- Smaller bar height (`GC_BAR_H = 12`, vs `BAR_H = 18` for parent bars)
- Same `bar_color()` / `text_color()` macros (tool calls get cyan as defined by defect 13)
- Lighter row background to distinguish nesting level

**Expandable section below SVG:**

Replace the current "View N sub-runs →" link with inline grandchild run details
listed directly in the `<details>` block (name, duration). The link to the child's
detail page is kept as a secondary option.

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/web/routes/proxy.py` | Fetch grandchildren, compute `grandchildren_by_parent`, update `span_s`, pass to template |
| `langgraph_pipeline/web/templates/proxy_trace.html` | Render grandchild rows in SVG, show tool calls in expandable section |
| `tests/langgraph/web/test_proxy.py` | Tests verifying grandchild bars appear in SVG and details section |

## Design Decisions

1. **No DB schema change.** Grandchildren are fetched with the existing `get_children()`
   method called once per child that has sub-runs. No new queries or indices needed.

2. **Fetch at detail page load.** Grandchildren are fetched synchronously in the
   `proxy_trace()` handler, consistent with how children are fetched today.
   This is acceptable because the trace detail page is low-traffic.

3. **Two-level hierarchy only.** The fix fetches one more level (grandchildren).
   Deeper nesting (great-grandchildren) is not in scope; that level doesn't exist
   in the current data model.

4. **Same elapsed time logic.** Grandchildren use the same `_compute_elapsed()` helper
   as children, anchoring to the root run start time.

5. **Expandable section shows inline details.** Instead of linking away to the
   child's own trace page, grandchild tool calls are listed directly so users can
   see them without navigating away.
