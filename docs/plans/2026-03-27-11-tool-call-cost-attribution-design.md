# Tool-Call Cost Attribution — Design

Work item: tmp/plans/.claimed/11-tool-call-cost-attribution.md

## Architecture Overview

This feature provides estimated per-tool-call cost attribution on the cost analysis
page. It uses post-hoc estimation (Option 2 from backlog): no pipeline changes needed.

The implementation already exists across three layers:

1. **Data collection**: POST /api/cost stores tool_calls with result_bytes in
   cost_tasks.tool_calls_json (already working)
2. **Attribution calculation**: TracingProxy.get_tool_call_attribution() distributes
   each task's cost_usd proportionally across tool calls by result_bytes
3. **Display**: analysis.html renders a "Tool Call Cost Attribution" table with
   columns: Tool, Slug, Task, Detail, Result KB, Est. $

## Current State (Review Required)

The core implementation is complete:
- ToolCallCost dataclass in proxy.py
- get_tool_call_attribution() method with proportional cost split
- Analysis route passes tool_attribution to template
- Template renders the table with disclaimer

### Gaps to address

1. **No unit tests** for get_tool_call_attribution() or the ToolCallCost dataclass.
   The cost endpoint tests exist but do not cover the attribution query.
2. **Validation of acceptance criteria**: Verify all criteria from the backlog item
   pass against the live implementation.

## Key Files

### Existing (verify)
- langgraph_pipeline/web/proxy.py - ToolCallCost dataclass (line ~80), get_tool_call_attribution() (line ~1166)
- langgraph_pipeline/web/routes/analysis.py - passes tool_attribution (line ~102, ~139)
- langgraph_pipeline/web/templates/analysis.html - table section (lines 386-438)

### Create
- tests/langgraph/web/test_tool_call_attribution.py - unit tests for attribution logic

### No changes needed
- langgraph_pipeline/web/routes/cost.py - already stores tool_calls_json
- langgraph_pipeline/executor/nodes/task_runner.py - already collects tool calls

## Design Decisions

- Post-hoc computation keeps the pipeline unchanged
- Proportional split by result_bytes: tools with 0 result_bytes excluded
- Top 250 results returned (TOP_TOOL_CALLS_LIMIT constant)
- Computation in Python (not SQL) for clean two-pass proportional division
- Clear disclaimer on the page about estimated nature of costs
