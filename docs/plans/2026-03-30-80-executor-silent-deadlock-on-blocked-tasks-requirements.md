# Structured Requirements: 80 Executor Silent Deadlock On Blocked Tasks

Source: tmp/plans/.claimed/80-executor-silent-deadlock-on-blocked-tasks.md
Generated: 2026-03-30T16:37:15.430619+00:00

## Requirements

### P1: find_next_task does not distinguish completion from deadlock
Type: functional
Priority: high
Source clauses: [C1, C2, C5, C11]
Description: The `find_next_task` function in `langgraph_pipeline/executor/nodes/task_selector.py` treats two fundamentally different states identically: (a) all tasks completed successfully, and (b) pending tasks exist but none are eligible because all are blocked by unsatisfied dependencies. When it examines remaining work, it finds pending tasks but checks only whether they are eligible to run, not whether the remaining dependency graph is solvable. As observed in item 74-item-page-step-explorer, tasks 0.4 and 0.5 were pending but blocked because task 0.3 was not validated. A log message exists at approximately line 268, but the executor loop still exits cleanly as if all work is done.
Acceptance Criteria:
- Does `find_next_task` return a distinguishable result when pending tasks exist but none are eligible due to unsatisfied dependencies? YES = pass, NO = fail
- Is the "all blocked" condition handled differently from "all completed" in the executor's return path? YES = pass, NO = fail

### P2: No error, warning, or distinct outcome signaling on deadlock
Type: functional
Priority: high
Source clauses: [C3, C11]
Description: When the executor encounters a state where pending tasks remain but none can proceed, it produces no error, no warning, and no distinct outcome value. Although a log message exists at approximately line 268 in `task_selector.py`, it is insufficient — the executor loop still exits cleanly without raising an error or setting a distinct outcome that downstream pipeline nodes can inspect.
Acceptance Criteria:
- Does the executor produce an error or warning when it exits with pending-but-blocked tasks? YES = pass, NO = fail
- Is the existing log message at line ~268 supplemented or replaced with an actionable signal (error, distinct outcome, or raised exception)? YES = pass, NO = fail

### P3: Pipeline archives deadlocked items as success
Type: functional
Priority: high
Source clauses: [C4, C6]
Description: Because the executor returns cleanly even when tasks are deadlocked, the pipeline interprets this as successful completion. In the observed case (item 74-item-page-step-explorer, after tasks 1.1 and 1.2 completed), the executor returned silently, the pipeline continued to the archival step, and the item was recorded as a success — despite tasks 0.4 and 0.5 never having run due to unsatisfied dependencies on task 0.3.
Acceptance Criteria:
- Does the pipeline refuse to archive an item as "success" when the executor signals a deadlock condition? YES = pass, NO = fail
- Is a deadlocked item recorded with a non-success outcome (e.g., "deadlock" or "failed")? YES = pass, NO = fail

### FR1: Deadlock detection when pending tasks have unsatisfied dependencies
Type: functional
Priority: high
Source clauses: [C7]
Description: The executor must detect when pending tasks exist but none can proceed because all are blocked by unsatisfied (or circular) dependencies. This is a deadlock condition and must be explicitly identified as such, rather than treated as normal completion. Detection should occur in the executor's main loop when `find_next_task` finds no eligible task but the task list still contains pending items.
Acceptance Criteria:
- Does the executor detect the condition where pending tasks exist but none have satisfied dependencies? YES = pass, NO = fail
- Is this condition classified internally as a "deadlock" (or equivalent named state)? YES = pass, NO = fail

### FR2: Report blocked tasks with their unsatisfied dependencies
Type: functional
Priority: medium
Source clauses: [C8]
Description: When a deadlock is detected, the executor must report an error or warning that includes the list of blocked tasks and, for each, the specific dependencies that are unsatisfied. This gives operators and the pipeline enough information to diagnose why execution stalled.
Acceptance Criteria:
- Does the deadlock report include the task IDs of all blocked tasks? YES = pass, NO = fail
- Does the deadlock report include, for each blocked task, the specific unsatisfied dependency task IDs? YES = pass, NO = fail

### FR3: Distinct "deadlock" outcome for pipeline handling
Type: functional
Priority: high
Source clauses: [C9]
Description: The executor must set a distinct outcome value (e.g., `"deadlock"`) when it detects the deadlock condition, so that downstream pipeline nodes (archival, notification, etc.) can distinguish deadlock from true success and handle it appropriately — for example, by not archiving the item as successful or by routing to an error-handling path.
Acceptance Criteria:
- Does the executor set a distinct, inspectable outcome value (not just a log message) when deadlock is detected? YES = pass, NO = fail
- Can downstream pipeline nodes programmatically distinguish "deadlock" from "success" using this outcome? YES = pass, NO = fail

### FR4: Log clear warning identifying blocked tasks and reasons
Type: functional
Priority: medium
Source clauses: [C10, C11]
Description: At minimum, the executor must log a clear warning message when deadlock is detected. The warning must identify which tasks are blocked and why (i.e., which dependencies are unsatisfied). This replaces or supplements the existing insufficient log message at approximately line 268 in `task_selector.py`, which logs but does not prevent the executor from exiting cleanly.
Acceptance Criteria:
- Is a warning-level (or higher) log message emitted when deadlock is detected? YES = pass, NO = fail
- Does the log message include the blocked task IDs and their unsatisfied dependency IDs? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| Title: "Executor silently returns when all remaining tasks are blocked" | P1 |
| find_next_task returns as if execution is complete when tasks are blocked | P1, P2 |
| No error, warning, or distinct outcome indicating deadlock | P2, FR4 |
| Reproduction: item 74, tasks 1.1 and 1.2 completed | P3 |
| Tasks 0.4 and 0.5 pending but blocked (0.3 not validated) | P1 |
| Executor returned silently, pipeline archived as success | P3 |
| Executor should detect deadlock condition | FR1 |
| Report error/warning with list of blocked tasks and unsatisfied deps | FR2 |
| Set a distinct outcome (e.g. "deadlock") for pipeline handling | FR3 |
| At minimum, log a clear warning identifying blocked tasks and why | FR4 |
| task_selector.py line ~268 logs but exits cleanly | P1, P2, FR4 |
| 5 Whys: find_next_task doesn't distinguish completion from blocked | P1 |
| 5 Whys: clean return interpreted as success | P3 |
| 5 Whys: log at line 268 insufficient | P2, FR4 |
| 5 Whys: blocked tasks represent failed execution | FR1, FR3 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [PROB] | PROB | P1 | Mapped |
| C2 [PROB] | PROB | P1 | Mapped |
| C3 [PROB] | PROB | P2 | Mapped |
| C4 [CTX] | CTX | P3 | Mapped — reproduction context establishing the observed failure |
| C5 [FACT] | FACT | P1 | Mapped — specific blocked tasks demonstrating the detection gap |
| C6 [PROB] | PROB | P3 | Mapped |
| C7 [GOAL] | GOAL | FR1 | Mapped |
| C8 [AC] | AC | FR2 | Mapped |
| C9 [AC] | AC | FR3 | Mapped |
| C10 [AC] | AC | FR4 | Mapped |
| C11 [FACT] | FACT | P1, P2, FR4 | Mapped — code location and existing insufficient logging |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

**AC1**: Does `find_next_task` return a distinguishable result when pending tasks exist but none are eligible due to unsatisfied dependencies? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse) and C2 [PROB] (inverse)
  Belongs to: P1
  Source clauses: [C1, C2, C5]

**AC2**: Is the "all blocked" condition handled differently from "all completed" in the executor's return path? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse)
  Belongs to: P1
  Source clauses: [C1, C2, C11]

**AC3**: Does the executor produce an error, warning, or distinct outcome when it exits with pending-but-blocked tasks? YES = pass, NO = fail
  Origin: Derived from C3 [PROB] (inverse)
  Belongs to: P2
  Source clauses: [C3, C11]

**AC4**: Is the existing log message at line ~268 in `task_selector.py` supplemented or replaced with an actionable signal (error, distinct outcome, or raised exception)? YES = pass, NO = fail
  Origin: Derived from C3 [PROB] (inverse)
  Belongs to: P2
  Source clauses: [C3, C11]

**AC5**: Does the pipeline refuse to archive an item as "success" when the executor signals a deadlock condition? YES = pass, NO = fail
  Origin: Derived from C6 [PROB] (inverse)
  Belongs to: P3
  Source clauses: [C6]

**AC6**: Is a deadlocked item recorded with a non-success outcome (e.g., "deadlock" or "failed")? YES = pass, NO = fail
  Origin: Derived from C6 [PROB] (inverse)
  Belongs to: P3
  Source clauses: [C6]

**AC7**: Does the executor detect when pending tasks exist but none have satisfied dependencies? YES = pass, NO = fail
  Origin: Derived from C7 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C7]

**AC8**: Is the deadlock condition classified internally as a "deadlock" (or equivalent named state)? YES = pass, NO = fail
  Origin: Derived from C7 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C7]

**AC9**: Does the deadlock report include the task IDs of all blocked tasks? YES = pass, NO = fail
  Origin: Explicit from C8 [AC]
  Belongs to: FR2
  Source clauses: [C8]

**AC10**: Does the deadlock report include, for each blocked task, the specific unsatisfied dependency task IDs? YES = pass, NO = fail
  Origin: Explicit from C8 [AC]
  Belongs to: FR2
  Source clauses: [C8]

**AC11**: Does the executor set a distinct, inspectable outcome value (not just a log message) when deadlock is detected? YES = pass, NO = fail
  Origin: Explicit from C9 [AC]
  Belongs to: FR3
  Source clauses: [C9]

**AC12**: Can downstream pipeline nodes programmatically distinguish "deadlock" from "success" using the executor's outcome? YES = pass, NO = fail
  Origin: Explicit from C9 [AC]
  Belongs to: FR3
  Source clauses: [C9]

**AC13**: Is a warning-level (or higher) log message emitted when deadlock is detected? YES = pass, NO = fail
  Origin: Explicit from C10 [AC]
  Belongs to: FR4
  Source clauses: [C10, C11]

**AC14**: Does the log message include the blocked task IDs and their unsatisfied dependency IDs? YES = pass, NO = fail
  Origin: Explicit from C10 [AC]
  Belongs to: FR4
  Source clauses: [C10, C11]

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2 | 2 |
| P2 | AC3, AC4 | 2 |
| P3 | AC5, AC6 | 2 |
| FR1 | AC7, AC8 | 2 |
| FR2 | AC9, AC10 | 2 |
| FR3 | AC11, AC12 | 2 |
| FR4 | AC13, AC14 | 2 |

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | PROB | AC1, AC2 | Inverse: "silently returns" -> "returns distinguishable result" |
| C2 | PROB | AC1, AC2 | Inverse: "returns as if complete" -> "handled differently from completed" |
| C3 | PROB | AC3, AC4 | Inverse: "no error/warning/outcome" -> "produces error/warning/outcome" |
| C4 | CTX | -- | Reproduction context establishing the observed failure; not independently testable |
| C5 | FACT | AC1 | Evidence context: specific blocked tasks demonstrating the detection gap |
| C6 | PROB | AC5, AC6 | Inverse: "archived as success" -> "refuses to archive as success" |
| C7 | GOAL | AC7, AC8 | Operationalized: "should detect" -> "does detect" + "classifies as deadlock" |
| C8 | AC | AC9, AC10 | Verbatim: split into task-ID reporting and dependency-ID reporting |
| C9 | AC | AC11, AC12 | Verbatim: split into outcome-setting and downstream-distinguishability |
| C10 | AC | AC13, AC14 | Verbatim: split into log-level check and log-content check |
| C11 | FACT | AC2, AC4, AC13 | Code-location evidence: anchors ACs that verify the fix site |
