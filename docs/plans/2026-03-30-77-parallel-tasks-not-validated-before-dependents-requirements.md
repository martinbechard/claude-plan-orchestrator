# Structured Requirements: 77 Parallel Tasks Not Validated Before Dependents

Source: tmp/plans/.claimed/77-parallel-tasks-not-validated-before-dependents.md
Generated: 2026-03-30T16:36:48.288508+00:00

## Requirements

### P1: Executor bypasses validation of completed parallel tasks
Type: functional
Priority: high
Source clauses: [C1, C2, C4, C5, C10]
Description: When a parallel group of tasks completes in the executor, the find_next_task logic in task_selector.py does not prioritize validation of tasks that appear in the validation run_after list. Instead, it selects any available ready task, including independent tasks in other sections. In the observed case (item 74-item-page-step-explorer), tasks 0.1, 0.2, and 0.3 ran in parallel (design-phase0). Task 0.3 (agent=frontend-coder) was in the validation run_after list but was never validated (validation_attempts=0). The task selection algorithm does not consult validation run_after metadata when prioritizing the next task, so validation-pending tasks are skipped indefinitely.
Acceptance Criteria:
- After a parallel group of tasks completes, does the executor validate all tasks in the group that appear in the validation run_after list before selecting tasks from other sections? YES = pass, NO = fail
- For a task in the validation run_after list that completes as part of a parallel group, does the executor invoke validate_task before moving to other work? YES = pass, NO = fail
- Does the find_next_task logic consult the validation run_after list when prioritizing the next task to select? YES = pass, NO = fail

### P2: Permanent deadlock when dependent tasks wait on unvalidated parallel prerequisites
Type: functional
Priority: high
Source clauses: [C3, C7, C8]
Description: When a parallel group contains a task that requires validation (per run_after) but that validation is never performed, dependent tasks that require all parallel tasks to be satisfied are permanently blocked. In the observed case, task 0.4 depends on tasks 0.1, 0.2, and 0.3. Because task 0.3 remained in "completed" status (never validated to "verified"), task 0.4 was permanently blocked. The executor moved on to section 1 tasks (1.1, 1.2 which had no dependencies) and then deadlocked when it returned to evaluate 0.4, which could never become ready. The executor had no mechanism to recover from this state.
Acceptance Criteria:
- Given a task that depends on multiple parallel tasks where one requires validation, does the executor eventually validate that task and unblock the dependent? YES = pass, NO = fail
- Does the executor avoid deadlock when a dependent task's prerequisites include tasks requiring validation? YES = pass, NO = fail
- In the reproduction scenario (tasks 0.1-0.3 parallel, 0.4 dependent on all three), does task 0.4 eventually become ready and execute? YES = pass, NO = fail

### FR1: Enforce validation phase after parallel group completion before dependency evaluation
Type: functional
Priority: high
Source clauses: [C9, C10, C11]
Description: After a parallel group of tasks completes, the executor must validate each task in the group that requires validation (i.e., appears in the validation run_after list) before evaluating dependencies for the next batch of tasks. The validation phase must be enforced in the find_next_task logic (task_selector.py) by detecting pending validations and routing them to validate_task (validator.py) before selecting any new task whose dependencies include the unvalidated tasks. This ensures that tasks transition from "completed" to "verified" status before their dependents' readiness is evaluated, and that the executor does not move to independent tasks in other sections while validations remain pending for a completed parallel group.
Acceptance Criteria:
- After all tasks in a parallel group reach "completed" status, does the executor immediately schedule validation for those tasks that have validation requirements (run_after) before selecting tasks from subsequent sections? YES = pass, NO = fail
- Does the task selector prioritize pending validations from a completed parallel group over selecting new independent tasks from other sections? YES = pass, NO = fail
- After validation completes for all tasks in a parallel group, do dependent tasks correctly see their prerequisites as satisfied and become ready? YES = pass, NO = fail
- Is the validation invoked via the existing validate_task path in validator.py? YES = pass, NO = fail

### FR2: Dependency evaluation must require "verified" status for tasks with validation requirements
Type: functional
Priority: high
Source clauses: [C6, C9]
Description: When evaluating whether a task's dependencies are satisfied, the executor must distinguish between "completed" and "verified" status for tasks that have validation requirements (appear in the validation run_after list). A task that requires validation must only satisfy its dependents' dependency checks once it has reached "verified" status, not merely "completed" status. In the observed case, task 0.3's effective_status remained "completed" instead of "verified", yet the dependency check for task 0.4 did not account for this distinction, leaving 0.4 permanently blocked because the system never progressed 0.3 past "completed". This requirement ensures that even if task ordering changes or edge cases arise, the dependency resolution layer itself enforces the validation contract.
Acceptance Criteria:
- For a dependency on a task that requires validation (appears in run_after), does the dependency check require "verified" status rather than accepting "completed"? YES = pass, NO = fail
- For a dependency on a task that does NOT require validation, does the dependency check accept "completed" status as sufficient? YES = pass, NO = fail
- If a task's effective_status is "completed" but it requires validation, do dependent tasks remain blocked until validation promotes the task to "verified"? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| Title: "Parallel tasks not validated before dependents are checked" | P1 |
| Mechanism: executor moves on to independent tasks without validating | P1, FR1 |
| Consequence: creates a permanent deadlock for dependent tasks | P2 |
| Reproduction: tasks 0.1, 0.2, 0.3 ran in parallel (design-phase0) | P1, P2 |
| Reproduction: task 0.3 in run_after list, never validated (validation_attempts=0) | P1 |
| Reproduction: effective_status remained "completed" instead of "verified" | FR2 |
| Reproduction: task 0.4 depends on 0.1+0.2+0.3, permanently blocked | P2 |
| Reproduction: executor moved to section 1 tasks then deadlocked on 0.4 | P2 |
| Expected behavior: validate each task before evaluating dependencies | FR1 |
| Affected code: task_selector.py find_next_task logic | P1, FR1 |
| Affected code: validator.py validate_task invocation | FR1 |
| LangSmith Trace reference | P1, P2 |
| 5 Whys W1: dependent tasks blocked by unvalidated prereq | P2 |
| 5 Whys W2: find_next_task doesn't validate parallel group systematically | P1 |
| 5 Whys W3: task selection prioritizes any ready task without enforcing validation-first | P1, FR1 |
| 5 Whys W4: status check doesn't distinguish completed from verified | FR2 |
| 5 Whys W5: run_after metadata not wired into task selection logic | P1, FR1 |
| Root Need: enforce validation phase after parallel group completes | FR1 |
| Root Need: tasks unblock dependents only after "verified" not "completed" | FR2 |
| Summary: task selection prioritizes any ready task, breaking dependency guarantee | P1, P2 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [PROB] | PROB | P1 | Mapped |
| C2 [PROB] | PROB | P1 | Mapped |
| C3 [PROB] | PROB | P2 | Mapped |
| C4 [FACT] | FACT | P1, P2 | Mapped: provides reproduction context for parallel group behavior |
| C5 [FACT] | FACT | P1 | Mapped: evidence that validation was never invoked |
| C6 [FACT] | FACT | FR2 | Mapped: evidence of the completed/verified status gap |
| C7 [FACT] | FACT | P2 | Mapped: evidence of permanent blocking |
| C8 [FACT] | FACT | P2 | Mapped: evidence of deadlock after executor moved to other sections |
| C9 [GOAL] | GOAL | FR1, FR2 | Mapped: primary goal produces FR1 (ordering) and co-sources FR2 (status contract) |
| C10 [CTX] | CTX | P1, FR1 | Mapped: identifies affected code for both problem and fix |
| C11 [CTX] | CTX | FR1 | Mapped: identifies validation entry point for the fix |
| C12 [CTX] | CTX | -- | Unmapped: diagnostic trace reference for investigation, not a requirement source |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

**AC1**: When a parallel group of tasks completes, does the executor validate all tasks in the group that appear in the validation run_after list before selecting tasks from other sections? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse) + Derived from C2 [PROB] (inverse)
  Belongs to: P1
  Source clauses: [C1, C2, C4, C10]

**AC2**: For a task in the validation run_after list that completes as part of a parallel group, does the executor invoke validate_task before moving to other work? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse), informed by C5 [FACT]
  Belongs to: P1
  Source clauses: [C2, C5, C11]

**AC3**: Does the find_next_task logic in task_selector.py consult the validation run_after list when prioritizing the next task to select? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse), scoped by C10 [CTX]
  Belongs to: P1
  Source clauses: [C1, C10]

**AC4**: Is the executor free from permanent deadlock when dependent tasks wait on parallel prerequisites that require validation? YES = pass, NO = fail
  Origin: Derived from C3 [PROB] (inverse)
  Belongs to: P2
  Source clauses: [C3, C7, C8]

**AC5**: In the reproduction scenario (tasks 0.1, 0.2, 0.3 parallel in design-phase0; task 0.4 dependent on all three; task 0.3 requiring validation), does task 0.4 eventually become ready and execute? YES = pass, NO = fail
  Origin: Derived from C3 [PROB] (inverse), grounded by C4, C7, C8 [FACT]
  Belongs to: P2
  Source clauses: [C3, C4, C7, C8]

**AC6**: When the executor moves to independent tasks in other sections (e.g., section 1), does it return to complete pending validations from a prior parallel group rather than deadlocking? YES = pass, NO = fail
  Origin: Derived from C3 [PROB] (inverse), informed by C8 [FACT]
  Belongs to: P2
  Source clauses: [C3, C8]

**AC7**: After all tasks in a parallel group reach "completed" status, does the executor immediately schedule validation for those tasks that have validation requirements (run_after) before selecting tasks from subsequent sections? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C9, C10]

**AC8**: Does the task selector prioritize pending validations from a completed parallel group over selecting new independent tasks from other sections? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized as priority rule)
  Belongs to: FR1
  Source clauses: [C9, C10]

**AC9**: After validation completes for all tasks in a parallel group, do dependent tasks correctly see their prerequisites as satisfied and become ready? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized as end-to-end contract)
  Belongs to: FR1
  Source clauses: [C9, C11]

**AC10**: Is validation of parallel-group tasks invoked via the existing validate_task path in validator.py (no new validation code path)? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized), scoped by C11 [CTX]
  Belongs to: FR1
  Source clauses: [C9, C11]

**AC11**: For a dependency on a task that requires validation (appears in run_after), does the dependency check require "verified" status rather than accepting "completed"? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized as status contract), informed by C6 [FACT]
  Belongs to: FR2
  Source clauses: [C6, C9]

**AC12**: For a dependency on a task that does NOT require validation, does the dependency check accept "completed" status as sufficient (no regression)? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized, non-validation path preserved)
  Belongs to: FR2
  Source clauses: [C9]

**AC13**: If a task's effective_status is "completed" but it requires validation, do dependent tasks remain blocked until validation promotes the task to "verified"? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized), grounded by C6 [FACT]
  Belongs to: FR2
  Source clauses: [C6, C9]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2, AC3 | 3 |
| P2 | AC4, AC5, AC6 | 3 |
| FR1 | AC7, AC8, AC9, AC10 | 4 |
| FR2 | AC11, AC12, AC13 | 3 |

---

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | PROB | AC1, AC3 | Inverse: "not validated before" -> "does it validate before" |
| C2 | PROB | AC1, AC2 | Inverse: "moves on without validating" -> "validates before moving on" |
| C3 | PROB | AC4, AC5, AC6 | Inverse: "creates permanent deadlock" -> "free from deadlock" |
| C4 | FACT | AC5 | Grounds reproduction scenario; not independently testable (describes observed input state) |
| C5 | FACT | AC2 | Informs AC2 test expectation; not independently testable (describes observed symptom that AC2 prevents) |
| C6 | FACT | AC11, AC13 | Grounds the completed/verified distinction; not independently testable (describes observed status gap that AC11/AC13 prevent) |
| C7 | FACT | AC4, AC5 | Grounds deadlock evidence; not independently testable (describes observed consequence that AC4/AC5 prevent) |
| C8 | FACT | AC5, AC6 | Grounds section-crossing deadlock; not independently testable (describes observed executor path that AC5/AC6 prevent) |
| C9 | GOAL | AC7, AC8, AC9, AC10, AC11, AC12, AC13 | Operationalized into FR1 (AC7-AC10) and FR2 (AC11-AC13) |
| C10 | CTX | AC1, AC3, AC7, AC8 | Context: identifies task_selector.py as the code location; scopes where AC1/AC3/AC7/AC8 apply |
| C11 | CTX | AC2, AC9, AC10 | Context: identifies validator.py as the validation entry point; scopes AC2/AC10 implementation path |
| C12 | CTX | -- | Diagnostic trace reference for investigation; not a requirement source, no AC needed |
