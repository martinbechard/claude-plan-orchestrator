# Design: 77 Parallel Tasks Not Validated Before Dependents

Source defect: tmp/plans/.claimed/77-parallel-tasks-not-validated-before-dependents.md
Requirements: docs/plans/2026-03-30-77-parallel-tasks-not-validated-before-dependents-requirements.md

## Architecture Overview

The executor has two task execution paths:

- **Single tasks**: find_next_task -> execute_task -> validate_task -> find_next_task
- **Parallel tasks**: find_next_task -> fan_out -> execute_parallel_task (xN) -> fan_in -> find_next_task

The parallel path completely skips the validate_task node. After fan_in, tasks remain
in "completed" status (never promoted to "verified"). The existing effective_status()
function correctly blocks dependents from seeing unvalidated tasks as done, but since
validation never runs for parallel tasks, the block becomes permanent -- a deadlock.

The fix introduces a validation-priority check in find_next_task and a new routing
edge so that unvalidated parallel tasks are routed to the existing validate_task node
before any new work is selected.

### Revised graph topology (new edge marked with **)

```
find_next_task --[all_done]--------------> END
find_next_task --[needs_validation]------> validate_task    **NEW**
find_next_task --[single_task]-----------> execute_task
find_next_task --[parallel_group]--------> fan_out -> execute_parallel_task -> fan_in -> find_next_task
execute_task   --[circuit_break]---------> END
execute_task   --[continue]--------------> validate_task
validate_task  --[pass/fail]-------------> find_next_task
validate_task  --[retry]-----------------> escalate -> execute_task
```

## Key Files to Modify

| File | Change |
|---|---|
| langgraph_pipeline/executor/nodes/task_selector.py | Add validation-pending scan before pending-task scan |
| langgraph_pipeline/executor/edges.py | Add ROUTE_NEEDS_VALIDATION constant and routing logic |
| langgraph_pipeline/executor/graph.py | Wire new ROUTE_NEEDS_VALIDATION -> validate_task edge |
| tests/langgraph/executor/nodes/test_task_selector.py | Tests for validation-pending detection |
| tests/langgraph/executor/test_edges.py | Tests for new routing path |

## Design Decisions

### D1: Validation-pending task detection in find_next_task

Addresses: P1, FR1
Satisfies: AC1, AC2, AC3, AC7, AC8
Approach: In find_next_task, before scanning for pending tasks, scan all tasks for those
with status="completed", agent in the run_after list, and validation_attempts==0. If any
are found, return the first one as current_task_id. This ensures validation-pending tasks
from completed parallel groups are picked up before any new work is selected. The scan
uses the same plan_data and validation_meta already loaded, so no new I/O is needed.

Files:
- langgraph_pipeline/executor/nodes/task_selector.py (modify find_next_task)
- tests/langgraph/executor/nodes/test_task_selector.py (add tests)

### D2: New routing edge from find_next_task to validate_task

Addresses: P1, P2, FR1
Satisfies: AC1, AC2, AC4, AC5, AC6, AC7, AC8, AC9, AC10
Approach: Add a ROUTE_NEEDS_VALIDATION constant to edges.py. Modify parallel_check() to
detect when the selected current task has status="completed" (indicating it was selected
for validation, not execution) and return ROUTE_NEEDS_VALIDATION. Update
_route_after_find_next_task() in graph.py to map ROUTE_NEEDS_VALIDATION to
NODE_VALIDATE_TASK. This reuses the existing validate_task node (satisfying AC10) and
the existing retry_check routing back to find_next_task, so the full validation +
retry cycle works for parallel tasks identically to single tasks.

After validation completes:
- PASS/WARN: task status -> "verified", retry_check routes to find_next_task, which
  can now see the dependency as satisfied (AC9)
- FAIL + retries: retry_check routes to escalate -> execute_task for re-execution
  in the main working directory, followed by the normal validate_task cycle

Files:
- langgraph_pipeline/executor/edges.py (add constant + modify parallel_check)
- langgraph_pipeline/executor/graph.py (wire new route)
- tests/langgraph/executor/test_edges.py (add tests)

### D3: FR2 already satisfied by existing effective_status()

Addresses: FR2
Satisfies: AC11, AC12, AC13
Approach: No code changes needed. The existing effective_status() in state.py already
implements the correct status contract:
- For tasks with status="completed" + agent in run_after + validation_attempts==0:
  returns "completed" (non-terminal), so dependents remain blocked (AC11, AC13)
- For tasks with status="completed" + agent NOT in run_after: returns "verified"
  (terminal), so dependents can proceed (AC12)
- For tasks with status="completed" + validation not enabled: returns "verified" (AC12)

The _completed_task_ids() helpers in both task_selector.py and parallel.py already use
effective_status() to build the dependency-satisfied set, so they correctly exclude
unvalidated tasks. This design decision is a verification point confirming that the
dependency-evaluation layer already enforces the validation contract once D1+D2 ensure
that validation actually runs.

Files: None (verification only)

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1, D2 | find_next_task detects unvalidated parallel tasks; routes to validate_task before selecting other work |
| AC2 | D1, D2 | Unvalidated task selected as current_task_id; routed to validate_task which invokes validation |
| AC3 | D1 | find_next_task consults validation run_after list in the new scan before pending-task scan |
| AC4 | D2 | New routing path ensures validation runs, preventing permanent deadlock |
| AC5 | D2 | In the reproduction scenario, task 0.3 gets validated after fan_in, then 0.4 becomes ready |
| AC6 | D1, D2 | find_next_task always checks for unvalidated tasks first, even if it previously moved to other sections |
| AC7 | D1, D2 | Validation-pending scan runs before pending-task scan, scheduling validation immediately |
| AC8 | D1, D2 | Validation-pending tasks are checked first, taking priority over independent tasks in other sections |
| AC9 | D2 | After validate_task promotes to "verified", effective_status returns terminal status for dependents |
| AC10 | D2 | Route goes to the existing validate_task node; no new validation code path |
| AC11 | D3 | effective_status already returns "completed" for tasks needing validation, blocking dependents |
| AC12 | D3 | effective_status already returns "verified" for tasks not needing validation |
| AC13 | D3 | Dependents blocked until effective_status returns terminal status, which requires validation first |
