# Design: 73 Three State Task Lifecycle

Source: tmp/plans/.claimed/73-three-state-task-lifecycle.md
Requirements: docs/plans/2026-03-28-73-three-state-task-lifecycle-requirements.md
Date: 2026-03-28

## Architecture Overview

The plan task lifecycle currently conflates execution completion with validation
completion. Both events map to the "completed" status, creating ambiguity in
dependency checking and crash recovery. This design introduces a "verified"
terminal success state that separates the two events.

The change touches files across three subsystems:

1. **Executor subsystem** (task lifecycle engine):
   - state.py -- TaskStatus type definition + effective_status helper
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
| langgraph_pipeline/executor/nodes/task_selector.py | Modify | Use "verified" for dependency satisfaction via effective_status |
| langgraph_pipeline/executor/nodes/task_runner.py | Modify | Keep "completed" after execution; set "verified" when validation not configured |
| langgraph_pipeline/executor/nodes/validator.py | Modify | Advance to "verified" on PASS/WARN verdict |
| langgraph_pipeline/executor/nodes/parallel.py | Modify | Update terminal statuses for dependency resolution |
| langgraph_pipeline/executor/edges.py | Modify | Count "verified" (via effective_status) as done in progress string |
| langgraph_pipeline/pipeline/nodes/execute_plan.py | Modify | Include "verified" in terminal status set |
| langgraph_pipeline/pipeline/nodes/scan.py | Modify | Recognize "verified" as completed for plan detection |
| langgraph_pipeline/web/static/dashboard.js | Modify | Render completed vs verified visual distinction |
| langgraph_pipeline/web/static/style.css | Modify | Status-specific CSS classes for six states |
| langgraph_pipeline/web/templates/dashboard.html | Modify | Template conditionals for six states |

## Design Decisions

### D1: Extend TaskStatus with "verified" state

Addresses: P1, P2, FR1
Satisfies: AC1, AC2, AC7, AC8, AC9

Approach: Add "verified" to the TaskStatus Literal in executor/state.py, making
it the sixth valid value alongside pending, in_progress, completed, failed, and
skipped. The semantic meaning of each state:

- pending: not started (unchanged)
- in_progress: currently executing (unchanged)
- completed: code/agent finished successfully, awaiting validation (redefined)
- verified: validation passed or validation not configured (new)
- failed: execution or validation failed (unchanged)
- skipped: deliberately skipped (unchanged)

The type definition provides separate, distinguishable states for "execution
finished" (completed) and "validation passed" (verified), allowing developers
to unambiguously determine task validation status from the status value alone.

Files: langgraph_pipeline/executor/state.py

### D2: Backward-compatible effective_status helper

Addresses: FR5
Satisfies: AC18, AC19, AC20

Approach: Add an effective_status(task, validation_meta) function to state.py
that returns the effective status for dependency checking and progress counting.
For a task with status "completed", it returns "verified" when:

1. Validation is not enabled for the plan, OR
2. The task agent is not in the validation run_after list, OR
3. The task has already been through validation (validation_attempts > 0)

This is a pure read-time transformation. It never mutates the stored status
value in the plan YAML. Callers in task_selector.py, parallel.py, edges.py,
and execute_plan.py use effective_status instead of reading task["status"]
directly for dependency/progress decisions.

The backward-compatibility logic only applies to tasks that have "completed"
status -- new tasks that go through the full lifecycle will have their status
explicitly set to "verified" by the validator (D3), so the effective_status
helper does not mask genuinely incomplete validation for new tasks.

Files: langgraph_pipeline/executor/state.py

### D3: Two-phase task completion in task_runner and validator

Addresses: FR3, P2
Satisfies: AC3, AC4, AC13, AC14, AC15

Approach: The task runner continues to set status = "completed" after successful
execution. The validator node, upon a PASS or WARN verdict, advances the status
from "completed" to "verified" and persists to YAML. This creates two distinct
transitions reflecting two distinct events:

  in_progress -> completed (execution success) -> verified (validation success)

For tasks where validation is not configured (agent not in run_after, or
validation disabled), the validator already skips with PASS. The validator node
will additionally set status to "verified" before returning when it skips due
to validation not being applicable. This ensures all successfully-executed tasks
reach "verified" status regardless of validation configuration.

After a crash where execution succeeded but validation did not run, the task
status will be "completed" (not "verified"), clearly indicating that validation
is still pending. On crash recovery, this distinction is unambiguous from the
task status alone.

If validation fails after execution succeeds, the validator sets the status to
"failed", keeping the task in a non-verified state.

Files: langgraph_pipeline/executor/nodes/task_runner.py,
       langgraph_pipeline/executor/nodes/validator.py

### D4: Verified-based dependency satisfaction in task selector

Addresses: FR2, P3
Satisfies: AC5, AC6, AC10, AC11, AC12

Approach: Change TERMINAL_STATUSES in task_selector.py from
{"completed", "failed", "skipped"} to {"verified", "failed", "skipped"}.
The _completed_task_ids function (which determines dependency satisfaction)
will use effective_status(task, validation_meta) instead of raw task status,
so that both new "verified" tasks and backward-compatible legacy "completed"
tasks satisfy dependencies.

A task in "completed" status (awaiting validation) does NOT satisfy dependencies.
Dependent tasks remain blocked until the predecessor reaches "verified" (or is
treated as "verified" via effective_status for backward compatibility).

The same change applies to _TERMINAL_STATUSES in parallel.py for parallel
group dependency resolution.

Files: langgraph_pipeline/executor/nodes/task_selector.py,
       langgraph_pipeline/executor/nodes/parallel.py

### D5: Progress counting with verified-as-done

Addresses: FR4 (backend)
Satisfies: AC16, AC17

Approach: Update _tasks_completed_str in edges.py to count "verified" (via
effective_status) as done instead of "completed". Update _TERMINAL_STATUSES
in execute_plan.py to include "verified". Update scan.py to recognize "verified"
alongside "completed" when detecting in-progress plans.

The dashboard progress bar and completion counts will reflect only tasks that
have fully passed validation (or are backward-compatible legacy completed tasks),
excluding tasks that are merely awaiting validation.

Files: langgraph_pipeline/executor/edges.py,
       langgraph_pipeline/pipeline/nodes/execute_plan.py,
       langgraph_pipeline/pipeline/nodes/scan.py

### D6: Dashboard visual distinction for completed vs verified

Addresses: FR4 (UI)
Satisfies: AC16, AC17

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
| AC1 | D1 | "verified" added to TaskStatus provides separate state for validation-passed vs execution-finished |
| AC2 | D1 | Developer checks status == "verified" vs "completed" to determine if validation has run |
| AC3 | D1, D3 | After crash, task stays "completed" (awaiting validation); "verified" means fully done |
| AC4 | D1, D3 | "completed" unambiguously means execution done but validation pending |
| AC5 | D4 | Task selector uses effective_status to distinguish awaiting-validation from passed-validation |
| AC6 | D4 | Dependents blocked until predecessor reaches "verified" (via effective_status) |
| AC7 | D1 | Six states defined in TaskStatus Literal: pending, in_progress, completed, verified, failed, skipped |
| AC8 | D1 | "completed" redefined as intermediate state: execution succeeded, awaiting validation |
| AC9 | D1 | "verified" defined as terminal success: validation passed or not required |
| AC10 | D4 | TERMINAL_STATUSES changed to {"verified", "failed", "skipped"}; selector requires "verified" |
| AC11 | D4 | "completed" not in TERMINAL_STATUSES; dependents blocked until "verified" |
| AC12 | D4 | "verified" in TERMINAL_STATUSES satisfies all downstream dependency checks |
| AC13 | D3 | Task runner sets "completed" after successful execution (unchanged behavior) |
| AC14 | D3 | Validator advances "completed" to "verified" on PASS/WARN verdict |
| AC15 | D3 | Validation failure sets "failed"; task remains non-verified |
| AC16 | D5, D6 | Backend: edges.py counts effective_status "verified" as done; Frontend: visual green checkmark |
| AC17 | D5, D6 | Backend: "completed" excluded from done count; Frontend: amber/pending visual for "completed" |
| AC18 | D2 | effective_status returns "verified" for legacy completed tasks when validation not configured |
| AC19 | D2 | Legacy plans work via effective_status read-time transformation; no YAML mutation needed |
| AC20 | D2 | effective_status only applies backward-compat for completed tasks; new tasks go through full lifecycle |

---

## D6 Design Competition Results

Three designs competed for the dashboard visual differentiation approach (D6):

| Design | Alignment | Completeness | Feasibility | Integration | Clarity | Total |
|--------|-----------|--------------|-------------|-------------|---------|-------|
| Design 1 - Systems Architecture | 4 | 5 | 9 | 9 | 6 | 33 |
| Design 2 - UX Design | 9 | 8 | 7 | 8 | 8 | 40 |
| Design 3 - Frontend Implementation | 9 | 9 | 10 | 9 | 9 | 46 |

**Winner: Design 3 - Frontend Implementation** (46/50)

Design 3 provides production-ready code for all six-state visual differentiation:
amber timer icon for completed, green checkmark for verified, stacked progress bar
with legend, and progress counter counting only verified as done. All changes are
scoped to item.html.

Improvements incorporated from runner-ups:
1. Descriptive aria-labels from UX Design ("Completed, awaiting validation")
2. In-progress spinner animation from UX Design (with reduced-motion support)
3. Dual-path divergence testing strategy from Systems Design

Full judgment: tmp/worker-output/73-three-state-task-lifecycle-judgment.md
