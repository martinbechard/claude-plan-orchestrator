# Defect 27: Tool Call Cost Attribution Dummy Data — Verification Design

Work item: tmp/plans/.claimed/27-tool-call-cost-attribution-dummy-data.md

## Problem

The tool call cost attribution section on the cost analysis page was showing dummy
placeholder data instead of real pipeline costs. The root cause was incomplete wiring:
the executor nodes did not POST cost data to the API, and ToolCallRecord did not capture
result_bytes from tool outputs.

## Current State

A prior implementation attempt addressed all four fix areas from the backlog item:

1. result_bytes capture added to ToolCallRecord in claude_cli.py (line 102, 321)
2. _post_cost_to_api() wired in task_runner.py (line 406) and validator.py (line 250)
3. _tool_call_to_dict() converts ToolCallRecord to API-compatible format in both nodes
4. The UI in analysis.html already renders from real data via get_tool_call_attribution()

The item is marked "Review Required" because it was previously completed without
end-to-end verification. The plan below verifies the existing implementation is correct
and fixes any remaining issues.

## Key Files

### Already Modified (verify correctness)
- langgraph_pipeline/shared/claude_cli.py — ToolCallRecord.result_bytes + capture logic
- langgraph_pipeline/executor/nodes/task_runner.py — _post_cost_to_api + _tool_call_to_dict
- langgraph_pipeline/executor/nodes/validator.py — same wiring as task_runner
- langgraph_pipeline/web/proxy.py — get_tool_call_attribution() proportional computation
- langgraph_pipeline/web/templates/analysis.html — attribution table rendering

### No Changes Expected
- langgraph_pipeline/web/routes/cost.py — POST /api/cost endpoint (already correct)
- langgraph_pipeline/web/cost_log_reader.py — aggregation reader (already correct)

## Design Decisions

- This is a verification pass, not a rewrite. The coder agent must check what exists
  before making changes, per the backlog item instructions.
- The stale "12-test-item" rows in cost_tasks are a runtime DB concern, not a code fix.
  If a DB cleanup script or migration is needed, the coder can add it.
- The proportional attribution algorithm (cost * result_bytes / sum_bytes) is the
  approved approach from Feature 11 design.
