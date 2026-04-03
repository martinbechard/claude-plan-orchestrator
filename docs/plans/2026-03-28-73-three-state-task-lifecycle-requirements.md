# Structured Requirements: 73 Three State Task Lifecycle

Source: tmp/plans/.claimed/73-three-state-task-lifecycle.md
Generated: 2026-03-29T00:30:13.463688+00:00

## Requirements

### P1: System conflates execution completion with validation completion
Type: functional
Priority: high
Source clauses: [C1, C2, C20]
Description: Plan tasks currently have only two terminal-ish states -- "completed" (task code ran successfully) and "failed". There is no distinction between a task that finished executing and one that also passed validation. The system conflates execution completion with validation completion, creating ambiguity that breaks dependency correctness and makes crash recovery semantics unclear.
Acceptance Criteria:
- Does the system provide separate, distinguishable states for "execution finished" and "validation passed"? YES = pass, NO = fail
- Can a developer inspecting task status unambiguously determine whether validation has run? YES = pass, NO = fail

### P2: Crash recovery behavior is confusing due to ambiguous "completed" status
Type: functional
Priority: high
Source clauses: [C3, C4]
Description: The ambiguity surfaced during crash recovery: task 1.3 of item 71 had status "completed" but validation had not yet run. On resume, the executor re-validated 1.3 before moving to 2.1, which was correct behavior but confusing because "completed" implied the task was fully done. The status label misled human operators about the actual state of work.
Acceptance Criteria:
- After a crash where execution succeeded but validation did not run, does the task status clearly indicate that validation is still pending? YES = pass, NO = fail
- On crash recovery, is the distinction between "needs validation" and "fully done" unambiguous from the task status alone? YES = pass, NO = fail

### P3: Task selector cannot determine if a "completed" task has pending validation
Type: functional
Priority: high
Source clauses: [C16, C17, C18]
Description: The downstream task selector currently cannot tell if a "completed" task still has pending validation. A task that has executed but has not passed validation might fail validation, and starting dependent work before that is caught creates unnecessary rework and cascading failures. The dependency checker lacks the information needed to make safe scheduling decisions.
Acceptance Criteria:
- Can the task selector distinguish between a task awaiting validation and a task that has passed validation? YES = pass, NO = fail
- Are dependent tasks prevented from starting until the prerequisite task's validation has either passed or been confirmed unnecessary? YES = pass, NO = fail

### FR1: Extend task status enum with six explicit states
Type: functional
Priority: high
Source clauses: [C5, C6, C7, C8, C9, C10]
Description: The task status model must support exactly six states: (1) pending -- not started; (2) in_progress -- currently executing; (3) completed -- code/agent finished successfully, awaiting validation; (4) verified -- validation passed, or validation not configured for this task; (5) failed -- execution or validation failed; (6) skipped -- deliberately skipped. The "completed" state is redefined from a terminal state to an intermediate state indicating execution success but pending validation.
Acceptance Criteria:
- Does the task status type/enum contain exactly the six states: pending, in_progress, completed, verified, failed, skipped? YES = pass, NO = fail
- Is "completed" defined as an intermediate (non-terminal) state meaning "awaiting validation"? YES = pass, NO = fail
- Is "verified" defined as the terminal success state meaning "validation passed or not required"? YES = pass, NO = fail

### FR2: Task selector treats "verified" as terminal success state for dependency satisfaction
Type: functional
Priority: high
Source clauses: [C11, C15, C19, C21]
Description: The task selector must treat "verified" -- not "completed" -- as the terminal success state when checking dependency satisfaction. "Verified" is the only state that guarantees both execution succeeded AND validation passed (or was not required), making it the true signal that a task is fully complete and safe for dependents to start. The downstream task selector needs to know whether dependent tasks can safely start, and only tasks confirmed to be fully correct should satisfy task dependencies.
Acceptance Criteria:
- Does the task selector require prerequisite tasks to be in "verified" status before allowing dependent tasks to start? YES = pass, NO = fail
- Does a task in "completed" (but not "verified") status block its dependents from starting? YES = pass, NO = fail
- Does a task in "verified" status satisfy dependency checks for all downstream tasks? YES = pass, NO = fail

### FR3: Task runner sets two-step status progression (completed then verified)
Type: functional
Priority: high
Source clauses: [C12, C22]
Description: The task runner must set status to "completed" after successful execution, then to "verified" after validation passes. This two-step progression separates execution completion from validation completion, ensuring dependencies only proceed when tasks are fully correct, not just when code has run. The status transition sequence is: in_progress -> completed (execution success) -> verified (validation success).
Acceptance Criteria:
- Does the task runner set status to "completed" immediately after successful code/agent execution? YES = pass, NO = fail
- Does the task runner set status to "verified" after validation passes? YES = pass, NO = fail
- If validation fails after execution succeeds, does the task remain in a non-verified state (e.g., "failed")? YES = pass, NO = fail

### FR4: Dashboard shows verified tasks as done in progress counts
Type: UI
Priority: medium
Source clauses: [C13]
Description: Dashboard task progress counts must show verified tasks as done. The progress indicator should count "verified" (not "completed") tasks when calculating how many tasks are finished, reflecting the true terminal success state.
Acceptance Criteria:
- Do dashboard progress counts include "verified" tasks in the "done" tally? YES = pass, NO = fail
- Are "completed" (awaiting validation) tasks excluded from the "done" count in the progress display? YES = pass, NO = fail

### FR5: Backward compatibility for existing plans with "completed" tasks
Type: functional
Priority: high
Source clauses: [C14]
Description: Existing plans with "completed" tasks (where no validation was configured) must be treated as "verified" for backward compatibility during the transition. This ensures that plans created before the status model change continue to function correctly without manual migration.
Acceptance Criteria:
- Are existing plan tasks with "completed" status and no configured validation treated as "verified" by the task selector? YES = pass, NO = fail
- Do legacy plans continue to function without manual status migration? YES = pass, NO = fail
- Does the backward-compatibility logic apply only during the transition period and not mask genuinely incomplete validation for new tasks? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "Plan tasks currently have two terminal-ish states" | P1 |
| "There is no distinction between a task that finished executing and one that also passed validation" | P1, P3 |
| "This ambiguity surfaced during crash recovery: task 1.3 of item 71" | P2 |
| "On resume, the executor re-validated 1.3 before moving to 2.1, which was correct but confusing" | P2 |
| Proposed states list (pending, in_progress, completed, verified, failed, skipped) | FR1 |
| "Task selector should treat verified (not completed) as the terminal success state" | FR2 |
| "Task runner should set status to completed after successful execution, then verified after validation passes" | FR3 |
| "Dashboard task progress counts should show verified tasks as done" | FR4 |
| "Existing plans with completed tasks should be treated as verified for backward compatibility" | FR5 |
| 5 Whys W1: "completed label implied the task was fully done" | P2 |
| 5 Whys W2: "no way to distinguish between a task that finished executing and one that also passed validation" | P1 |
| 5 Whys W3: "Downstream task selector needs to know whether dependent tasks can safely start" | FR2, P3 |
| 5 Whys W4: "task might fail validation, starting dependent work creates rework and cascading failures" | P3 |
| 5 Whys W5: "Verified guarantees both execution succeeded AND validation passed" | FR2 |
| Root Need: "system conflates execution completion with validation completion" | P1, FR1, FR2 |
| Root Need: "verified as an explicit terminal success state" | FR2 |
| Summary: "Add verified state to separate execution from validation, ensuring dependencies only proceed when fully correct" | FR3, FR2 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 | FACT | P1 | Mapped: establishes current-state context for the problem |
| C2 | PROB | P1 | Mapped |
| C3 | FACT | P2 | Mapped: provides the specific incident evidence |
| C4 | PROB | P2 | Mapped |
| C5 | GOAL | FR1 | Mapped |
| C6 | GOAL | FR1 | Mapped |
| C7 | GOAL | FR1 | Mapped |
| C8 | GOAL | FR1 | Mapped |
| C9 | GOAL | FR1 | Mapped |
| C10 | GOAL | FR1 | Mapped |
| C11 | GOAL | FR2 | Mapped |
| C12 | GOAL | FR3 | Mapped |
| C13 | GOAL | FR4 | Mapped |
| C14 | GOAL | FR5 | Mapped |
| C15 | GOAL | FR2 | Mapped |
| C16 | PROB | P3 | Mapped |
| C17 | FACT | P3 | Mapped: factual evidence supporting the problem |
| C18 | CONS | P3 | Mapped: consequence that motivates the problem severity |
| C19 | GOAL | FR2 | Mapped |
| C20 | PROB | P1 | Mapped |
| C21 | GOAL | FR2 | Mapped |
| C22 | GOAL | FR3 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

**AC1**: Does the system provide separate, distinguishable states for "execution finished" and "validation passed"? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse) + C20 [PROB] (inverse)
  Belongs to: P1
  Source clauses: [C2, C20]

**AC2**: Can a developer inspecting task status unambiguously determine whether validation has run? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse)
  Belongs to: P1
  Source clauses: [C2]

**AC3**: After a crash where execution succeeded but validation did not run, does the task status clearly indicate that validation is still pending? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse)
  Belongs to: P2
  Source clauses: [C4]

**AC4**: On crash recovery, is the distinction between "needs validation" and "fully done" unambiguous from the task status alone? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse)
  Belongs to: P2
  Source clauses: [C4]

**AC5**: Can the task selector distinguish between a task awaiting validation and a task that has passed validation? YES = pass, NO = fail
  Origin: Derived from C16 [PROB] (inverse)
  Belongs to: P3
  Source clauses: [C16]

**AC6**: Are dependent tasks prevented from starting until the prerequisite task's validation has either passed or been confirmed unnecessary? YES = pass, NO = fail
  Origin: Derived from C15 [GOAL] (operationalized) + C16 [PROB] (inverse)
  Belongs to: P3
  Source clauses: [C15, C16]

**AC7**: Does the task status type/enum contain exactly six states: pending, in_progress, completed, verified, failed, skipped? YES = pass, NO = fail
  Origin: Derived from C5, C6, C7, C8, C9, C10 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C5, C6, C7, C8, C9, C10]

**AC8**: Is "completed" defined as an intermediate (non-terminal) state meaning "awaiting validation"? YES = pass, NO = fail
  Origin: Derived from C7 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C7]

**AC9**: Is "verified" defined as the terminal success state meaning "validation passed or not required"? YES = pass, NO = fail
  Origin: Derived from C8 [GOAL] (operationalized) + C19 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C8, C19]

**AC10**: Does the task selector require prerequisite tasks to be in "verified" status before allowing dependent tasks to start? YES = pass, NO = fail
  Origin: Derived from C11 [GOAL] (operationalized) + C21 [GOAL] (operationalized)
  Belongs to: FR2
  Source clauses: [C11, C15, C21]

**AC11**: Does a task in "completed" (but not "verified") status block its dependents from starting? YES = pass, NO = fail
  Origin: Derived from C11 [GOAL] (operationalized)
  Belongs to: FR2
  Source clauses: [C11, C15]

**AC12**: Does a task in "verified" status satisfy dependency checks for all downstream tasks? YES = pass, NO = fail
  Origin: Derived from C19 [GOAL] (operationalized) + C21 [GOAL] (operationalized)
  Belongs to: FR2
  Source clauses: [C19, C21]

**AC13**: Does the task runner set status to "completed" immediately after successful code/agent execution? YES = pass, NO = fail
  Origin: Derived from C12 [GOAL] (operationalized)
  Belongs to: FR3
  Source clauses: [C12]

**AC14**: Does the task runner set status to "verified" after validation passes? YES = pass, NO = fail
  Origin: Derived from C12 [GOAL] (operationalized) + C22 [GOAL] (operationalized)
  Belongs to: FR3
  Source clauses: [C12, C22]

**AC15**: If validation fails after execution succeeds, does the task remain in a non-verified state (e.g., "failed")? YES = pass, NO = fail
  Origin: Derived from C22 [GOAL] (operationalized)
  Belongs to: FR3
  Source clauses: [C22]

**AC16**: Do dashboard progress counts include "verified" tasks in the "done" tally? YES = pass, NO = fail
  Origin: Derived from C13 [GOAL] (operationalized)
  Belongs to: FR4
  Source clauses: [C13]

**AC17**: Are "completed" (awaiting validation) tasks excluded from the "done" count in the dashboard progress display? YES = pass, NO = fail
  Origin: Derived from C13 [GOAL] (operationalized)
  Belongs to: FR4
  Source clauses: [C13]

**AC18**: Are existing plan tasks with "completed" status and no configured validation treated as "verified" by the task selector? YES = pass, NO = fail
  Origin: Derived from C14 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C14]

**AC19**: Do legacy plans continue to function without manual status migration? YES = pass, NO = fail
  Origin: Derived from C14 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C14]

**AC20**: Does the backward-compatibility logic apply only during the transition period and not mask genuinely incomplete validation for new tasks? YES = pass, NO = fail
  Origin: Derived from C14 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C14]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2 | 2 |
| P2 | AC3, AC4 | 2 |
| P3 | AC5, AC6 | 2 |
| FR1 | AC7, AC8, AC9 | 3 |
| FR2 | AC10, AC11, AC12 | 3 |
| FR3 | AC13, AC14, AC15 | 3 |
| FR4 | AC16, AC17 | 2 |
| FR5 | AC18, AC19, AC20 | 3 |

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | FACT | -- | Context: establishes the current two-state model; tested indirectly via AC1 (P1 requires distinguishing states beyond the current two) |
| C2 | PROB | AC1, AC2 | Inverse: "no distinction" -> "does the system distinguish?" |
| C3 | FACT | -- | Evidence: specific crash-recovery incident motivating P2; tested indirectly via AC3, AC4 (the crash scenario described is exactly what those ACs verify) |
| C4 | PROB | AC3, AC4 | Inverse: "confusing because completed implied fully done" -> "is the distinction unambiguous?" |
| C5 | GOAL | AC7 | Made testable: "pending: not started" -> enum contains pending state |
| C6 | GOAL | AC7 | Made testable: "in_progress: currently executing" -> enum contains in_progress state |
| C7 | GOAL | AC7, AC8 | Made testable: "completed: awaiting validation" -> enum contains completed as intermediate state |
| C8 | GOAL | AC7, AC9 | Made testable: "verified: validation passed" -> enum contains verified as terminal success |
| C9 | GOAL | AC7 | Made testable: "failed: execution or validation failed" -> enum contains failed state |
| C10 | GOAL | AC7 | Made testable: "skipped: deliberately skipped" -> enum contains skipped state |
| C11 | GOAL | AC10, AC11 | Made testable: "treat verified as terminal success for dependencies" -> selector requires verified |
| C12 | GOAL | AC13, AC14 | Made testable: "set completed then verified" -> two-step status progression |
| C13 | GOAL | AC16, AC17 | Made testable: "show verified as done" -> dashboard counts verified as done, excludes completed |
| C14 | GOAL | AC18, AC19, AC20 | Made testable: "backward compatibility" -> legacy plans treated as verified, no manual migration, no masking |
| C15 | GOAL | AC6, AC10, AC11 | Made testable: "selector needs to know if dependents can safely start" -> dependents blocked until verified |
| C16 | PROB | AC5, AC6 | Inverse: "can't tell if completed has pending validation" -> "can the selector distinguish?" |
| C17 | FACT | -- | Factual observation: executed task might fail validation; motivates AC6 and AC15 (dependents blocked, failed validation keeps task non-verified) |
| C18 | CONS | -- | Consequence: "starting dependent work creates rework and cascading failures"; motivates the severity of P3; tested indirectly via AC6 (prevention of premature dependent starts) |
| C19 | GOAL | AC9, AC12 | Made testable: "verified guarantees execution + validation" -> verified is terminal success, satisfies dependencies |
| C20 | PROB | AC1 | Inverse: "conflates execution with validation completion" -> "does the system provide separate states?" |
| C21 | GOAL | AC10, AC12 | Made testable: "only fully correct tasks satisfy dependencies" -> selector requires verified |
| C22 | GOAL | AC14, AC15 | Made testable: "add verified to separate execution from validation" -> verified set after validation; failure keeps task non-verified |
