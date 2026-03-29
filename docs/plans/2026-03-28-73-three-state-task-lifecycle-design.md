# Design: 73 Three State Task Lifecycle

Source: tmp/plans/.claimed/73-three-state-task-lifecycle.md
Requirements: docs/plans/2026-03-28-73-three-state-task-lifecycle-requirements.md
Date: 2026-03-28

## Architecture Overview

The plan task lifecycle currently conflates execution completion with validation
completion. Both events map to the "completed" status, creating ambiguity in
dependency checking and crash recovery. This design introduces a "verified"
terminal success state that separates the two events.

The change touches six files across two subsystems:

1. **Executor subsystem** (task lifecycle engine):
   - state.py -- TaskStatus type definition
   - task_selector.py -- dependency satisfaction logic
   - task_runner.py -- post-execution status transitions
   - validator.py -- post-validation status advancement
   - parallel.py -- parallel execution terminal statuses
   - edges.py -- progress counting for routing decisions

2. **Pipeline subsystem** (plan orchestration):
   - execute_plan.py -- plan snapshot terminal status counting
   - scan.py -- in-progress plan detection

3. **Dashboard subsystem** (UI):
   - dashboard.js, style.css, dashboard.html -- visual status differentiation

A backward-compatibility helper (effective_status) ensures existing plans with
"completed" tasks continue to work without mutating stored YAML values.

## Key Files to Create/Modify

| File | Action | Purpose |
|---|---|---|
| langgraph_pipeline/executor/state.py | Modify | Add "verified" to TaskStatus Literal, add effective_status helper |
| langgraph_pipeline/executor/nodes/task_selector.py | Modify | Use "verified" for dependency satisfaction |
| langgraph_pipeline/executor/nodes/task_runner.py | Modify | Set "verified" when validation not configured |
| langgraph_pipeline/executor/nodes/validator.py | Modify | Advance to "verified" on PASS/WARN |
| langgraph_pipeline/executor/nodes/parallel.py | Modify | Update terminal statuses for dependency resolution |
| langgraph_pipeline/executor/edges.py | Modify | Count "verified" as done in progress string |
| langgraph_pipeline/pipeline/nodes/execute_plan.py | Modify | Include "verified" in terminal status set |
| langgraph_pipeline/pipeline/nodes/scan.py | Modify | Recognize "verified" as completed for plan detection |
| langgraph_pipeline/web/static/dashboard.js | Modify | Render completed vs verified visual distinction |
| langgraph_pipeline/web/static/style.css | Modify | Status-specific CSS classes |
| langgraph_pipeline/web/templates/dashboard.html | Modify | Template conditionals for six states |

## Design Decisions

### D1: Extend TaskStatus with "verified" state

Addresses: P1, P2, FR1
Satisfies: AC1, AC2, AC3, AC4, AC7, AC8, AC9, AC10, AC11, AC12, AC13, AC14

Approach: Add "verified" to the TaskStatus Literal in executor/state.py, making
it the sixth valid value alongside pending, in_progress, completed, failed, and
skipped. The semantic meaning of each state:

- pending: not started (unchanged)
- in_progress: currently executing (unchanged)
- completed: code/agent finished successfully, awaiting validation (redefined)
- verified: validation passed or validation not configured (new)
- failed: execution or validation failed (unchanged)
- skipped: deliberately skipped (unchanged)

All downstream code that reads or writes task status accepts these six values.

Files: langgraph_pipeline/executor/state.py

### D2: Backward-compatible effective_status helper

Addresses: FR5
Satisfies: AC24, AC25, AC26

Approach: Add an effective_status(task, validation_meta) function to state.py
that returns the effective status for dependency checking and progress counting.
For a task with status "completed", it returns "verified" when:

1. Validation is not enabled for the plan, OR
2. The task agent is not in the validation run_after list, OR
3. The task has already been through validation (validation_attempts > 0)

This is a pure read-time transformation. It never mutates the stored status
value in the plan YAML (satisfying AC26). Callers in task_selector.py,
parallel.py, edges.py, and execute_plan.py use effective_status instead of
reading task["status"] directly for dependency/progress decisions.

Files: langgraph_pipeline/executor/state.py

### D3: Two-phase task completion in task_runner and validator

Addresses: FR3, P1, P2
Satisfies: AC19, AC20

Approach: The task runner continues to set status = "completed" after successful
execution (line 692 of task_runner.py). The validator node, upon a PASS or WARN
verdict, advances the status from "completed" to "verified" and persists to YAML.
This creates two distinct transitions reflecting two distinct events.

For tasks where validation is not configured (agent not in run_after, or
validation disabled), the validator already skips with PASS. The validator node
will additionally set status to "verified" before returning when it skips due
to validation not being applicable. This ensures all successfully-executed tasks
reach "verified" status regardless of validation configuration (satisfying AC20).

The parallel.py node uses the same logic: after a parallel task completes with
outcome "completed", the validator handles advancement to "verified".

Files: langgraph_pipeline/executor/nodes/task_runner.py,
       langgraph_pipeline/executor/nodes/validator.py

### D4: Verified-based dependency satisfaction in task selector

Addresses: FR2, P3
Satisfies: AC5, AC6, AC15, AC16, AC17, AC18

Approach: Change TERMINAL_STATUSES in task_selector.py from
{"completed", "failed", "skipped"} to {"verified", "failed", "skipped"}.
The _completed_task_ids function (which determines dependency satisfaction)
will use effective_status(task, validation_meta) instead of raw task status,
so that both new "verified" tasks and backward-compatible legacy "completed"
tasks satisfy dependencies.

A task in "completed" status (awaiting validation) does NOT satisfy dependencies.
Dependent tasks remain blocked until the predecessor reaches "verified".

The same change applies to _TERMINAL_STATUSES in parallel.py for parallel
group dependency resolution.

Files: langgraph_pipeline/executor/nodes/task_selector.py,
       langgraph_pipeline/executor/nodes/parallel.py

### D5: Progress counting with verified-as-done

Addresses: FR4 (backend)
Satisfies: AC21, AC22

Approach: Update _tasks_completed_str in edges.py to count "verified" (via
effective_status) as done instead of "completed". Update _TERMINAL_STATUSES
in execute_plan.py to include "verified". Update scan.py to recognize "verified"
alongside "completed" when detecting in-progress plans.

Files: langgraph_pipeline/executor/edges.py,
       langgraph_pipeline/pipeline/nodes/execute_plan.py,
       langgraph_pipeline/pipeline/nodes/scan.py

### D6: Dashboard visual distinction for completed vs verified

Addresses: FR4 (UI)
Satisfies: AC23

Approach: Phase 0 design competition. Three competing designs evaluate how to
visually distinguish "completed" (awaiting validation) from "verified" (fully
done) in the dashboard. The winning design drives frontend implementation tasks.

Key constraints for designers:
- Progress bar segments must differentiate all six states
- Color scheme must be accessible (WCAG 2.1 AA, color-blind safe)
- "Completed" should convey "in progress / awaiting next step" (not done)
- "Verified" should convey "fully done / green checkmark"
- Existing dashboard layout (Jinja2 templates, vanilla JS) must be preserved

Files: langgraph_pipeline/web/static/dashboard.js,
       langgraph_pipeline/web/static/style.css,
       langgraph_pipeline/web/templates/dashboard.html

---

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | "verified" added to TaskStatus separates execution-finished from validation-passed |
| AC2 | D1 | Code checks status == "verified" vs "completed" programmatically |
| AC3 | D1, D3 | "completed" means awaiting validation; "verified" means fully done |
| AC4 | D1, D3 | "completed" redefined as execution finished, awaiting validation |
| AC5 | D4 | Task selector requires "verified" via effective_status; blocks on "completed" |
| AC6 | D4 | Validation failure sets "failed"; dependents remain blocked |
| AC7 | D1 | Six states defined in TaskStatus Literal type |
| AC8 | D1 | "pending" = not started (unchanged) |
| AC9 | D1 | "in_progress" = currently executing (unchanged) |
| AC10 | D1, D3 | "completed" = execution succeeded, awaiting validation |
| AC11 | D1, D3 | "verified" = validation passed or not configured |
| AC12 | D1 | "failed" = execution or validation failed (unchanged) |
| AC13 | D1 | "skipped" = deliberately skipped (unchanged) |
| AC14 | D1 | All six states in TaskStatus Literal, accepted everywhere |
| AC15 | D4 | Task selector checks effective_status == "verified" for dependencies |
| AC16 | D4 | All predecessors "verified" (effective) -> task eligible |
| AC17 | D4 | Any predecessor "completed" (not verified) -> task blocked |
| AC18 | D4 | Only "verified" (or effective "verified") satisfies dependency requirements |
| AC19 | D3 | Task runner sets "completed"; validator advances to "verified" |
| AC20 | D3 | Validator sets "verified" when skipping non-applicable validation |
| AC21 | D5 | Progress counts "verified" (via effective_status) as done |
| AC22 | D5 | "completed" excluded from done count (only "verified" counts) |
| AC23 | D6 | Phase 0 design competition for visual distinction |
| AC24 | D2 | effective_status returns "verified" for legacy completed tasks |
| AC25 | D2, D5 | Legacy completed treated as done via effective_status in progress counting |
| AC26 | D2 | effective_status is read-only; never mutates stored YAML values |
