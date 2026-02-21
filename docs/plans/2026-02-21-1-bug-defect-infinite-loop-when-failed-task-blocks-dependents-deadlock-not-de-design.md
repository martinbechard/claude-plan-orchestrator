# Design: Detect and Halt Deadlocked Plans

## Problem

When a task fails and its dependents remain pending, the system enters an infinite
loop:

1. plan-orchestrator.py: find_next_task() returns None (pending tasks exist but are
   blocked by failed dependencies). The orchestrator treats this as "All tasks
   completed!" and exits 0.
2. auto-pipeline.py: find_in_progress_plans() sees completed + pending tasks and
   resumes the orchestrator, which exits 0 again. This repeats indefinitely.

Two scenarios cause this:
- **Failed dependency deadlock**: Task A is failed, Task B depends on A.
  check_dependencies_satisfied() requires status == "completed", so B is skipped.
- **Suspended dependency deadlock**: Similar pattern with suspended tasks blocking
  dependents.

## Architecture

### Component 1: Deadlock Detection (plan-orchestrator.py)

Add a detect_plan_deadlock() function that runs when find_next_task() returns None.

**Logic:**
1. Collect all non-terminal tasks (status in pending, in_progress).
2. If none exist, the plan is genuinely complete -- no deadlock.
3. For each non-terminal task, check if any dependency has status failed or
   suspended.
4. If ALL non-terminal tasks are blocked by failed/suspended dependencies, the plan
   is deadlocked.

**Actions on deadlock:**
- Set meta.status to "failed" in the YAML plan file.
- Log which tasks are blocked and by which failed dependencies.
- Send a Slack notification with deadlock details.
- Exit with non-zero status code.

**Key change in main loop (around line 5336):**

Replace the unconditional "All tasks completed!" with:
- If find_next_task() returns None AND non-terminal tasks exist: deadlock detected.
- If find_next_task() returns None AND no non-terminal tasks exist: genuinely complete.

### Component 2: Pipeline Deadlock Awareness (auto-pipeline.py)

**find_in_progress_plans() (line 1997):**
- After loading the YAML, check meta.status. If it is "failed", skip the plan
  (do not add it to the in_progress list).

**is_plan_fully_completed() (line 1737):**
- After loading the YAML, check meta.status. If it is "failed", return False
  (the plan is NOT "fully completed" -- it is failed).
- This prevents the pipeline from skipping Phase 2 and silently treating a
  deadlocked plan as done.

### Key Files

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Add detect_plan_deadlock(), update main loop exit logic |
| scripts/auto-pipeline.py | Update find_in_progress_plans() and is_plan_fully_completed() to check meta.status |
| tests/test_plan_orchestrator.py | Tests for deadlock detection |
| tests/test_auto_pipeline.py | Tests for meta.status handling |

### Design Decisions

1. **meta.status: "failed" as the coordination mechanism** -- The orchestrator
   writes this to the YAML, and the pipeline reads it. This follows the existing
   pattern (meta.status: "paused_quota" already exists in plan-orchestrator.py
   line 5089).

2. **Non-zero exit from orchestrator** -- Ensures execute_plan() in the pipeline
   sees a failure and does not proceed to verification.

3. **Transitive deadlock not needed initially** -- Direct dependency checking
   (is any dep failed/suspended?) is sufficient because if Task A fails, Task B
   (depends on A) stays pending, and Task C (depends on B) also stays pending.
   find_next_task() already skips both B and C since neither has satisfied deps.
   The deadlock detector only needs to confirm that at least one dep is in a
   terminal-failure state.

4. **No changes to find_next_task() itself** -- The function's current behavior
   (skip failed, check deps) is correct. The fix adds post-hoc analysis when it
   returns None.
