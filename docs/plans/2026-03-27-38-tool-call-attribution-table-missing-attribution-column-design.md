# Design: Tool Call Cost Attribution Table - Missing Attribution Column

## Status: Review Required

This defect was previously implemented. The plan validates the existing
implementation against acceptance criteria and fixes any gaps.

## Architecture Overview

The Tool Call Cost Attribution feature spans three layers:

1. **Data collection**: POST /api/cost endpoint receives tool_calls with
   result_bytes per call, stored as JSON in cost_tasks.tool_calls_json
2. **Attribution calculation**: TracingProxy.get_tool_call_attribution()
   distributes each task cost_usd proportionally across tool calls by
   result_bytes
3. **Display**: analysis.html template renders the table with columns:
   Tool, Slug, Task, Detail, Result KB, Est. $

## Key Files

- langgraph_pipeline/web/proxy.py - get_tool_call_attribution(), ToolCallCost
- langgraph_pipeline/web/templates/analysis.html - table markup (lines 386-438)
- langgraph_pipeline/web/routes/analysis.py - passes tool_attribution to template
- langgraph_pipeline/web/routes/cost.py - POST endpoint accepting tool_calls
- tests/langgraph/web/test_cost_endpoint.py - cost endpoint tests

## Design Decisions

- **Proportional by result_bytes**: Cost is attributed proportionally to the
  bytes returned by each tool call within a task. This is a reasonable heuristic
  since larger responses correlate with more token usage.
- **Exclusion of zero-byte calls**: Tool calls returning no data get no cost
  attribution and are excluded from the table.
- **Column header "Est. $"**: Short, clear header indicating estimated dollar cost.
