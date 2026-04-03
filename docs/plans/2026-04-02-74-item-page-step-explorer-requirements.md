# Structured Requirements: 74 Item Page Step Explorer

Source: tmp/plans/.claimed/74-item-page-step-explorer.md
Generated: 2026-04-02T18:45:14.248975+00:00

## Requirements

### P1: Flat artifact layout makes item page hard to navigate
Type: UI
Priority: high
Source clauses: [C1, C2, C4]
Description: The work item detail page displays all artifacts (raw input, clause register, 5 whys, structured requirements, design, plan, validation reports, execution logs) in a single long page with no grouping, making it difficult for users to find the information they need.
Acceptance Criteria:
- Are artifacts grouped by pipeline stage rather than displayed in a flat list? YES = pass, NO = fail
- Can a user locate a specific artifact without scrolling through the entire page? YES = pass, NO = fail

### P2: No visual hierarchy showing artifact provenance
Type: UI
Priority: high
Source clauses: [C5, C22]
Description: There is no visual hierarchy indicating which pipeline stage produced each artifact, and users cannot understand the temporal sequence of work. Users cannot easily identify whether an artifact was produced during Intake, Requirements, Planning, Execution, Verification, or Archive.
Acceptance Criteria:
- Does each artifact visually indicate which pipeline stage produced it? YES = pass, NO = fail
- Is the temporal sequence of stages visually apparent? YES = pass, NO = fail

### P3: No timestamps on artifacts or stages
Type: UI
Priority: high
Source clauses: [C6]
Description: The item page shows no timestamps, making it impossible to determine when artifacts were created or when pipeline stages completed.
Acceptance Criteria:
- Does each pipeline stage display a completion timestamp? YES = pass, NO = fail
- Does each artifact display a created-or-last-modified timestamp? YES = pass, NO = fail

### P4: No way to collapse unneeded sections
Type: UI
Priority: high
Source clauses: [C7]
Description: All sections are permanently expanded with no mechanism for users to collapse sections they are not currently interested in, forcing them to scroll past irrelevant content.
Acceptance Criteria:
- Can the user collapse any section they are not interested in? YES = pass, NO = fail
- Do collapsed sections remain collapsed until the user explicitly expands them? YES = pass, NO = fail

### P5: Page is slow and overwhelming when all artifacts load at once
Type: performance
Priority: medium
Source clauses: [C25]
Description: When all artifacts load together at page load time, the page becomes slow to render and cognitively overwhelming to read, especially for work items that have accumulated many artifacts across multiple stages.
Acceptance Criteria:
- Does the page load without rendering all artifact content upfront? YES = pass, NO = fail
- Is the initial page load noticeably faster than the current all-at-once rendering? YES = pass, NO = fail

### FR1: Organize artifacts under pipeline stages in chronological order
Type: functional
Priority: high
Source clauses: [C3, C8, C9, C10, C11, C12, C13, C14, C23, C24]
Description: The system should organize artifacts under their pipeline stages in chronological order. The six stages and their nested artifacts are:
1. **Intake** - User request (raw input), clause register, 5 whys analysis
2. **Requirements** - Structured requirements document
3. **Planning** - Design document, YAML plan
4. **Execution** - Per-task results, validation reports
5. **Verification** - Final verification report (defects only)
6. **Archive** - Completion status, outcome

Each stage represents a distinct phase with its own outputs and context. The sequence is essential to understanding why decisions were made and what work was done.
Acceptance Criteria:
- Does the Intake stage contain user request, clause register, and 5 whys analysis? YES = pass, NO = fail
- Does the Requirements stage contain the structured requirements document? YES = pass, NO = fail
- Does the Planning stage contain the design document and YAML plan? YES = pass, NO = fail
- Does the Execution stage contain per-task results and validation reports? YES = pass, NO = fail
- Does the Verification stage contain the final verification report (shown for defects only)? YES = pass, NO = fail
- Does the Archive stage contain completion status and outcome? YES = pass, NO = fail
- Are the stages presented in the order: Intake, Requirements, Planning, Execution, Verification, Archive? YES = pass, NO = fail

### FR2: Collapsible stage sections with status and timestamps
Type: UI
Priority: high
Source clauses: [C15, C16, C17, C18, C20]
Description: Each pipeline stage should be rendered as a collapsible section. Each stage section displays:
- Stage name and status indicator (not started / in progress / done)
- Timestamp of when the stage completed
- Artifacts nested underneath, each with its own timestamp showing when it was created or last modified
Acceptance Criteria:
- Does each stage section show a status of "not started", "in progress", or "done"? YES = pass, NO = fail
- Does each stage section show its completion timestamp? YES = pass, NO = fail
- Are artifacts nested under their parent stage? YES = pass, NO = fail
- Does each artifact display a created-or-last-modified timestamp? YES = pass, NO = fail
- Can each stage section be collapsed and expanded? YES = pass, NO = fail

### FR3: On-demand artifact loading
Type: performance
Priority: medium
Source clauses: [C3, C19, C26, C27, C28]
Description: Artifacts should be loaded on demand (not all at page load) to keep the page fast. Since work items accumulate many artifacts across multiple stages and users typically need to focus on specific stages for their current task, loading artifact content only when the user expands a stage provides instant access to relevant sections, eliminates friction, and prevents information overload.
Acceptance Criteria:
- Are artifact contents fetched only when their parent stage is expanded? YES = pass, NO = fail
- Does the page load without fetching all artifact content upfront? YES = pass, NO = fail
- Does expanding a stage load its artifacts without a full page refresh? YES = pass, NO = fail

### FR4: Rename "Raw Input" to "User Request"
Type: UI
Priority: low
Source clauses: [C21]
Description: The "Raw Input" section should be renamed to "User Request" since that more accurately describes what it contains -- the original user request that initiated the work item.
Acceptance Criteria:
- Is the label "Raw Input" replaced with "User Request" everywhere it appears on the item page? YES = pass, NO = fail
- Does the underlying data still reference the same artifact content? YES = pass, NO = fail

---

## Coverage Matrix

| Raw Input Section | Requirement(s) |
|---|---|
| "displays all artifacts in a single long page, making it hard to navigate" | P1 |
| "no visual hierarchy showing which pipeline stage produced each artifact" | P2 |
| "no timestamps" | P3 |
| "no way to collapse sections you're not interested in" | P4 |
| "page becomes slow to render and overwhelming to read" | P5 |
| "organized as a step explorer showing the pipeline stages in order" | FR1 |
| Stage definitions (Intake, Requirements, Planning, Execution, Verification, Archive) | FR1 |
| "Each stage should be a collapsible section showing: stage name and status, timestamp, nested artifacts" | FR2 |
| "Each artifact document should display a timestamp" | FR2 |
| "Artifacts loaded on demand (not all at page load) to keep the page fast" | FR3 |
| "The 'Raw Input' section should be renamed to 'User Request'" | FR4 |
| "users typically need to focus on specific stages for their current task" | FR3 |
| "providing instant access to relevant sections eliminates friction" | FR3 |

## Clause Coverage Grid

| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 | FACT | P1 | Mapped |
| C2 | PROB | P1 | Mapped |
| C3 | GOAL | FR1, FR3 | Mapped |
| C4 | FACT | P1 | Mapped |
| C5 | PROB | P2 | Mapped |
| C6 | PROB | P3 | Mapped |
| C7 | PROB | P4 | Mapped |
| C8 | GOAL | FR1 | Mapped |
| C9 | AC | FR1 | Mapped |
| C10 | AC | FR1 | Mapped |
| C11 | AC | FR1 | Mapped |
| C12 | AC | FR1 | Mapped |
| C13 | AC | FR1 | Mapped |
| C14 | AC | FR1 | Mapped |
| C15 | GOAL | FR2 | Mapped |
| C16 | AC | FR2 | Mapped |
| C17 | AC | FR2 | Mapped |
| C18 | AC | FR2 | Mapped |
| C19 | CONS | FR3 | Mapped |
| C20 | AC | FR2 | Mapped |
| C21 | GOAL | FR4 | Mapped |
| C22 | PROB | P2 | Mapped |
| C23 | CTX | FR1 | Mapped: provides context for stage definitions |
| C24 | CTX | FR1 | Mapped: motivates chronological stage ordering |
| C25 | PROB | P5 | Mapped |
| C26 | CTX | FR3 | Mapped: motivates on-demand loading |
| C27 | CTX | FR3 | Mapped: motivates on-demand loading |
| C28 | GOAL | FR3 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

AC1: Are artifacts grouped by pipeline stage rather than displayed in a flat list? YES = pass, NO = fail
  Origin: Derived from C1 [FACT] + C2 [PROB] (inverse of "single long page" + "hard to navigate")
  Belongs to: P1
  Source clauses: [C1, C2, C4]

AC2: Can a user locate a specific artifact without scrolling through the entire page? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse)
  Belongs to: P1
  Source clauses: [C2]

AC3: Does each artifact visually indicate which pipeline stage produced it? YES = pass, NO = fail
  Origin: Derived from C5 [PROB] (inverse)
  Belongs to: P2
  Source clauses: [C5]

AC4: Is the temporal sequence of stages visually apparent (Intake -> Requirements -> Planning -> Execution -> Verification -> Archive)? YES = pass, NO = fail
  Origin: Derived from C22 [PROB] (inverse of "cannot understand the temporal sequence")
  Belongs to: P2
  Source clauses: [C22, C23]

AC5: Does each pipeline stage display a completion timestamp? YES = pass, NO = fail
  Origin: Derived from C6 [PROB] (inverse of "no timestamps")
  Belongs to: P3
  Source clauses: [C6, C17]

AC6: Does each artifact display a created-or-last-modified timestamp? YES = pass, NO = fail
  Origin: Explicit from C20 [AC]
  Belongs to: P3
  Source clauses: [C6, C20]

AC7: Can the user collapse any stage section they are not interested in? YES = pass, NO = fail
  Origin: Derived from C7 [PROB] (inverse of "no way to collapse sections")
  Belongs to: P4
  Source clauses: [C7]

AC8: Do collapsed sections remain collapsed until the user explicitly expands them? YES = pass, NO = fail
  Origin: Derived from C7 [PROB] (behavioral stability requirement)
  Belongs to: P4
  Source clauses: [C7]

AC9: Does the page load without rendering all artifact content upfront? YES = pass, NO = fail
  Origin: Derived from C25 [PROB] (inverse of "all artifacts load together, page becomes slow")
  Belongs to: P5
  Source clauses: [C25, C19]

AC10: Is the initial page load noticeably faster than the current all-at-once rendering? YES = pass, NO = fail
  Origin: Derived from C25 [PROB] (inverse)
  Belongs to: P5
  Source clauses: [C25]

AC11: Does the Intake stage contain user request, clause register, and 5 whys analysis? YES = pass, NO = fail
  Origin: Explicit from C9 [AC]
  Belongs to: FR1
  Source clauses: [C9]

AC12: Does the Requirements stage contain the structured requirements document? YES = pass, NO = fail
  Origin: Explicit from C10 [AC]
  Belongs to: FR1
  Source clauses: [C10]

AC13: Does the Planning stage contain the design document and YAML plan? YES = pass, NO = fail
  Origin: Explicit from C11 [AC]
  Belongs to: FR1
  Source clauses: [C11]

AC14: Does the Execution stage contain per-task results and validation reports? YES = pass, NO = fail
  Origin: Explicit from C12 [AC]
  Belongs to: FR1
  Source clauses: [C12]

AC15: Does the Verification stage contain the final verification report (shown for defects only)? YES = pass, NO = fail
  Origin: Explicit from C13 [AC]
  Belongs to: FR1
  Source clauses: [C13]

AC16: Does the Archive stage contain completion status and outcome? YES = pass, NO = fail
  Origin: Explicit from C14 [AC]
  Belongs to: FR1
  Source clauses: [C14]

AC17: Are the stages presented in the order: Intake, Requirements, Planning, Execution, Verification, Archive? YES = pass, NO = fail
  Origin: Derived from C8 [GOAL] (operationalized "chronological order" into explicit sequence)
  Belongs to: FR1
  Source clauses: [C3, C8]

AC18: Does each stage section show a status of "not started", "in progress", or "done"? YES = pass, NO = fail
  Origin: Explicit from C16 [AC]
  Belongs to: FR2
  Source clauses: [C15, C16]

AC19: Does each stage section show its completion timestamp? YES = pass, NO = fail
  Origin: Explicit from C17 [AC]
  Belongs to: FR2
  Source clauses: [C17]

AC20: Are artifacts nested under their parent stage? YES = pass, NO = fail
  Origin: Explicit from C18 [AC]
  Belongs to: FR2
  Source clauses: [C15, C18]

AC21: Does each artifact within a stage display a created-or-last-modified timestamp? YES = pass, NO = fail
  Origin: Explicit from C20 [AC]
  Belongs to: FR2
  Source clauses: [C18, C20]

AC22: Can each stage section be collapsed and expanded by the user? YES = pass, NO = fail
  Origin: Derived from C15 [GOAL] (operationalized "collapsible section")
  Belongs to: FR2
  Source clauses: [C15]

AC23: Are artifact contents fetched only when their parent stage is expanded? YES = pass, NO = fail
  Origin: Derived from C19 [CONS] (operationalized "loaded on demand")
  Belongs to: FR3
  Source clauses: [C3, C19]

AC24: Does the page load without fetching all artifact content upfront? YES = pass, NO = fail
  Origin: Derived from C28 [GOAL] (operationalized "instant access" via lazy loading)
  Belongs to: FR3
  Source clauses: [C19, C26, C27]

AC25: Does expanding a stage load its artifacts without a full page refresh? YES = pass, NO = fail
  Origin: Derived from C28 [GOAL] (operationalized "eliminates friction")
  Belongs to: FR3
  Source clauses: [C27, C28]

AC26: Is the label "Raw Input" replaced with "User Request" everywhere it appears on the item page? YES = pass, NO = fail
  Origin: Derived from C21 [GOAL] (operationalized)
  Belongs to: FR4
  Source clauses: [C21]

AC27: Does the underlying data still reference the same artifact content after the rename? YES = pass, NO = fail
  Origin: Derived from C21 [GOAL] (non-regression guard)
  Belongs to: FR4
  Source clauses: [C21]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2 | 2 |
| P2 | AC3, AC4 | 2 |
| P3 | AC5, AC6 | 2 |
| P4 | AC7, AC8 | 2 |
| P5 | AC9, AC10 | 2 |
| FR1 | AC11, AC12, AC13, AC14, AC15, AC16, AC17 | 7 |
| FR2 | AC18, AC19, AC20, AC21, AC22 | 5 |
| FR3 | AC23, AC24, AC25 | 3 |
| FR4 | AC26, AC27 | 2 |

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | FACT | AC1 | Context for grouping criterion |
| C2 | PROB | AC1, AC2 | Inverse |
| C3 | GOAL | AC17, AC23 | Made testable |
| C4 | FACT | AC1 | Context for grouping criterion |
| C5 | PROB | AC3 | Inverse |
| C6 | PROB | AC5, AC6 | Inverse |
| C7 | PROB | AC7, AC8 | Inverse |
| C8 | GOAL | AC17 | Made testable (explicit ordering) |
| C9 | AC | AC11 | Verbatim |
| C10 | AC | AC12 | Verbatim |
| C11 | AC | AC13 | Verbatim |
| C12 | AC | AC14 | Verbatim |
| C13 | AC | AC15 | Verbatim |
| C14 | AC | AC16 | Verbatim |
| C15 | GOAL | AC20, AC22 | Made testable |
| C16 | AC | AC18 | Verbatim |
| C17 | AC | AC5, AC19 | Verbatim |
| C18 | AC | AC20, AC21 | Verbatim |
| C19 | CONS | AC23, AC24 | Made testable |
| C20 | AC | AC6, AC21 | Verbatim |
| C21 | GOAL | AC26, AC27 | Made testable |
| C22 | PROB | AC4 | Inverse |
| C23 | CTX | AC4 | Context for stage ordering; not independently testable |
| C24 | CTX | -- | Motivation for chronological ordering; captured by AC17 indirectly. Not independently testable — provides rationale, not a verifiable behavior |
| C25 | PROB | AC9, AC10 | Inverse |
| C26 | CTX | AC24 | Motivation for on-demand loading; not independently testable — justifies why lazy loading matters |
| C27 | CTX | AC25 | Motivation for per-stage focus; not independently testable — justifies expand-in-place behavior |
| C28 | GOAL | AC25 | Made testable |
