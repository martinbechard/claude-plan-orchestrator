# Planner targets legacy script instead of LangGraph pipeline

## Status: Open

## Priority: High

## Summary

The planner agent incorrectly scoped feature 12 (structured execution cost log)
to `scripts/plan-orchestrator.py` instead of
`langgraph_pipeline/executor/nodes/task_runner.py`. The implementation was
completed correctly against the plan, but landed in dead code — the legacy script
is no longer the active execution path.

## Symptoms

- `docs/reports/execution-costs/` is never written during pipeline runs
- `scripts/plan-orchestrator.py` has `write_execution_cost_log()` and
  `ToolCallRecord`, but `langgraph_pipeline/executor/nodes/task_runner.py` does not
- Feature 12 was archived as completed; the validator PASSed all tasks because
  each task description correctly scoped to the legacy file and the implementation
  matched the scope
- The error was not catchable by per-task validation: the validator checks whether
  the implementation matches the task description, not whether the task description
  targets the correct file

## Root Cause

The planner read the feature backlog item (which referenced general concepts, not
specific files) and then chose `scripts/plan-orchestrator.py` as the target,
apparently because that file already contained the `stream_json_output()` function
and `run_claude_task()`. It did not recognise that
`langgraph_pipeline/executor/nodes/task_runner.py` is the active equivalent.

The design doc (`docs/plans/2026-03-24-12-structured-execution-cost-log-and-analysis-design.md`)
locked in this wrong target on line 8:
> "The feature adds two things to `scripts/plan-orchestrator.py`"

## Fix

1. Add `write_execution_cost_log()` and `ToolCallRecord` (result_bytes tracking) to
   `langgraph_pipeline/executor/nodes/task_runner.py` (or a new shared module
   `langgraph_pipeline/shared/cost_log.py`), mirroring what was implemented in the
   legacy script.
2. Call it from `execute_task` after `emit_tool_call_traces()`.
3. Add a note to CLAUDE.md or the planner agent instructions clarifying that
   `scripts/plan-orchestrator.py` is legacy — all new pipeline features go in
   `langgraph_pipeline/`.

## Verification Log

*(empty — no fix attempts yet)*
