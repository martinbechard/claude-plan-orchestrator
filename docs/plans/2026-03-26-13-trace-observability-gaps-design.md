# Design: Trace Observability Gaps (Item 13)

## Overview

Five gaps in LangSmith trace metadata prevent diagnosing pipeline failures from
traces alone. This design adds structured metadata to executor nodes so that
subprocess failures, validator verdicts, pipeline decisions, plan state, and
invocation status are all captured in traces.

## Files to Modify

### `langgraph_pipeline/executor/nodes/task_runner.py` (Gaps 1, 5)

**`_run_claude()` signature change:**
Return a 6-tuple by adding `returncode: int` after `success`:
`(success, returncode, result_capture, stdout_text, stderr_text, tool_calls)`

- Normal exit: `returncode = process.returncode`
- Timeout: `returncode = -1`
- Exception: `returncode = -2`

**`failure_reason` derivation:**
- `returncode == 0` → `"ok"`
- Timeout → `"timeout"`
- Quota exhaustion detected (caller, not `_run_claude`) → `"quota_exhausted"`
- Otherwise → `f"exit_code_{returncode}"`

**`add_trace_metadata` additions for normal execution:**
```python
"subprocess_exit_code": returncode,
"subprocess_error": _stderr[:500] if not cli_success else "",
"failure_reason": failure_reason,
"claude_invoked": True,
```

**Early-exit cases (return `{}` or `{"quota_exhausted": True}`):**
Each must call `add_trace_metadata` with `claude_invoked=False` and a `skip_reason`:
- `task_id is None` → `skip_reason="no_current_task_id"`
- `task/section not found` → `skip_reason="task_not_found_in_plan"`
- Quota reset path → `skip_reason="quota_exhausted"` (already sets `quota_exhausted=True`)

### `langgraph_pipeline/executor/nodes/validator.py` (Gaps 1, 2)

**`_run_claude()` signature change:**
Return `(success, returncode, result_capture, stderr_text)` — same pattern as task_runner.

**`add_trace_metadata` additions:**
```python
"subprocess_exit_code": returncode,
"subprocess_error": stderr_text[:500] if not cli_success else "",
"failure_reason": failure_reason,
"findings": task.get("validation_findings", ""),
"requirements_checked": status_dict.get("requirements_checked") if status_dict else None,
"requirements_met": status_dict.get("requirements_met") if status_dict else None,
```

**Status file format update in `_build_validator_prompt()`:**
Extend the example status file to include optional fields:
```json
{
  "task_id": "...",
  "verdict": "PASS",
  "status": "completed",
  "message": "Brief summary of findings",
  "requirements_checked": 5,
  "requirements_met": 5
}
```

### `langgraph_pipeline/executor/nodes/task_selector.py` (Gap 3)

When `find_next_task` stops (returns `current_task_id=None`), add a pipeline
decision trace identifying the reason:

```python
add_trace_metadata({
    "node_name": "find_next_task",
    "decision": "stop",
    "reason": "quota_exhausted" | "circuit_open" | "budget_exceeded"
             | "no_pending_tasks" | "deadlock",
    "cycle_number": ...,
    "tasks_completed": f"{completed}/{total}",
})
```

The `completed` and `total` counts are already derivable from `all_tasks` once loaded.

### `langgraph_pipeline/pipeline/nodes/execute_plan.py` (Gap 4)

Before invoking the executor subgraph, read the plan YAML and include a task
snapshot in `add_trace_metadata`:

```python
"plan_tasks": [{"task_id": t["id"], "description": t.get("name",""), "status": t.get("status","")} ...],
"completed_count": ...,
"total_count": ...,
```

After invoking, add the final task state using `final_task_state.get("plan_data")`.

## Key Design Decisions

1. **Return code from `_run_claude`**: Both `task_runner._run_claude` and
   `validator._run_claude` are private functions. Extending their return tuple is
   the least intrusive change — no new types needed.

2. **`subprocess_error` truncated at 500 chars**: Matches the spec exactly and
   keeps LangSmith metadata lean.

3. **`requirements_checked`/`requirements_met` are validator-supplied**: The
   validator agent writes them into the status file if applicable. The node
   reads them — no schema enforcement needed. `None` when absent.

4. **Plan task snapshot uses task `name` as description**: Task descriptions
   in the YAML can be long multi-line strings. The `name` field is a concise
   label suitable for trace metadata. Full descriptions remain in the plan YAML.

5. **Decision traces in `find_next_task`**: Edge functions are pure routing and
   cannot call `add_trace_metadata`. The decision context is emitted by the
   node that makes the decision (`find_next_task`), not the edge.
