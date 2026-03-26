# Trace-Based Cost Analysis Page — Design

Work item: .claude/plans/.claimed/10-trace-cost-analysis-page.md

## Architecture Overview

Replace the existing `/analysis` route (which reads from the fake `cost_tasks` table via
`CostLogReader`) with a new implementation that queries real cost data from the `traces`
table using `json_extract()` on `metadata_json`.

The URL `/analysis` and the nav link in `base.html` are kept unchanged so no other pages
need updating. Only the route implementation and template are replaced.

## Data Model

Cost data lives in `traces.metadata_json` for `execute_task` and `validate_task` runs:

```
json_extract(metadata_json, '$.total_cost_usd')   -- float
json_extract(metadata_json, '$.input_tokens')      -- int
json_extract(metadata_json, '$.output_tokens')     -- int
json_extract(metadata_json, '$.duration_ms')       -- int
json_extract(metadata_json, '$.tool_calls_count')  -- int
json_extract(metadata_json, '$.model')             -- str
json_extract(metadata_json, '$.item_slug')         -- str (980 rows)
json_extract(metadata_json, '$.item_type')         -- str
```

`parent_run_id` links children to parents for inclusive cost rollup via recursive CTE.

## Key Files

### Modify
- `langgraph_pipeline/web/proxy.py` — add query methods for trace-based cost data
- `langgraph_pipeline/web/routes/analysis.py` — replace implementation
- `langgraph_pipeline/web/templates/analysis.html` — replace template

### No changes needed
- `langgraph_pipeline/web/server.py` — already registers `analysis_router`
- `langgraph_pipeline/web/templates/base.html` — nav already links to `/analysis`

## New Query Methods on TracingProxy

```python
def get_cost_summary() -> CostSummary
    # total cost all-time, today, this week, most expensive slug

def get_cost_by_day(days: int = 30) -> list[DailyCost]
    # [(date_str, cost_usd)] for bar chart

def list_cost_runs(
    page: int, page_size: int,
    slug: str | None, item_type: str | None,
    date_from: str | None, date_to: str | None,
    sort: str = "inclusive_desc"
) -> tuple[list[CostRun], int]
    # rows + total count; inclusive cost via recursive CTE per-row or sub-query

def get_cost_by_slug() -> list[SlugCost]
    # group by item_slug: total cost, task count, avg

def get_cost_by_node_type() -> list[NodeCost]
    # group by name (execute_task, validate_task): count, total, avg
```

## Inclusive Cost Strategy

Use a pre-computed approach: a single query computes per-run inclusive cost as the
sum of `total_cost_usd` for the run and all its descendants. For the paginated table
this is done via a correlated sub-query with a recursive CTE scoped to each row.

Since the DB has ~26k rows this is acceptable at page load time (no caching needed).

## Page Sections

1. **Summary cards** — total, today, this week, most expensive slug
2. **Cost over time** — server-rendered SVG bar chart (daily, last 30 days),
   consistent with the existing `svg_bar_chart()` helper in `cost_log_reader.py`
3. **Top runs table** — slug, node name, model, exclusive cost, inclusive cost,
   tokens (in/out), duration, timestamp; paginated 50/page; sort + filter controls
4. **Cost by work item** — aggregated table: slug, item_type, total cost, task count, avg
5. **Cost by node type** — bar chart + table: execute_task vs validate_task

## Design Decisions

- Keep `/analysis` URL (no redirect needed, nav unchanged)
- Remove dependency on `CostLogReader` from the analysis route (old class stays for
  potential future use, just not imported by the new route)
- All queries go through `TracingProxy` query methods (consistent with completions/proxy patterns)
- SVG bar chart reuse: import `svg_bar_chart` from `cost_log_reader` (it's a pure utility)
- Filters via query params: `?slug=`, `?item_type=`, `?date_from=`, `?date_to=`,
  `?sort=`, `?page=` — all GET, no JS required for basic functionality
- Tool calls with no cost show a clear note: "Cost is recorded at the agent task level only"
