# Tool-Call Cost Attribution — Design

Work item: .claude/plans/.claimed/11-tool-call-cost-attribution.md

## Architecture Overview

Add estimated cost attribution for individual tool calls (Read, Edit, Write, Bash, etc.)
to the cost analysis page. Uses Option 2 from the backlog: post-hoc estimation with no
pipeline changes.

**Data source:** `cost_tasks.tool_calls_json` stores per-tool metadata including
`result_bytes` for Read calls and `tool` name for all calls. Cost attribution is
computed proportionally in Python after fetching task rows from the DB:

```
estimated_tool_cost = (tool_result_bytes / sum_of_all_result_bytes_in_task) * task_cost_usd
```

Tasks whose tool_calls_json has no result_bytes entries produce no attributed rows.

## Data Model

The `cost_tasks` table is the data source:

```
cost_tasks.tool_calls_json  -- JSON list of {tool, file_path?, command?, result_bytes?}
cost_tasks.cost_usd         -- task total cost for proportional split
cost_tasks.item_slug        -- work item slug
cost_tasks.task_id          -- e.g. "1.1"
```

The attribution is computed in Python (not SQL) because result_bytes is buried in JSON
and proportional division requires a two-pass scan per task.

## New Components

### ToolCallCost dataclass (proxy.py)

```python
@dataclass
class ToolCallCost:
    tool_name: str
    detail: str           # file_path for Read/Edit/Write, command prefix for Bash, pattern for Grep/Glob
    result_bytes: int
    estimated_cost_usd: float
    item_slug: str
    task_id: str
```

### TracingProxy.get_tool_call_attribution() (proxy.py)

Queries all cost_tasks rows that have non-empty tool_calls_json. For each task, parses
the JSON list and computes proportional cost. Returns `list[ToolCallCost]` sorted by
estimated_cost_usd descending. Caps the return at TOP_TOOL_CALLS_LIMIT rows (constant:
250) to keep page load fast.

### Analysis page integration

Feature 10 replaces the analysis route and template. Feature 11 adds a new section to
whichever analysis page exists at execution time. The coder should read the current
`langgraph_pipeline/web/routes/analysis.py` and add:
- Call `proxy.get_tool_call_attribution()` and pass result as `tool_attribution` to template

The frontend-coder should read the current
`langgraph_pipeline/web/templates/analysis.html` and add a new section:
- "Tool Call Cost Attribution" table: tool name, detail, result KB, estimated cost
- Note: estimates are proportional; tools with no result_bytes are excluded

## Key Files

### Modify
- `langgraph_pipeline/web/proxy.py` — add ToolCallCost dataclass and
  get_tool_call_attribution() method
- `langgraph_pipeline/web/routes/analysis.py` — add tool_attribution query + pass to template
- `langgraph_pipeline/web/templates/analysis.html` — add tool attribution section

### No changes needed
- `langgraph_pipeline/web/routes/cost.py` — already stores tool_calls_json
- Pipeline executor nodes — no changes (Option 2 requires none)

## Design Decisions

- Post-hoc computation (Option 2) keeps the pipeline unchanged
- Proportional split by result_bytes is directional only; tools with no result_bytes
  (Edit, Write, non-Read tools) contribute 0 bytes and receive no cost attribution
- Cap return list at 250 rows — cost_tasks grows over time; full scan is fast but
  returning thousands of template rows is not useful
- Keep computation in Python not SQL — proportional division across a task's tool calls
  is a two-pass operation that is cleaner in Python than a correlated sub-query
- Reuse existing `cost_tasks` table — no schema changes needed
- Show a clear disclaimer: "Estimated costs based on result_bytes; tools returning no
  data are excluded. This is a proportional estimate, not exact billing."
