# Design: Capture Agent Traces Per Item for Review

**Work Item:** `.claude/plans/.claimed/43-capture-agent-traces-per-item-for-review.md`
**Date:** 2026-03-26

## Problem

When a pipeline agent makes a bad design decision there is no human-readable
record of the reasoning. The LangSmith traces track node execution timings but
not which skills were invoked or why a particular design was chosen.

## Architecture Overview

Write a Markdown trace file to `docs/reports/item-traces/<slug>.md` after each
task execution. The file is created on the first task and each subsequent task
appends its section. A final summary is appended during archival.

Data is sourced from what task_runner.py already has available:
- **Model**: `model_cli_name` passed into `_run_claude()`
- **Skill invocations**: `ToolCallRecord` list filtered for `tool_name == "Skill"`
- **Cost / tokens**: parsed from `result_capture` after `_run_claude()` returns
- **Task metadata**: task id, name, agent from the plan YAML

The slug is derived from `plan_path` (strip directory and `.yaml` suffix), so
no new state fields are needed.

## Key Files

| File | Action |
|------|--------|
| `langgraph_pipeline/shared/item_trace.py` | New — `ItemTraceWriter` class |
| `langgraph_pipeline/executor/nodes/task_runner.py` | Modified — call trace writer after each task |
| `langgraph_pipeline/pipeline/nodes/archival.py` | Modified — finalize trace file on archive |
| `docs/reports/item-traces/` | New directory (created by code) |

## ItemTraceWriter API

```python
class ItemTraceWriter:
    def __init__(self, slug: str, item_path: str) -> None: ...

    def record_task(
        self,
        task_id: str,
        task_name: str,
        agent: str,
        model: str,
        tool_calls: list[ToolCallRecord],
        cost_usd: float,
        input_tokens: int,
        output_tokens: int,
        status: str,
        duration_s: float,
    ) -> None: ...

    def finalize(self, outcome: str) -> None: ...
```

`record_task()` extracts Skill tool calls via:
```python
skills = [tc["tool_input"].get("skill", "") for tc in tool_calls if tc["tool_name"] == "Skill"]
```

## Trace File Format (Markdown)

```markdown
# Agent Trace: <slug>

**Item:** <item_path>
**Generated:** <ISO timestamp>

---

## Task 1.1 — <task name>

- **Agent:** coder
- **Model:** claude-sonnet-4-6
- **Status:** completed
- **Duration:** 42.1 s
- **Cost:** $0.0312  |  Input: 8 420 tok  |  Output: 1 230 tok
- **Skills invoked:** frontend-design

---

## Summary

| Task | Agent | Model | Skills | Status | Cost |
|------|-------|-------|--------|--------|------|
| 1.1  | coder | sonnet | frontend-design | completed | $0.0312 |

**Outcome:** archived
```

## Design Decisions

- **Markdown over JSON**: Acceptance criteria require human readability.
- **Append-per-task**: Writing incrementally means partial traces exist even if
  the pipeline crashes before archival.
- **Derive slug from plan_path**: Avoids threading a new field through `TaskState`.
- **docs/reports/item-traces/**: Consistent with the requested location in the work item; separate from LangSmith.
