# Tool Call Timing and Cost Analysis UI — Design

Feature 16 | 2026-03-25

## Overview

Add a read-only `/analysis` page to the embedded web server (Feature 13) that
reads the structured JSON cost logs produced by Feature 12 from
`docs/reports/execution-costs/` and renders interactive charts and tables for
surfacing token waste patterns. No external charting library is used — SVG is
generated server-side in Python, and a minimal JavaScript file handles
expand/collapse and column sorting.

## Cost Log JSON Schema

Files are written by `write_execution_cost_log()` in
`langgraph_pipeline/shared/cost_log.py`. Each file at
`docs/reports/execution-costs/<item_slug>.json` has the shape:

```json
{
  "item_slug": "some-feature-slug",
  "item_type": "feature",
  "tasks": [
    {
      "task_id": "1.1",
      "agent_type": "coder",
      "model": "sonnet",
      "input_tokens": 12000,
      "output_tokens": 800,
      "cost_usd": 0.042,
      "duration_s": 45.3,
      "tool_calls": [
        { "tool": "Read", "file_path": "src/foo.py", "result_bytes": 3200 },
        { "tool": "Bash", "command": "pytest tests/ -v", "result_bytes": 512 }
      ]
    }
  ]
}
```

Note: the field is `duration_s` (seconds), not `duration_ms` as mentioned in
the backlog item's Requirements section. The authoritative schema is the writer
in `langgraph_pipeline/shared/cost_log.py`.

## Architecture

```
GET /analysis
      │
      ▼
routes/analysis.py
  AnalysisRouter
      │
      ├─ CostLogReader.load_all()
      │     reads docs/reports/execution-costs/*.json
      │     returns CostData with pre-computed aggregations
      │
      ├─ svg_bar_chart(items, values) → str   (server-side SVG)
      │
      └─ Jinja2TemplateResponse("analysis.html")
              ├─ top files by read volume (SVG bar chart)
              ├─ token cost by agent type (SVG bar chart)
              ├─ per-item cost table (sortable via analysis.js)
              ├─ wasted reads panel
              └─ "No data yet" message when logs absent
```

## Key Files

| File | Action |
|------|--------|
| `langgraph_pipeline/web/cost_log_reader.py` | Create — `CostLogReader`, aggregation dataclasses, `svg_bar_chart()` helper |
| `langgraph_pipeline/web/routes/analysis.py` | Create — `GET /analysis` router |
| `langgraph_pipeline/web/templates/analysis.html` | Create — Jinja2 template extending `base.html` |
| `langgraph_pipeline/web/static/analysis.js` | Create — expand/collapse row and client-side column sort |
| `langgraph_pipeline/web/server.py` | Modify — always mount the analysis router |
| `langgraph_pipeline/web/templates/base.html` | Modify — add Cost Analysis nav link |
| `tests/langgraph/web/test_cost_log_reader.py` | Create — unit tests for all aggregation functions |

## Design Decisions

**Server-side SVG** — No JS charting library required. Horizontal bar charts
are generated as inline SVG strings in Python and embedded directly in the
template. This satisfies the no-build-step constraint from Feature 15 and
keeps the charts readable in terminal browsers.

**Always-on route** — Unlike the `/proxy` router which is conditional on
`web.proxy.enabled`, the `/analysis` route is always mounted. It reads
local files only, has no external dependencies, and returns a friendly
"No data yet" page when the log directory is empty or absent.

**On-demand aggregation** — `CostLogReader.load_all()` reads and aggregates
every time the page is loaded. No caching is needed for a dev tool with
infrequent access.

**Aggregations**

| Name | Logic |
|------|-------|
| Top files by read volume | Sum `result_bytes` for `Read` tool calls grouped by `file_path`. Top 20 by bytes. |
| Token cost by agent type | Sum `input_tokens + output_tokens` grouped by `agent_type`. |
| Cost by item | Total `cost_usd` per item slug, descending. |
| Wasted reads | Any `file_path` appearing in `Read` calls across 2+ distinct tasks within the same item. |
| Duration histogram | Bucket `duration_s` per `tool` type (0-1s, 1-5s, 5-30s, 30s+). Only when `duration_s` is present on tool call records — the current schema does not include per-tool-call duration, so this chart is omitted until the schema is extended. |

**Duration histogram note** — The backlog requires a per-tool-call duration
histogram keyed on `duration_ms`. The current schema attaches `duration_s` at
the task level, not the tool call level. This chart section renders a helpful
note explaining the field is not yet available, rather than silently omitting
the panel.

**Filtering** — clicking an agent type in the token cost chart filters the
per-item table. This is implemented with a `?agent=` query parameter so the
filter survives page refresh and works in terminal browsers without JavaScript.
The `analysis.js` file additionally supports client-side column sorting and
expand/collapse of per-task rows.

**File path display** — file paths are truncated to the last 3 components
in chart labels. Full path appears in a `<title>` attribute (tooltip).
