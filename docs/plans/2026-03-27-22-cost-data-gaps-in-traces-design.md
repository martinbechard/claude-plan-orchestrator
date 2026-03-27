---
title: Cost Data Gaps in Traces — Design (Review Pass)
date: 2026-03-27
defect: 22
---

# Cost Data Gaps in Traces — Design (Review Pass)

## Problem

This item was previously implemented and marked complete. The original defect
reported that only execute_task and validate_task nodes recorded total_cost_usd,
and that many execute_task rows showed 0.01 (suspected placeholder).

A codebase audit shows cost tracking has been added to all Claude-invoking nodes:
- execute_task (task_runner.py) — extracts from result_capture
- validate_task (validator.py) — extracts from result_capture
- create_plan (plan_creation.py) — uses _extract_cost_from_json_output()
- intake_analyze (intake.py) — accumulates cost from multiple call_claude() calls
- verify_fix (verification.py) — _invoke_claude() returns (text, cost) tuple
- suspension.py — answer_question, intake_analysis, dedup_check all record cost

ClaudeResult in claude_cli.py includes total_cost_usd extracted from JSON output.
Default fallback values are 0.0 (not 0.01).

## Scope of Review

Since the implementation appears complete, the task is to:

1. Verify all cost recording paths work end-to-end by reading the code
2. Confirm no remaining 0.01 hardcoded defaults exist in production code
3. Check that add_trace_metadata calls include total_cost_usd in all nodes
4. Validate that call_claude() in claude_cli.py correctly parses cost from JSON
5. Fix any gaps found during verification

## Key Files

- langgraph_pipeline/shared/claude_cli.py — ClaudeResult and call_claude()
- langgraph_pipeline/pipeline/nodes/intake.py — intake_analyze cost accumulation
- langgraph_pipeline/pipeline/nodes/verification.py — verify_fix cost extraction
- langgraph_pipeline/pipeline/nodes/plan_creation.py — create_plan cost extraction
- langgraph_pipeline/executor/nodes/task_runner.py — execute_task cost recording
- langgraph_pipeline/executor/nodes/validator.py — validate_task cost recording
- langgraph_pipeline/slack/suspension.py — Slack LLM call cost recording

## Design Decisions

- This is a verification pass, not a rewrite. The coder should read existing code
  and confirm correctness before making changes.
- Any 0.01 values in the database are likely real minimum-charge API costs, not
  hardcoded defaults (production code uses 0.0 as fallback).
- If gaps are found, fix them inline rather than introducing new abstractions.
