# Structured Requirements: 83 Trace Links Empty Or Missing

Source: tmp/plans/.claimed/83-trace-links-empty-or-missing.md
Generated: 2026-03-31T20:44:41.233711+00:00

## Requirements

### P1: Trace links missing from most Recent Completions entries
Type: UI
Priority: high
Source clauses: [C1, C2]
Description: Most work items in the Recent Completions table have nothing in the Trace column. The system is not populating trace identifiers for the majority of completed work items, leaving users with no way to investigate execution history.
Acceptance Criteria:
- Does every work item in the Recent Completions table display a value in the Trace column? YES = pass, NO = fail

### P2: Existing trace links open to empty pages
Type: functional
Priority: high
Source clauses: [C1, C3]
Description: The few work items that do have a "Trace" link in the Recent Completions table open to an empty page with no content. The trace detail page fails to fetch or render any execution data, making the links useless.
Acceptance Criteria:
- Do all trace links in Recent Completions navigate to a page that displays trace content (not an empty page)? YES = pass, NO = fail

### UC1: Drill down from completion to hierarchical execution trace
Type: functional
Priority: high
Source clauses: [C4]
Description: A user viewing the Recent Completions table should be able to click a trace link on any completion and be taken to a hierarchical traces view showing the execution tree for that work item. The view must display the full execution structure, not a flat list or empty page.
Acceptance Criteria:
- Can a user click a trace link on a completion and see a hierarchical view of the execution tree? YES = pass, NO = fail
- Does the traces view show parent-child relationships between execution steps (i.e., a tree structure)? YES = pass, NO = fail

### FR1: Capture and persist trace identifiers for every work item execution
Type: functional
Priority: high
Source clauses: [C1, C2, C4, C5]
Description: The system must capture the execution trace identifier (e.g., LangSmith trace ID as referenced in C5) during work item execution and persist it so that the Recent Completions table can link to it. This integration must be end-to-end: from execution through to dashboard display, with no completions left without a trace reference.
Acceptance Criteria:
- Does the system record a trace identifier for every work item that completes execution? YES = pass, NO = fail
- Is the captured trace identifier used to populate the Trace column in Recent Completions? YES = pass, NO = fail

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "Trace links in Recent Completions are mostly empty or lead to empty pages" (title / problem statement) | P1, P2 |
| "Most work items in the Recent Completions table have nothing in the Trace column" | P1 |
| "The few that do have a 'Trace' link open to an empty page" | P2 |
| "every completion should have a trace link that drills down to a hierarchical traces view showing the execution tree" | UC1, FR1 |
| "LangSmith Trace: 7a591155-8a4b-4aa0-9d1a-31812b62d801" | FR1 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [C-PROB] | PROB | P1, P2, FR1 | Mapped |
| C2 [C-FACT] | FACT | P1 | Mapped |
| C3 [C-FACT] | FACT | P2 | Mapped |
| C4 [C-GOAL] | GOAL | UC1, FR1 | Mapped |
| C5 [C-CTX] | CTX | FR1 | Mapped: referenced as example of trace ID format and source system |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

AC1: Does every work item in the Recent Completions table display a non-empty value in the Trace column? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse: "trace links mostly empty" → "are trace links populated?") and C2 [FACT] (inverse: "nothing in Trace column" → "something in Trace column")
  Belongs to: P1
  Source clauses: [C1, C2]

AC2: Do all trace links in the Recent Completions table navigate to a page that displays trace content rather than an empty page? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse: "lead to empty pages" → "lead to non-empty pages") and C3 [FACT] (inverse: "open to an empty page" → "open to a page with content")
  Belongs to: P2
  Source clauses: [C1, C3]

AC3: Can a user click a trace link on any completion in the Recent Completions table and see a hierarchical view of the execution tree? YES = pass, NO = fail
  Origin: Derived from C4 [GOAL] (operationalized: "should be able to click a trace link that drills down to a hierarchical traces view" → testable click-through question)
  Belongs to: UC1
  Source clauses: [C4]

AC4: Does the trace detail view show parent-child relationships between execution steps (i.e., a tree structure, not a flat list)? YES = pass, NO = fail
  Origin: Derived from C4 [GOAL] (operationalized: "hierarchical traces view showing the execution tree" → verifiable tree-structure question)
  Belongs to: UC1
  Source clauses: [C4]

AC5: Does the system record a trace identifier for every work item that completes execution? YES = pass, NO = fail
  Origin: Derived from C4 [GOAL] (operationalized: "every completion should have a trace link") combined with C1 [PROB] (inverse: completions lack traces → completions must have traces)
  Belongs to: FR1
  Source clauses: [C1, C2, C4, C5]

AC6: Is the captured trace identifier used to populate the Trace column link in the Recent Completions table end-to-end (from execution capture through dashboard display)? YES = pass, NO = fail
  Origin: Derived from C4 [GOAL] (operationalized: end-to-end link requirement made testable) combined with C1 [PROB] (inverse of the missing-link problem)
  Belongs to: FR1
  Source clauses: [C1, C4, C5]

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
| C1 | PROB | AC1, AC2 | Inverse ("mostly empty / lead to empty pages" → "populated and non-empty") |
| C2 | FACT | AC1, AC5 | Subsumed: C2 is the factual evidence for C1; AC1 directly tests the inverse of C2's observation; AC5 ensures the root cause (missing capture) is fixed |
| C3 | FACT | AC2 | Subsumed: C3 is the factual evidence for the empty-page aspect of C1; AC2 directly tests the inverse |
| C4 | GOAL | AC3, AC4, AC5, AC6 | Made testable: hierarchical drill-down (AC3, AC4) and every-completion coverage (AC5, AC6) |
| C5 | CTX | -- | Context only: provides an example trace ID format (LangSmith UUID) and confirms the source system; not independently testable but referenced by FR1/AC5/AC6 to identify what kind of identifier must be captured |
