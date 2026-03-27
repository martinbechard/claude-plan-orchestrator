# Cost Data Gaps in Traces — Design (#22)

## Problem

Only execute_task and validate_task nodes recorded total_cost_usd in trace
metadata. Other Claude-invoking nodes had no cost metadata, and many
execute_task rows showed 0.01 (suspected placeholder).

## Current State (Audit)

A codebase audit shows cost tracking has been added to most Claude-invoking nodes:

| Node | File | Cost Tracked | Notes |
|------|------|-------------|-------|
| execute_task | executor/nodes/task_runner.py | Yes | Extracts from result_capture |
| execute_parallel_task | executor/nodes/parallel.py | Yes | Extracts from result_capture |
| validate_task | executor/nodes/validator.py | Yes | Extracts from subprocess JSON |
| create_plan | pipeline/nodes/plan_creation.py | Yes | Uses _extract_cost_from_json_output() |
| intake_analyze | pipeline/nodes/intake.py | Yes | Accumulates from call_claude() |
| verify_fix | pipeline/nodes/verification.py | Yes | _invoke_claude() returns (text, cost) |
| Slack call_claude | slack/suspension.py | Yes | Records cost at 3 call sites |
| classify_idea | pipeline/nodes/idea_classifier.py | **No** | No JSON output, no trace metadata |

ClaudeResult in claude_cli.py defaults to 0.0 (not 0.01). The 0.01 values in
the database are likely real minimum-charge API costs.

## Remaining Gap

### idea_classifier.py

The classify_idea function invokes Claude without --output-format json, so cost
data cannot be extracted. Changes needed:

- Add --output-format json to the subprocess call
- Parse JSON response to extract total_cost_usd
- Call add_trace_metadata with node_name "classify_idea" and cost
- Handle JSON parse failures gracefully (default to 0.0)

## Key Files

- langgraph_pipeline/pipeline/nodes/idea_classifier.py — add JSON output and cost tracking
- langgraph_pipeline/shared/claude_cli.py — ClaudeResult and call_claude()
- langgraph_pipeline/pipeline/nodes/intake.py — intake_analyze cost accumulation
- langgraph_pipeline/pipeline/nodes/verification.py — verify_fix cost extraction
- langgraph_pipeline/pipeline/nodes/plan_creation.py — create_plan cost extraction
- langgraph_pipeline/executor/nodes/task_runner.py — execute_task cost recording
- langgraph_pipeline/executor/nodes/validator.py — validate_task cost recording
- langgraph_pipeline/slack/suspension.py — Slack LLM call cost recording

## Design Decisions

- Fix the remaining gap (idea_classifier) and verify all other nodes
- Any 0.01 values in the database are real minimum-charge API costs, not
  hardcoded defaults (production code uses 0.0 as fallback)
- Fix gaps inline rather than introducing new abstractions
- Keep the existing pattern: extract cost from Claude JSON output, pass to
  add_trace_metadata
