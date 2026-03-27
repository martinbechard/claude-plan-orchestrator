# Trace-Based Cost Analysis Page — Validation Design

Work item: tmp/plans/.claimed/10-trace-cost-analysis-page.md

## Status

This feature was previously implemented. The implementation includes:
- Route: langgraph_pipeline/web/routes/analysis.py (GET /analysis)
- Template: langgraph_pipeline/web/templates/analysis.html (40KB Jinja2)
- JS: langgraph_pipeline/web/static/analysis.js (expand/collapse, column sort)
- Backend: TracingProxy query methods in langgraph_pipeline/web/proxy.py
- Design doc: docs/plans/2026-03-26-10-trace-cost-analysis-page-design.md

## What Needs Validation

The backlog item is marked "Review Required". The plan must:

1. Validate each acceptance criterion from the work item against the existing code
2. Fix any gaps found during validation
3. Write E2E tests (tests/e2e/ currently empty, Playwright config exists)

## Architecture Overview

The cost analysis page is a server-rendered FastAPI page using Jinja2 templates:

- **Data source**: traces table in SQLite (metadata_json fields via json_extract)
- **Query layer**: TracingProxy methods (get_cost_summary, get_cost_by_day, list_cost_runs, etc.)
- **Rendering**: Server-side SVG bar charts via svg_bar_chart() + Jinja2 template
- **Client JS**: Expand/collapse rows, client-side column sorting for item cost table

## Key Files

### Existing (validate, fix if needed)
- langgraph_pipeline/web/routes/analysis.py — route handler
- langgraph_pipeline/web/templates/analysis.html — template
- langgraph_pipeline/web/static/analysis.js — client interactivity
- langgraph_pipeline/web/proxy.py — TracingProxy query methods

### Create
- tests/e2e/analysis.spec.ts — E2E tests for the cost analysis page

## Acceptance Criteria to Validate

From the work item, the page must answer:
1. Top cost consumers ranked by total_cost_usd
2. Per-call cost visibility (with note about tool calls having no direct cost)
3. Inclusive vs exclusive cost display
4. Sorted run list with filters (time range, slug)
5. Cost over time visualization

Page sections required:
1. Summary cards (total, today, this week, most expensive)
2. Cost over time chart (SVG bar chart)
3. Top runs table (sortable, filterable, paginated)
4. Cost by work item (aggregated, expandable)
5. Cost by agent/node type (chart + table)

## Design Decisions

- Reuse existing implementation — do not rewrite from scratch
- E2E tests use Playwright against running server (port 7070)
- Validation focuses on checking existing code against acceptance criteria
