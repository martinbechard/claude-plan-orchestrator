# Design: 80 Executor Silent Deadlock On Blocked Tasks

Source: tmp/plans/.claimed/80-executor-silent-deadlock-on-blocked-tasks.md
Requirements: docs/plans/2026-03-30-80-executor-silent-deadlock-on-blocked-tasks-requirements.md

## Architecture Overview

The executor subgraph's find_next_task node (langgraph_pipeline/executor/nodes/task_selector.py)
already detects deadlock -- when pending tasks exist but none have satisfied dependencies --
and logs a message. However, it signals deadlock identically to normal completion: by
returning current_task_id=None with no distinguishing marker. The executor graph routes
to END, execute_plan maps cost/tokens back to PipelineState, and the pipeline archives
the item as success because there is no signal that execution was incomplete.

The fix introduces a deadlock_detected boolean in TaskState that find_next_task sets when
it encounters the deadlock condition. This signal propagates through execute_plan back to
PipelineState, where route_after_execution can detect it and route appropriately. The
deadlock report includes blocked task IDs and their unsatisfied dependencies via both
structured logging and a warning-level log message.

Relationship to defect #78: That defect adds a safety net at the archival layer (refusing
to archive as success when tasks are pending). This defect (#80) fixes the root cause --
the executor explicitly signals deadlock so the pipeline can distinguish it from completion
before reaching archival. These are complementary: #78 is a catch-all gate, #80 is proper
signal propagation.

## Key Files

- MODIFY: langgraph_pipeline/executor/nodes/task_selector.py -- return deadlock signal
  with blocked task details
- MODIFY: langgraph_pipeline/executor/state.py -- add deadlock_detected and
  deadlock_details fields to TaskState
- MODIFY: langgraph_pipeline/pipeline/nodes/execute_plan.py -- propagate deadlock signal
  from TaskState to PipelineState
- MODIFY: langgraph_pipeline/pipeline/state.py -- add executor_deadlock field to
  PipelineState
- MODIFY: langgraph_pipeline/pipeline/edges.py -- route deadlocked items to archive
  instead of verify, log warning
- MODIFY: langgraph_pipeline/pipeline/nodes/archival.py -- handle deadlock outcome
  distinctly from success
- MODIFY: tests/langgraph/executor/nodes/test_task_selector.py -- test deadlock return
  value includes signal and details
- MODIFY: tests/langgraph/executor/test_edges.py -- test routing with deadlock state
- MODIFY: tests/langgraph/pipeline/nodes/test_execute_plan.py -- test deadlock propagation
- MODIFY: tests/langgraph/pipeline/test_edges.py -- test deadlock routing in pipeline

## Design Decisions

### D1: Deadlock detection returns distinguishable result via TaskState fields

Addresses: P1, FR1
Satisfies: AC1, AC2, AC7, AC8
Approach: Add two fields to TaskState in executor/state.py:
  - deadlock_detected: bool (default False) -- set True when find_next_task encounters
    pending tasks with no eligible next step
  - deadlock_details: Optional[list[dict]] -- each dict contains task_id, task_name, and
    unsatisfied_deps (list of dependency task IDs that are not in terminal status)

In find_next_task, the existing deadlock branch (line 265-277) is modified to:
1. Build the deadlock_details list by iterating pending tasks and computing each task's
   unsatisfied dependencies (deps not in completed_ids)
2. Return deadlock_detected=True and deadlock_details in the state dict
3. Continue returning current_task_id=None (the executor graph still routes to END)

This makes the deadlock condition distinguishable from "all completed" (where
deadlock_detected remains False) in the executor's return path.

Files: langgraph_pipeline/executor/state.py, langgraph_pipeline/executor/nodes/task_selector.py

### D2: Warning-level logging with blocked task and dependency details

Addresses: P2, FR2, FR4
Satisfies: AC3, AC4, AC9, AC10, AC13, AC14
Approach: Replace the existing print statement (line 266-268) with a proper warning-level
log message using the module logger. The warning includes:
  - Total count of blocked tasks
  - For each blocked task: task ID, task name, and list of unsatisfied dependency IDs

The existing add_trace_metadata call is enhanced to include the deadlock_details list,
making the structured trace data include blocked task IDs and unsatisfied deps.

This replaces the insufficient log at line ~268 with an actionable warning signal.

Files: langgraph_pipeline/executor/nodes/task_selector.py

### D3: Deadlock signal propagation from executor to pipeline state

Addresses: P2, FR3
Satisfies: AC3, AC4, AC11, AC12
Approach: Three-layer propagation:

1. TaskState (executor/state.py): deadlock_detected and deadlock_details fields carry
   the signal through the executor subgraph to END.

2. execute_plan node (pipeline/nodes/execute_plan.py): After executor.invoke(), read
   final_task_state["deadlock_detected"] and map it to PipelineState as
   executor_deadlock (bool). Also propagate deadlock_details as executor_deadlock_details.

3. PipelineState (pipeline/state.py): Add executor_deadlock: bool and
   executor_deadlock_details: Optional[list[dict]] fields. These are inspectable by
   downstream pipeline nodes (route_after_execution, archive).

This gives downstream nodes a programmatic way to distinguish "deadlock" from "success".

Files: langgraph_pipeline/executor/state.py, langgraph_pipeline/pipeline/nodes/execute_plan.py,
       langgraph_pipeline/pipeline/state.py

### D4: Pipeline routing handles deadlock outcome

Addresses: P3, FR3
Satisfies: AC5, AC6, AC11, AC12
Approach: Modify route_after_execution in pipeline/edges.py to check
state["executor_deadlock"]. When True, route directly to NODE_ARCHIVE (skip verification
for defects since there is nothing to verify -- tasks never ran). Log a warning with the
deadlock details.

In archival.py, modify _determine_outcome to check state["executor_deadlock"]. When True,
return a distinct outcome "deadlock" (new constant ARCHIVE_OUTCOME_DEADLOCK). Modify
_build_slack_message to handle the deadlock outcome with an error-level notification
that lists the blocked tasks.

This ensures deadlocked items are never archived as "success" and the outcome is
programmatically distinguishable.

Files: langgraph_pipeline/pipeline/edges.py, langgraph_pipeline/pipeline/nodes/archival.py

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | find_next_task returns deadlock_detected=True (distinguishable from None/False on normal completion) |
| AC2 | D1 | Deadlock branch sets deadlock_detected=True; normal completion leaves it False -- different return paths |
| AC3 | D2, D3 | Warning log emitted + deadlock_detected propagated as inspectable state field |
| AC4 | D2, D3 | Existing print replaced with logger.warning; executor_deadlock field replaces clean return |
| AC5 | D4 | _determine_outcome returns "deadlock" (not "completed") when executor_deadlock is True |
| AC6 | D4 | ARCHIVE_OUTCOME_DEADLOCK is a non-success outcome; item is not recorded as success |
| AC7 | D1 | deadlock_detected=True set when pending tasks exist but none have satisfied deps |
| AC8 | D1 | deadlock_detected boolean classifies the condition as a named deadlock state |
| AC9 | D2 | deadlock_details list includes task_id for every blocked task |
| AC10 | D2 | deadlock_details includes unsatisfied_deps for each blocked task |
| AC11 | D1, D3 | deadlock_detected is an inspectable boolean in both TaskState and PipelineState |
| AC12 | D3, D4 | route_after_execution and _determine_outcome both check executor_deadlock programmatically |
| AC13 | D2 | logger.warning() call emits warning-level message on deadlock |
| AC14 | D2 | Warning message includes blocked task IDs and their unsatisfied dependency IDs |
