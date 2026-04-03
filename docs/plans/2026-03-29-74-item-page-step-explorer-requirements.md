# Structured Requirements: 74 Item Page Step Explorer

Source: tmp/plans/.claimed/74-item-page-step-explorer.md
Generated: 2026-03-29T17:13:12.038040+00:00

## Requirements

### P1: Flat artifact layout lacks visual hierarchy
Type: UI
Priority: high
Source clauses: [C1, C3, C4, C21]
Description: The work item detail page displays all artifacts (raw input, clause register, 5 whys, structured requirements, design, plan, validation reports, execution logs) in a single flat list with no visual hierarchy. Users cannot identify which pipeline stage produced each artifact or understand the relationship between stages and their outputs.
Acceptance Criteria:
- Are artifacts grouped by pipeline stage rather than displayed in a flat list? YES = pass, NO = fail
- Does each group show a visual hierarchy distinguishing stage headers from nested artifact entries? YES = pass, NO = fail
- Can users identify which pipeline stage produced a given artifact? YES = pass, NO = fail

### P2: No timestamps on stages or artifacts
Type: UI
Priority: high
Source clauses: [C5, C22]
Description: The current item detail page shows no timestamps on any stages or artifacts. Users cannot understand the temporal sequence of work -- when each stage ran or when each artifact was produced or last modified.
Acceptance Criteria:
- Does each stage display a completion timestamp? YES = pass, NO = fail
- Does each artifact display a creation or last-modified timestamp? YES = pass, NO = fail
- Can the user determine the temporal order of work from the displayed timestamps? YES = pass, NO = fail

### P3: Unable to collapse irrelevant sections
Type: UI
Priority: high
Source clauses: [C6, C27]
Description: There is no way to collapse sections the user is not interested in. Users are forced to scroll through all artifact content -- including irrelevant sections -- to locate the information they need.
Acceptance Criteria:
- Can users collapse individual stage sections to hide their artifacts? YES = pass, NO = fail
- Can users expand a collapsed section to reveal its artifacts? YES = pass, NO = fail
- Can users reach a specific section without scrolling through all preceding content? YES = pass, NO = fail

### P4: Page performance degradation from bulk artifact loading
Type: performance
Priority: high
Source clauses: [C25, C26]
Description: When all artifacts load together at page load, the page becomes slow to render and overwhelming to read. This is especially problematic as work items accumulate many artifacts across multiple pipeline stages over their lifecycle.
Acceptance Criteria:
- Does the page load quickly without fetching all artifact content upfront? YES = pass, NO = fail
- Is the initial page render fast even for items with many accumulated artifacts? YES = pass, NO = fail

### FR1: Step-based explorer with pipeline stage hierarchy
Type: UI
Priority: high
Source clauses: [C2, C7]
Description: Organize the item detail page as a step-based explorer showing pipeline stages in chronological order. Each stage is a collapsible section with its artifacts nested underneath. The six stages and their artifacts are:

1. Intake -- User request (formerly "Raw Input"), clause register, 5 whys analysis
2. Requirements -- Structured requirements document
3. Planning -- Design document, YAML plan
4. Execution -- Per-task results, validation reports
5. Verification -- Final verification report (defects only)
6. Archive -- Completion status, outcome

Each stage displays its name and status (not started / in progress / done), plus a timestamp of when the stage completed. Each artifact nested under a stage displays a timestamp showing when it was created or last modified. The "Raw Input" section must be renamed to "User Request".

Acceptance Criteria:
- Does the page show six collapsible stage sections in order: Intake, Requirements, Planning, Execution, Verification, Archive? YES = pass, NO = fail
- Does the Intake stage contain User Request, clause register, and 5 whys analysis? YES = pass, NO = fail
- Does the Requirements stage contain the structured requirements document? YES = pass, NO = fail
- Does the Planning stage contain the design document and YAML plan? YES = pass, NO = fail
- Does the Execution stage contain per-task results and validation reports? YES = pass, NO = fail
- Does the Verification stage contain the final verification report (defects only)? YES = pass, NO = fail
- Does the Archive stage contain completion status and outcome? YES = pass, NO = fail
- Does each stage display its name and status (not started / in progress / done)? YES = pass, NO = fail
- Does each stage display a timestamp of when it completed? YES = pass, NO = fail
- Does each artifact display a timestamp showing when it was created or last modified? YES = pass, NO = fail
- Is the former "Raw Input" section renamed to "User Request"? YES = pass, NO = fail
- Are stages displayed in chronological pipeline order (Intake through Archive)? YES = pass, NO = fail

### FR2: On-demand artifact loading
Type: performance
Priority: high
Source clauses: [C18]
Description: Artifacts must be loaded on demand -- not all at page load -- to keep the page fast. When a user expands a collapsed stage section, its artifact content is fetched at that point rather than being pre-loaded with the initial page render.
Acceptance Criteria:
- Are artifacts loaded only when their parent stage section is expanded? YES = pass, NO = fail
- Does the initial page load avoid fetching all artifact content? YES = pass, NO = fail
- Does the page render quickly on initial load compared to the current all-at-once approach? YES = pass, NO = fail

### UC1: Navigate directly to a relevant pipeline stage
Type: UI
Priority: high
Source clauses: [C30]
Description: A user who needs to focus on a specific pipeline stage for their current task can navigate directly to that stage section, expand it to view its artifacts, and work within that context -- without scrolling through or loading irrelevant sections. This provides instant access to relevant information and eliminates friction from information overload.
Acceptance Criteria:
- Can a user expand a single stage to view its artifacts without expanding all others? YES = pass, NO = fail
- Can a user collapse stages they are not interested in to reduce visual noise? YES = pass, NO = fail
- Does the interface support task-focused navigation where the user views one or a few stages at a time? YES = pass, NO = fail

---

## Coverage Matrix

| Raw Input Section | Requirement(s) |
|---|---|
| Title/intro: "displays all artifacts in a single long page, making it hard to navigate" | P1 |
| Title/intro: "organized as a step explorer showing the pipeline stages in order, with artifacts nested under each stage and loaded on demand" | FR1, FR2 |
| Current problem: "All sections... are dumped at once in a long page" | P1 |
| Current problem: "No visual hierarchy showing which pipeline stage produced each artifact" | P1 |
| Current problem: "no timestamps" | P2 |
| Current problem: "no way to collapse sections you're not interested in" | P3 |
| Desired behavior: "Organize artifacts under their pipeline stages in chronological order" | FR1 |
| Stage list: Intake (user request, clause register, 5 whys) | FR1 |
| Stage list: Requirements (structured requirements document) | FR1 |
| Stage list: Planning (design document, YAML plan) | FR1 |
| Stage list: Execution (per-task results, validation reports) | FR1 |
| Stage list: Verification (final verification report, defects only) | FR1 |
| Stage list: Archive (completion status, outcome) | FR1 |
| "Stage name and status (not started / in progress / done)" | FR1 |
| "Timestamp of when the stage completed" | FR1, P2 |
| "Artifacts nested underneath, each with its own timestamp" | FR1, P2 |
| "Artifacts loaded on demand (not all at page load) to keep the page fast" | FR2, P4 |
| "Each artifact document should display a timestamp showing when it was created or last modified" | FR1, P2 |
| "The 'Raw Input' section should be renamed to 'User Request'" | FR1 |
| 5 Whys W1: all artifacts displayed without hierarchy or collapsibility | P1, P3 |
| 5 Whys W2: users cannot identify stage or temporal sequence | P1, P2 |
| 5 Whys W3: each stage is a distinct phase with own outputs | FR1 |
| 5 Whys W4: page slow and overwhelming when all load together | P4 |
| 5 Whys W5: users need to focus on specific stages | UC1 |
| Root Need: hierarchical by stage with timestamps and on-demand loading | FR1, FR2, P2, UC1 |

## Clause Coverage Grid

| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [PROB] | PROB | P1 | Mapped |
| C2 [GOAL] | GOAL | FR1 | Mapped |
| C3 [FACT] | FACT | P1 | Mapped (supporting evidence) |
| C4 [PROB] | PROB | P1 | Mapped |
| C5 [PROB] | PROB | P2 | Mapped |
| C6 [PROB] | PROB | P3 | Mapped |
| C7 [GOAL] | GOAL | FR1 | Mapped |
| C8 [AC] | AC | FR1 | Mapped (acceptance criterion: Intake stage contents) |
| C9 [AC] | AC | FR1 | Mapped (acceptance criterion: Requirements stage contents) |
| C10 [AC] | AC | FR1 | Mapped (acceptance criterion: Planning stage contents) |
| C11 [AC] | AC | FR1 | Mapped (acceptance criterion: Execution stage contents) |
| C12 [AC] | AC | FR1 | Mapped (acceptance criterion: Verification stage contents) |
| C13 [AC] | AC | FR1 | Mapped (acceptance criterion: Archive stage contents) |
| C14 [AC] | AC | FR1 | Mapped (acceptance criterion: stage name and status display) |
| C15 [AC] | AC | FR1, P2 | Mapped (acceptance criterion: stage completion timestamp) |
| C16 [AC] | AC | FR1, P2 | Mapped (acceptance criterion: nested artifacts with timestamps) |
| C17 [AC] | AC | FR2 | Mapped (acceptance criterion: on-demand loading) |
| C18 [GOAL] | GOAL | FR2 | Mapped |
| C19 [AC] | AC | FR1, P2 | Mapped (acceptance criterion: artifact creation/modification timestamp) |
| C20 [AC] | AC | FR1 | Mapped (acceptance criterion: rename Raw Input to User Request) |
| C21 [PROB] | PROB | P1 | Mapped |
| C22 [PROB] | PROB | P2 | Mapped |
| C23 [CTX] | CTX | FR1 | Mapped (contextual justification for stage structure) |
| C24 [CTX] | CTX | FR1 | Mapped (contextual justification for chronological ordering) |
| C25 [PROB] | PROB | P4 | Mapped |
| C26 [PROB] | PROB | P4 | Mapped |
| C27 [PROB] | PROB | P3 | Mapped |
| C28 [FACT] | FACT | UC1 | Mapped (supporting context for task-focused navigation) |
| C29 [CTX] | CTX | UC1 | Mapped (contextual justification for stage-focused navigation) |
| C30 [GOAL] | GOAL | UC1 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

AC1: Does the Intake stage contain User Request, clause register, and 5 whys analysis? YES = pass, NO = fail
  Origin: Explicit from C8 [AC]
  Belongs to: FR1
  Source clauses: [C8]

AC2: Does the Requirements stage contain the structured requirements document? YES = pass, NO = fail
  Origin: Explicit from C9 [AC]
  Belongs to: FR1
  Source clauses: [C9]

AC3: Does the Planning stage contain the design document and YAML plan? YES = pass, NO = fail
  Origin: Explicit from C10 [AC]
  Belongs to: FR1
  Source clauses: [C10]

AC4: Does the Execution stage contain per-task results and validation reports? YES = pass, NO = fail
  Origin: Explicit from C11 [AC]
  Belongs to: FR1
  Source clauses: [C11]

AC5: Does the Verification stage contain the final verification report (defects only)? YES = pass, NO = fail
  Origin: Explicit from C12 [AC]
  Belongs to: FR1
  Source clauses: [C12]

AC6: Does the Archive stage contain completion status and outcome? YES = pass, NO = fail
  Origin: Explicit from C13 [AC]
  Belongs to: FR1
  Source clauses: [C13]

AC7: Does each stage display its name and status (not started / in progress / done)? YES = pass, NO = fail
  Origin: Explicit from C14 [AC]
  Belongs to: FR1
  Source clauses: [C14]

AC8: Is the former "Raw Input" section renamed to "User Request"? YES = pass, NO = fail
  Origin: Explicit from C20 [AC]
  Belongs to: FR1
  Source clauses: [C20]

AC9: Does the page show six collapsible stage sections displayed in chronological pipeline order (Intake, Requirements, Planning, Execution, Verification, Archive)? YES = pass, NO = fail
  Origin: Derived from C2 [GOAL] (operationalized) and C7 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C2, C7, C23, C24]

AC10: Does each stage display a timestamp of when it completed? YES = pass, NO = fail
  Origin: Explicit from C15 [AC]
  Belongs to: FR1, P2
  Source clauses: [C15]

AC11: Are artifacts nested underneath their parent stage, each with its own timestamp? YES = pass, NO = fail
  Origin: Explicit from C16 [AC]
  Belongs to: FR1, P2
  Source clauses: [C16]

AC12: Does each artifact document display a timestamp showing when it was created or last modified? YES = pass, NO = fail
  Origin: Explicit from C19 [AC]
  Belongs to: FR1, P2
  Source clauses: [C19]

AC13: Are artifacts loaded on demand, only when their parent stage section is expanded (not all at page load)? YES = pass, NO = fail
  Origin: Explicit from C17 [AC]
  Belongs to: FR2
  Source clauses: [C17]

AC14: Does the page render quickly on initial load by deferring artifact content fetching? YES = pass, NO = fail
  Origin: Derived from C18 [GOAL] (operationalized)
  Belongs to: FR2
  Source clauses: [C18]

AC15: Are artifacts grouped by pipeline stage rather than displayed in a flat list? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse)
  Belongs to: P1
  Source clauses: [C1, C3]

AC16: Does the page display a visual hierarchy distinguishing pipeline stage headers from their nested artifact entries? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse)
  Belongs to: P1
  Source clauses: [C4]

AC17: Can users identify which pipeline stage produced a given artifact? YES = pass, NO = fail
  Origin: Derived from C21 [PROB] (inverse)
  Belongs to: P1
  Source clauses: [C21]

AC18: Are timestamps displayed on both stages and artifacts? YES = pass, NO = fail
  Origin: Derived from C5 [PROB] (inverse)
  Belongs to: P2
  Source clauses: [C5]

AC19: Can the user determine the temporal order of work from the displayed timestamps? YES = pass, NO = fail
  Origin: Derived from C22 [PROB] (inverse)
  Belongs to: P2
  Source clauses: [C22]

AC20: Can users collapse individual stage sections to hide their artifacts? YES = pass, NO = fail
  Origin: Derived from C6 [PROB] (inverse)
  Belongs to: P3
  Source clauses: [C6]

AC21: Can users expand a collapsed section to reveal its artifacts? YES = pass, NO = fail
  Origin: Derived from C6 [PROB] (inverse)
  Belongs to: P3
  Source clauses: [C6]

AC22: Can users reach a specific section without scrolling through all preceding content? YES = pass, NO = fail
  Origin: Derived from C27 [PROB] (inverse)
  Belongs to: P3
  Source clauses: [C27]

AC23: Does the page load quickly without rendering all artifact content at once? YES = pass, NO = fail
  Origin: Derived from C25 [PROB] (inverse)
  Belongs to: P4
  Source clauses: [C25]

AC24: Is the initial page content manageable and not overwhelming even for items with many accumulated artifacts? YES = pass, NO = fail
  Origin: Derived from C26 [PROB] (inverse)
  Belongs to: P4
  Source clauses: [C26, C28]

AC25: Can a user expand a single stage to view its artifacts without expanding all others? YES = pass, NO = fail
  Origin: Derived from C30 [GOAL] (operationalized)
  Belongs to: UC1
  Source clauses: [C29, C30]

AC26: Does the interface support task-focused navigation where the user can view one or a few stages at a time while others remain collapsed? YES = pass, NO = fail
  Origin: Derived from C30 [GOAL] (operationalized)
  Belongs to: UC1
  Source clauses: [C30]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| FR1 | AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10, AC11, AC12 | 12 |
| FR2 | AC13, AC14 | 2 |
| P1 | AC15, AC16, AC17 | 3 |
| P2 | AC10, AC11, AC12, AC18, AC19 | 5 |
| P3 | AC20, AC21, AC22 | 3 |
| P4 | AC23, AC24 | 2 |
| UC1 | AC25, AC26 | 2 |

---

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | PROB | AC15 | Inverse |
| C2 | GOAL | AC9 | Operationalized |
| C3 | FACT | AC15 | Supporting evidence (source clause for P1 inverse) |
| C4 | PROB | AC16 | Inverse |
| C5 | PROB | AC18 | Inverse |
| C6 | PROB | AC20, AC21 | Inverse (collapse and expand tested separately) |
| C7 | GOAL | AC9 | Operationalized |
| C8 | AC | AC1 | Verbatim |
| C9 | AC | AC2 | Verbatim |
| C10 | AC | AC3 | Verbatim |
| C11 | AC | AC4 | Verbatim |
| C12 | AC | AC5 | Verbatim |
| C13 | AC | AC6 | Verbatim |
| C14 | AC | AC7 | Verbatim |
| C15 | AC | AC10 | Verbatim |
| C16 | AC | AC11 | Verbatim |
| C17 | AC | AC13 | Verbatim |
| C18 | GOAL | AC14 | Operationalized |
| C19 | AC | AC12 | Verbatim |
| C20 | AC | AC8 | Verbatim |
| C21 | PROB | AC17 | Inverse |
| C22 | PROB | AC19 | Inverse |
| C23 | CTX | -- | Context only: justifies stage structure in FR1; tested indirectly via AC9 (stage ordering) |
| C24 | CTX | -- | Context only: justifies chronological ordering in FR1; tested indirectly via AC9 |
| C25 | PROB | AC23 | Inverse |
| C26 | PROB | AC24 | Inverse |
| C27 | PROB | AC22 | Inverse |
| C28 | FACT | AC24 | Supporting context (scoping condition for "many artifacts" in P4 test) |
| C29 | CTX | -- | Context only: justifies stage-focused navigation in UC1; tested indirectly via AC25 |
| C30 | GOAL | AC25, AC26 | Operationalized |
