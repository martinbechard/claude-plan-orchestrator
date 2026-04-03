# Structured Requirements: 78 Item Archived As Success With Pending Tasks

Source: tmp/plans/.claimed/78-item-archived-as-success-with-pending-tasks.md
Generated: 2026-03-30T16:33:54.720923+00:00

## Requirements

### P1: Archival node does not verify task terminal status before committing
Type: functional
Priority: high
Source clauses: [C1, C3, C4]
Description: The archival node in `langgraph_pipeline/pipeline/nodes/archival.py` does not verify that all plan tasks have reached a terminal status (verified, failed, or skipped) before committing the archive outcome. This was observed on item 74-item-page-step-explorer, where tasks 0.4 and 0.5 remained in "pending" status. The executor had deadlocked on an unvalidated dependency and returned without completing those tasks, yet the pipeline routed to archival and the node committed the item as complete.
Acceptance Criteria:
- Does the archival node inspect the status of every plan task before committing the outcome? YES = pass, NO = fail
- If any task is not in a terminal status (verified, failed, skipped), does the archival node detect this condition? YES = pass, NO = fail

### P2: Items can be archived as "success" despite pending or blocked tasks
Type: functional
Priority: high
Source clauses: [C2, C3, C4]
Description: An item can be archived with outcome=success while tasks are still pending or blocked by unresolved dependencies. In the observed case (item 74-item-page-step-explorer), the executor deadlocked on an unvalidated dependency for tasks 0.4 and 0.5, returned without completing them, and the pipeline routed the item to archive, which silently committed it as outcome=success. There is no upstream gate preventing archival when tasks remain incomplete.
Acceptance Criteria:
- Is it impossible for an item to be archived as outcome=success when one or more tasks are still in pending or blocked status? YES = pass, NO = fail
- Does the system prevent silent success archival when the executor returns without completing all tasks? YES = pass, NO = fail

### FR1: Pre-archive validation gate for task terminal status
Type: functional
Priority: high
Source clauses: [C5, C7]
Description: Before archiving, the archival node (in `langgraph_pipeline/pipeline/nodes/archival.py`) must check whether all plan tasks are in a terminal status (verified, failed, or skipped). This validation must occur as a pre-commit gate -- i.e., before the archive outcome is written. If any task is not in a terminal status, the archival node must not commit outcome=success.
Acceptance Criteria:
- Does the archival node enumerate all plan tasks and check each task's status before committing? YES = pass, NO = fail
- Does the archival node define terminal statuses as exactly: verified, failed, skipped? YES = pass, NO = fail
- Does the archival node refuse to commit outcome=success if any task is not in a terminal status? YES = pass, NO = fail

### FR2: Outcome reflects pending tasks instead of silently reporting success
Type: functional
Priority: high
Source clauses: [C6, C7]
Description: If pending tasks remain at archive time, the outcome must reflect that condition rather than silently reporting success. The outcome should be set to outcome=warn (or equivalent non-success status) and include a message identifying the specific tasks that were not completed (e.g., still in pending or blocked status). This ensures operators can see which tasks were skipped or left incomplete.
Acceptance Criteria:
- When pending tasks remain at archive time, is the outcome set to something other than "success" (e.g., outcome=warn)? YES = pass, NO = fail
- Does the outcome message identify the specific tasks that were still pending or blocked? YES = pass, NO = fail
- Is the list of non-terminal tasks included in the archived output (not just logged)? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "The archival node does not verify that all plan tasks reached a terminal status" | P1, FR1 |
| "An item can be archived as 'success' while tasks are still pending or blocked" | P2 |
| "Item 74-item-page-step-explorer was archived as outcome=success, but tasks 0.4 and 0.5 were still in 'pending' status" | P1, P2 |
| "The executor returned without completing them (deadlocked on unvalidated dependency), the pipeline routed to archive, and archive committed the item as complete" | P1, P2 |
| "Before archiving, the archival node should check whether all plan tasks are in a terminal status" | FR1 |
| "If pending tasks remain, the outcome should reflect that (e.g. outcome=warn with a message identifying the skipped tasks), not silently report success" | FR2 |
| "langgraph_pipeline/pipeline/nodes/archival.py - archive node" | FR1, FR2 |
| "LangSmith Trace: 3174b058-af3a-4ca4-afd5-4c39ca7d9ec2" | (context, see grid) |
| 5 Whys Analysis (W1-W5 and Root Need) | P1, P2, FR1, FR2 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [C-PROB] | PROB | P1 | Mapped |
| C2 [C-PROB] | PROB | P2 | Mapped |
| C3 [C-FACT] | FACT | P1, P2 | Mapped (evidence supporting both problems) |
| C4 [C-FACT] | FACT | P1, P2 | Mapped (evidence supporting both problems) |
| C5 [C-GOAL] | GOAL | FR1 | Mapped |
| C6 [C-GOAL] | GOAL | FR2 | Mapped |
| C7 [C-CTX] | CTX | FR1, FR2 | Mapped (identifies affected file for both feature requests) |
| C8 [C-CTX] | CTX | -- | Unmapped: diagnostic trace reference only, no actionable requirement derivable |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

**AC1**: Does the archival node inspect the status of every plan task before committing the archive outcome? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse: "does not verify" -> "does it verify?")
  Belongs to: P1
  Source clauses: [C1]

**AC2**: If any task is not in a terminal status (verified, failed, or skipped), does the archival node detect this condition before committing? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse: "does not verify terminal status" -> "does it detect non-terminal tasks?")
  Belongs to: P1
  Source clauses: [C1, C3]

**AC3**: Is it impossible for an item to be archived as outcome=success when one or more tasks are in pending or blocked status? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse: "can be archived as success while tasks still pending" -> "is this prevented?")
  Belongs to: P2
  Source clauses: [C2]

**AC4**: Does the system prevent silent success archival when the executor returns without completing all tasks? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse: "archive committed the item as complete" despite executor deadlock -> "does the system prevent this?")
  Belongs to: P2
  Source clauses: [C2, C4]

**AC5**: Does the archival node enumerate all plan tasks and check each task's status against defined terminal statuses before committing? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: "should check whether all plan tasks are in a terminal status" -> testable gate question)
  Belongs to: FR1
  Source clauses: [C5, C7]

**AC6**: Does the archival node define terminal statuses as exactly: verified, failed, skipped? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: terminal status definition extracted and made independently testable)
  Belongs to: FR1
  Source clauses: [C5]

**AC7**: Does the archival node refuse to commit outcome=success if any task is not in a terminal status? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: "should check" -> gate behavior: refusal to commit success on non-terminal tasks)
  Belongs to: FR1
  Source clauses: [C5, C7]

**AC8**: When pending tasks remain at archive time, is the outcome set to a non-success value (e.g., outcome=warn)? YES = pass, NO = fail
  Origin: Derived from C6 [GOAL] (operationalized: "outcome should reflect that" -> "is outcome non-success?")
  Belongs to: FR2
  Source clauses: [C6]

**AC9**: Does the outcome message identify the specific tasks that were still pending or blocked at archive time? YES = pass, NO = fail
  Origin: Derived from C6 [GOAL] (operationalized: "message identifying the skipped tasks" -> "does the message identify them?")
  Belongs to: FR2
  Source clauses: [C6]

**AC10**: Is the list of non-terminal tasks included in the archived output artifact, not only in transient logs? YES = pass, NO = fail
  Origin: Derived from C6 [GOAL] (operationalized: persistence of evidence made testable -- operators must find the list in the output, not hunt through logs)
  Belongs to: FR2
  Source clauses: [C6, C7]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2 | 2 |
| P2 | AC3, AC4 | 2 |
| FR1 | AC5, AC6, AC7 | 3 |
| FR2 | AC8, AC9, AC10 | 3 |

---

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | PROB | AC1, AC2 | Inverse ("does not verify" -> "does it verify/detect?") |
| C2 | PROB | AC3, AC4 | Inverse ("can be archived as success" -> "is it prevented?") |
| C3 | FACT | -- | Evidence supporting P1 and P2; corroborates AC2 and AC3 but does not generate a distinct testable criterion. The specific incident (item 74, tasks 0.4/0.5) is a historical observation, not a repeatable test condition. |
| C4 | FACT | -- | Evidence supporting P1 and P2; corroborates AC4 (executor-returns-incomplete scenario). The deadlock mechanism is a causal explanation, not a testable property of the archival node itself. |
| C5 | GOAL | AC5, AC6, AC7 | Operationalized (goal decomposed into enumeration, definition, and gate behavior) |
| C6 | GOAL | AC8, AC9, AC10 | Operationalized (goal decomposed into outcome value, message content, and persistence) |
| C7 | CTX | -- | Context: identifies the affected file (`archival.py`). Referenced as implementation scope in AC5, AC7, AC10; does not generate its own testable criterion. |
| C8 | CTX | -- | Context: diagnostic trace reference for forensic investigation only. No actionable requirement derivable; trace ID may be used to reproduce the original failure but is not a testable acceptance condition. |
