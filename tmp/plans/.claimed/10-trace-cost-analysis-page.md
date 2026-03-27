# Trace-based cost analysis page

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: High

## Summary

Build a comprehensive cost analysis page powered by the trace data in the
SQLite DB. The current /analysis page uses the cost_tasks table which only
has fake test data. The traces table already has real cost data embedded in
metadata_json for execute_task and validate_task runs (1129 rows with
total_cost_usd > 0, totalling ~$56 across those nodes).

## Available Data (from DB investigation)

- 26,404 total traces; 1,555 have cost/token fields in metadata_json
- Fields available in metadata_json for cost-bearing runs:
  total_cost_usd, input_tokens, output_tokens, duration_ms,
  tool_calls_count, model, task_id, item_slug (980 traces), item_type
- Cost-bearing run types: execute_task (~$39.60 total), validate_task (~$16.84)
- Tool calls (Read, Bash, Edit, Write, etc.) have NO cost data in their
  metadata — cost is only recorded at the parent execute_task/validate_task
  level
- parent_run_id links children to parents for inclusive cost rollup

## Questions This Page Must Answer

1. **Top cost consumers**: What sub-runs consume the most quota? Rank by
   total_cost_usd across all traces or within a time window.
2. **Per-call cost**: How much does a particular LLM call or tool call cost?
   (Tool calls have no direct cost — cost is only at the agent task level.
   The page should show this clearly.)
3. **Inclusive vs exclusive cost**: For a given run, what is the total cost
   including all descendant sub-runs vs the run's own cost only?
4. **Sorted run list**: Most expensive runs sorted by inclusive or exclusive
   cost, with filters by time range and work item slug.
5. **Cost over time**: Visualization of cost by time period (daily/hourly
   bar chart or line chart).

## Page Design

### URL: /cost-analysis (or replace existing /analysis)

### Sections

**1. Summary cards (top bar)**
- Total cost (all time)
- Cost today / this week
- Average cost per work item
- Most expensive item

**2. Cost over time chart**
- SVG or JS bar chart: cost aggregated by day (or hour if zoomed in)
- Clickable bars to filter the table below to that time period

**3. Top runs by cost (sortable table)**
- Columns: slug, item_type, run name (node), model, exclusive cost,
  inclusive cost, tokens (in/out), duration, timestamp
- Sort by exclusive or inclusive cost (default: inclusive desc)
- Filter: date range picker, slug substring, item_type dropdown
- Pagination (50 per page)
- Inclusive cost = run's own cost + SUM of all descendant costs
  (requires recursive CTE or pre-computation)

**4. Cost by work item (aggregated view)**
- Group all runs by item_slug
- Show total cost, task count, avg cost per task
- Expandable rows showing per-task breakdown

**5. Cost by agent/node type**
- Bar chart: execute_task vs validate_task vs other
- Table: node name, count, total cost, avg cost

## Implementation Notes

### Cost extraction from metadata_json

Use json_extract() in SQLite:
    json_extract(metadata_json, '$.total_cost_usd')
    json_extract(metadata_json, '$.input_tokens')
    json_extract(metadata_json, '$.item_slug')

### Inclusive cost computation

Option A: Recursive CTE at query time (slow for large datasets):
    WITH RECURSIVE descendants AS (
      SELECT run_id, total_cost FROM traces WHERE run_id = ?
      UNION ALL
      SELECT t.run_id, t.total_cost FROM traces t
      JOIN descendants d ON t.parent_run_id = d.run_id
    )
    SELECT SUM(total_cost) FROM descendants;

Option B: Pre-compute inclusive_cost_usd column via a background job or
on-write trigger. Better for large tables.

### Gap: tool-level cost data

Tool calls (Read, Edit, Bash, etc.) have no cost metadata. They are free
operations from an API perspective — the cost is in the LLM tokens consumed
by the parent agent run. The page should make this clear rather than showing
$0.00 for every tool call.

### Relationship to existing /analysis page

The existing /analysis page reads from the cost_tasks table which has only
fake data. This new page should either:
- Replace /analysis entirely (rename route)
- Or coexist as /cost-analysis with a migration plan to retire /analysis

Recommendation: replace /analysis, since cost_tasks has no real data and
the trace-based approach is strictly better.

## Data Gaps to Log as Separate Enhancements

Based on the investigation, the following gaps need separate backlog items:

1. Tool calls have no cost attribution — cannot answer "how much does a
   Read call cost?" at the individual call level
2. Only execute_task and validate_task record costs — other nodes
   (create_plan, intake_analyze, verify_symptoms) that spawn Claude
   sessions may not be recording cost
3. Many traces have total_cost_usd = 0.01 (looks like a default/dummy
   value) — data quality issue
4. No cost data for Slack intake LLM calls (call_claude in suspension.py)

## LangSmith Trace: b254a65e-9ee1-47f9-b1dd-eb20dd7b81ce


## 5 Whys Analysis

Title: Replace fake test data with real trace-based cost analysis visibility

Clarity: 4 (Detailed specification with data, design, and implementation notes; underlying urgency reasoning could be more explicit)

5 Whys:

1. Why is this feature being requested?
   - The current `/analysis` page displays only fake test data from the `cost_tasks` table, but the team now has real cost data embedded in the `traces` table (~$56 across 1,129 cost-bearing operations) that could provide genuine insight into actual API spending.

2. Why is having real cost data more valuable than working with fake data?
   - Without real data, the team cannot see actual spending patterns across different operation types (execute_task, validate_task, tool calls, etc.), making it impossible to understand where budget is going or identify inefficiencies.

3. Why does identifying cost patterns matter as a High-priority item right now?
   - The system is actively accumulating costs (~$39.60 from execute_task, ~$16.84 from validate_task) across a complex hierarchy of operations, and the team has no visibility into which operations are most expensive or which work items consume disproportionate budget.

4. Why is manual cost analysis insufficient without a dedicated tool?
   - The cost attribution is nested (parent runs roll up child costs, tool calls have no direct cost, only their parent LLM call has cost), making it impossible to manually drill down and answer questions like "which work item was most expensive?" or "which operation type costs the most on average?"

5. Why is surfacing these cost patterns critical to prioritize now, during development?
   - Early visibility into cost hotspots allows the team to make architectural decisions (which operations to optimize, which to refactor) while the system is still in development, preventing expensive mistakes or runaway costs when scaling.

Root Need: To establish cost visibility during active development so the team can make proactive architectural decisions rather than discovering cost problems only after scaling.

Summary: The team needs a working cost analysis tool to understand API spending patterns and optimize expensive operations before the system scales.
