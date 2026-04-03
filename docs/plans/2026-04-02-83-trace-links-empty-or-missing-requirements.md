# Structured Requirements: 83 Trace Links Empty Or Missing

Source: tmp/plans/.claimed/83-trace-links-empty-or-missing.md
Generated: 2026-04-02T18:52:26.894848+00:00

## Requirements

### P1: Trace links missing from most Recent Completions entries
Type: UI
Priority: high
Source clauses: [C1, C2]
Description: Most work items in the Recent Completions table have nothing in the Trace column. The column exists but is unpopulated for the majority of rows, leaving users with no way to navigate to execution details for those items.
Acceptance Criteria:
- Does every work item in the Recent Completions table display a non-empty value in the Trace column? YES = pass, NO = fail

### P2: Existing trace links open to empty pages
Type: functional
Priority: high
Source clauses: [C1, C3]
Description: The small number of work items that do have a "Trace" link in the Recent Completions table lead to pages with no content. Clicking the link navigates successfully (no 404), but the destination page renders empty — no trace data, no execution tree, no error message.
Acceptance Criteria:
- Does every trace link in the Recent Completions table open a page that displays trace content (not an empty page)? YES = pass, NO = fail

### UC1: Drill down from a completion to a hierarchical execution trace
Type: functional
Priority: high
Source clauses: [C4]
Description: A user viewing the Recent Completions table should be able to click a trace link on any completed work item and arrive at a hierarchical traces view that shows the full execution tree for that item. The view must represent the parent-child relationships of execution steps so the user can understand what happened during processing.
Acceptance Criteria:
- Can a user click a trace link on any completed work item and see a hierarchical view of the execution tree? YES = pass, NO = fail
- Does the hierarchical view show parent-child relationships between execution steps? YES = pass, NO = fail

### FR1: Capture and store trace identifiers for every work item execution
Type: functional
Priority: high
Source clauses: [C1, C2, C4, C5]
Description: The system must capture a trace identifier (e.g., a LangSmith trace ID as referenced in C5) during every work item execution and persist it in the completion record. This end-to-end mapping between execution and completion is the prerequisite for populating trace links. Without it, the Trace column will remain empty for most items.
Acceptance Criteria:
- Does every newly completed work item have a trace identifier stored in its completion record? YES = pass, NO = fail
- Is the stored trace identifier valid and resolvable to actual trace data? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "Trace links in Recent Completions are mostly empty or lead to empty pages" (title / C1) | P1, P2 |
| "Most work items in the Recent Completions table have nothing in the Trace column" (C2) | P1 |
| "The few that do have a 'Trace' link open to an empty page" (C3) | P2 |
| "every completion should have a trace link that drills down to a hierarchical traces view showing the execution tree" (C4) | UC1, FR1 |
| "LangSmith Trace: 7a591155-..." (C5) | FR1 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [PROB] | PROB | P1, P2 | Mapped |
| C2 [FACT] | FACT | P1 | Mapped |
| C3 [FACT] | FACT | P2 | Mapped |
| C4 [GOAL] | GOAL | UC1, FR1 | Mapped |
| C5 [CTX] | CTX | FR1 | Mapped: informs trace-ID capture requirement |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

AC1: Does every work item in the Recent Completions table display a non-empty, clickable trace link in the Trace column? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse — "mostly empty" inverted to "every item has a link")
  Belongs to: P1
  Source clauses: [C1, C2]

AC2: Does every trace link in the Recent Completions table open a page that displays trace content rather than rendering empty? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse — "lead to empty pages" inverted to "displays trace content")
  Belongs to: P2
  Source clauses: [C1, C3]

AC3: Can a user click a trace link on any completed work item and see a hierarchical view of the execution tree? YES = pass, NO = fail
  Origin: Derived from C4 [GOAL] (operationalized — "drills down to a hierarchical traces view" made testable)
  Belongs to: UC1
  Source clauses: [C4]

AC4: Does the hierarchical trace view display parent-child relationships between execution steps? YES = pass, NO = fail
  Origin: Derived from C4 [GOAL] (operationalized — "showing the execution tree" made testable as structural requirement)
  Belongs to: UC1
  Source clauses: [C4]

AC5: Does every newly completed work item have a trace identifier stored in its completion record? YES = pass, NO = fail
  Origin: Derived from C4 [GOAL] (operationalized — prerequisite for "every completion should have a trace link")
  Belongs to: FR1
  Source clauses: [C1, C2, C4]

AC6: Is every stored trace identifier valid and resolvable to actual trace data? YES = pass, NO = fail
  Origin: Derived from C4 [GOAL] (operationalized — trace link must "drill down" to real data, so the ID must resolve)
  Belongs to: FR1
  Source clauses: [C4, C5]

---

## Requirement -> AC Coverage
| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1 | 1 |
| P2 | AC2 | 1 |
| UC1 | AC3, AC4 | 2 |
| FR1 | AC5, AC6 | 2 |

## Clause -> AC Coverage
| Clause | Type | AC | How |
|---|---|---|---|
| C1 | PROB | AC1, AC2 | Inverse ("mostly empty / empty pages" -> "every item has link / displays content") |
| C2 | FACT | AC1 | Subsumed — C2 states the factual observation that AC1 directly tests against |
| C3 | FACT | AC2 | Subsumed — C3 states the factual observation that AC2 directly tests against |
| C4 | GOAL | AC3, AC4, AC5, AC6 | Made testable (hierarchy, parent-child, trace capture, resolvability) |
| C5 | CTX | AC6 | Context — informs what a valid trace identifier looks like (LangSmith ID format); not independently testable but shapes AC6's "resolvable" criterion |
