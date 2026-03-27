# Defect 27: Tool Call Cost Attribution Dummy Data — Design

Work item: tmp/plans/.claimed/27-tool-call-cost-attribution-dummy-data.md

## Problem

The tool call cost attribution section on the cost analysis page was showing dummy
placeholder data instead of real pipeline costs. A prior implementation attempt
addressed this and the item is marked "Review Required".

## Current State (Prior Implementation)

The prior attempt wired up the full data pipeline:

1. ToolCallRecord in claude_cli.py captures result_bytes from tool outputs (line 362)
2. task_runner.py and validator.py both POST cost data via _post_cost_to_api() with
   tool call dicts including result_bytes
3. TracingProxy.get_tool_call_attribution() reads cost_tasks rows, distributes cost
   proportionally by result_bytes, returns ToolCallCost list
4. analysis.html renders the attribution table from real data

## Remaining Issue

The test fixture in test_cost_log_reader.py (client_with_proxy fixture, line 455)
mocks all proxy methods except get_tool_call_attribution(). This means the /analysis
endpoint test passes a MagicMock instead of a list to the template. The fixture needs
to mock this method with an empty list or valid ToolCallCost instances.

## Plan

Single verification-and-fix task: the coder agent reads the work item, checks the
existing implementation against acceptance criteria, adds the missing test mock, and
fixes any other gaps found during review.

## Key Files

- langgraph_pipeline/shared/claude_cli.py — ToolCallRecord.result_bytes capture
- langgraph_pipeline/executor/nodes/task_runner.py — _post_cost_to_api wiring
- langgraph_pipeline/executor/nodes/validator.py — same wiring
- langgraph_pipeline/web/proxy.py — get_tool_call_attribution() query + proportional calc
- langgraph_pipeline/web/templates/analysis.html — attribution table rendering
- tests/langgraph/web/test_cost_log_reader.py — missing mock for get_tool_call_attribution
