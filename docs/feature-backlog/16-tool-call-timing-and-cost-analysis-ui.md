# Tool call timing and cost analysis UI

## Status: Open

## Priority: Medium

## Depends On: Feature 13 (embedded web server), Feature 12 cost log writer
   (currently implemented in scripts/plan-orchestrator.py — defect 04 tracks
   porting it to langgraph_pipeline/executor/nodes/task_runner.py)

## Summary

A read-only analysis UI at `/analysis` that reads the structured cost logs
from `docs/reports/execution-costs/` and renders interactive charts and
tables to surface token waste patterns. Answers questions like "which files
are we reading most?", "which agent types cost the most?", and "which items
had the highest cost per task?".

## Motivation

Feature 12 (structured execution cost log) produces JSON files but they are
currently only consumable by the analysis pipeline agent (which posts a
one-time Slack message). The UI provides a persistent, explorable view of
the same data that improves over time as more items are processed.

## Requirements

### Data Layer

1. `CostLogReader` — reads all JSON files under `docs/reports/execution-costs/`,
   parses and aggregates on demand (no caching needed for a dev tool). Returns
   structured results for each chart.

2. Aggregations computed:
   - **Read volume by file path**: sum `result_bytes` for all `Read` tool calls
     grouped by `file_path`. Top 20 files ranked by total bytes.
   - **Token cost by agent type**: sum `input_tokens + output_tokens` grouped
     by `agent_type` across all items.
   - **Cost by item**: total `cost_usd` per item slug, ranked highest first.
   - **Repeated reads within an item**: for each item, any `file_path` appearing
     in `Read` calls across 2+ distinct tasks (wasted reads).
   - **Tool call duration histogram**: if `duration_ms` is present on tool call
     records, bucket into a histogram per tool type.

### Analysis UI (`/analysis`)

3. **Top files by read volume** — horizontal bar chart (plain SVG) with file
   paths truncated to the last 3 path components. Tooltip shows full path and
   exact bytes.

4. **Token cost by agent type** — pie or bar chart. Clicking an agent type
   filters the per-item table to only that agent.

5. **Per-item cost table** — sortable table: item slug, agent types used,
   total input tokens, total output tokens, total cost, number of tasks,
   number of wasted reads. Clicking an item expands to per-task breakdown.

6. **Wasted reads panel** — lists every intra-item repeated read with item
   slug, file path, and count. Sorted by count descending.

7. **"No data yet" state** — when `docs/reports/execution-costs/` is empty or
   absent, renders a friendly message explaining that cost logs will appear
   once the pipeline processes items with the cost log writer enabled.

### Design constraints

- Same no-build-step constraint as feature 15.
- Charts must be readable in a terminal browser (no colour-only encoding).
- SVG charts generated server-side in Python (no JS charting library required).

## Files

- `langgraph_pipeline/web/cost_log_reader.py` — `CostLogReader`, aggregation functions
- `langgraph_pipeline/web/routes/analysis.py` — FastAPI router
- `langgraph_pipeline/web/templates/analysis.html`
- `langgraph_pipeline/web/static/analysis.js` (minimal: expand/collapse, sort)
- `tests/langgraph/web/test_cost_log_reader.py`
