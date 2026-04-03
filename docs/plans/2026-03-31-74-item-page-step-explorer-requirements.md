# Structured Requirements: 74 Item Page Step Explorer

Source: tmp/plans/.claimed/74-item-page-step-explorer.md
Generated: 2026-03-31T21:07:10.918551+00:00

## Requirements

### P1: Flat artifact layout lacks visual hierarchy
Type: UI
Priority: high
Source clauses: [C1, C3, C4]
Description: The work item detail page displays all artifacts (raw input, clause register, 5 whys, structured requirements, design, plan, validation reports, execution logs) in a single long page with no visual hierarchy showing which pipeline stage produced each artifact. Users cannot distinguish stage boundaries or understand the relationship between artifacts and the pipeline phases that generated them.
Acceptance Criteria:
- Does the current page dump all sections in a flat, undifferentiated list? YES = confirmed problem, NO = fail

### P2: No timestamps on artifacts or pipeline stages
Type: UI
Priority: medium
Source clauses: [C5]
Description: The item detail page shows no timestamps indicating when pipeline stages completed or when individual artifacts were created or last modified. Users have no temporal context for the work performed.
Acceptance Criteria:
- Are artifacts and stages displayed without any timestamp information? YES = confirmed problem, NO = fail

### P3: No way to collapse irrelevant sections
Type: UI
Priority: high
Source clauses: [C6, C26]
Description: All sections are permanently expanded with no collapse/expand mechanism. Users are forced to scroll through irrelevant sections to find the artifact they need, creating unnecessary friction and cognitive overload.
Acceptance Criteria:
- Are users forced to scroll through all sections with no way to collapse them? YES = confirmed problem, NO = fail

### P4: Page slow from loading all artifacts at once
Type: performance
Priority: high
Source clauses: [C23]
Description: When all artifacts load together at page load time, the page becomes slow to render. Work items accumulate many artifacts across multiple stages, and loading them all eagerly degrades page performance.
Acceptance Criteria:
- Does the page load all artifact content eagerly, causing slow render times? YES = confirmed problem, NO = fail

### FR1: Step explorer organizing artifacts by pipeline stage
Type: UI
Priority: high
Source clauses: [C2, C7, C8, C9, C10, C11, C12, C13]
Description: The system should organize all artifacts under their respective pipeline stages in chronological order, presented as a step explorer. The defined stages and their artifacts are:
1. **Intake** - User request (raw input), clause register, 5 whys analysis
2. **Requirements** - Structured requirements document
3. **Planning** - Design document, YAML plan
4. **Execution** - Per-task results, validation reports
5. **Verification** - Final verification report (defects only)
6. **Archive** - Completion status, outcome
Acceptance Criteria:
- Does the page display an Intake stage containing user request, clause register, and 5 whys analysis? YES = pass, NO = fail
- Does the page display a Requirements stage containing the structured requirements document? YES = pass, NO = fail
- Does the page display a Planning stage containing the design document and YAML plan? YES = pass, NO = fail
- Does the page display an Execution stage containing per-task results and validation reports? YES = pass, NO = fail
- Does the page display a Verification stage containing the final verification report (for defects only)? YES = pass, NO = fail
- Does the page display an Archive stage containing completion status and outcome? YES = pass, NO = fail
- Are stages presented in chronological pipeline order (Intake → Requirements → Planning → Execution → Verification → Archive)? YES = pass, NO = fail

### FR2: Collapsible stage sections with status indicators
Type: UI
Priority: high
Source clauses: [C14, C15, C16]
Description: Each pipeline stage should be rendered as a collapsible section. Each section header must display the stage name and its current status (not started / in progress / done). When a stage has completed, the section must also show a timestamp of when the stage completed.
Acceptance Criteria:
- Is each pipeline stage rendered as a collapsible section that can be expanded and collapsed? YES = pass, NO = fail
- Does each stage header display the stage name? YES = pass, NO = fail
- Does each stage header display the stage status as one of: not started, in progress, or done? YES = pass, NO = fail
- Does each completed stage display a timestamp of when it completed? YES = pass, NO = fail

### FR3: Artifacts nested under stages with individual timestamps
Type: UI
Priority: high
Source clauses: [C17, C19]
Description: Within each stage section, artifacts should be nested underneath the stage header. Each artifact document must display a timestamp showing when it was created or last modified.
Acceptance Criteria:
- Are artifacts visually nested under their parent stage section? YES = pass, NO = fail
- Does each artifact display a timestamp showing when it was created or last modified? YES = pass, NO = fail

### FR4: On-demand artifact loading
Type: performance
Priority: high
Source clauses: [C18]
Description: Artifact content should be loaded on demand rather than all at page load. When a user expands a stage or artifact, only then should its content be fetched and rendered. This keeps the initial page load fast.
Acceptance Criteria:
- Are artifact contents deferred and not loaded at initial page load? YES = pass, NO = fail
- Does expanding a stage or artifact trigger loading of its content? YES = pass, NO = fail
- Is the initial page load noticeably faster than loading all artifacts eagerly? YES = pass, NO = fail

### FR5: Rename "Raw Input" to "User Request"
Type: UI
Priority: low
Source clauses: [C20]
Description: The section currently labeled "Raw Input" should be renamed to "User Request" since that more accurately describes what the content represents.
Acceptance Criteria:
- Is the former "Raw Input" section now labeled "User Request"? YES = pass, NO = fail
- Does the label "Raw Input" no longer appear as a section name on the item page? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "displays all artifacts in a single long page, making it hard to navigate" | P1 |
| "organized as a step explorer showing pipeline stages in order, with artifacts nested under each stage and loaded on demand" | FR1, FR3, FR4 |
| "All sections dumped at once in a long page" | P1 |
| "No visual hierarchy showing which pipeline stage produced each artifact" | P1 |
| "no timestamps" | P2 |
| "no way to collapse sections you're not interested in" | P3 |
| Stage definitions (Intake, Requirements, Planning, Execution, Verification, Archive) with their artifacts | FR1 |
| "Each stage should be a collapsible section" | FR2 |
| "Stage name and status (not started / in progress / done)" | FR2 |
| "Timestamp of when the stage completed" | FR2 |
| "Artifacts nested underneath, each with its own timestamp" | FR3 |
| "Artifacts loaded on demand (not all at page load) to keep the page fast" | FR4 |
| "Each artifact document should display a timestamp showing when it was created or last modified" | FR3 |
| "Raw Input section should be renamed to User Request" | FR5 |
| "page becomes slow to render and overwhelming to read" | P4 |
| "forced to scroll through irrelevant sections" | P3 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 | PROB | P1 | Mapped |
| C2 | GOAL | FR1 | Mapped |
| C3 | FACT | P1 | Mapped |
| C4 | PROB | P1 | Mapped |
| C5 | PROB | P2 | Mapped |
| C6 | PROB | P3 | Mapped |
| C7 | GOAL | FR1 | Mapped |
| C8 | AC | FR1 | Mapped |
| C9 | AC | FR1 | Mapped |
| C10 | AC | FR1 | Mapped |
| C11 | AC | FR1 | Mapped |
| C12 | AC | FR1 | Mapped |
| C13 | AC | FR1 | Mapped |
| C14 | AC | FR2 | Mapped |
| C15 | AC | FR2 | Mapped |
| C16 | AC | FR2 | Mapped |
| C17 | AC | FR3 | Mapped |
| C18 | AC | FR4 | Mapped |
| C19 | AC | FR3 | Mapped |
| C20 | AC | FR5 | Mapped |
| C21 | CTX | -- | Unmapped: context summarizing the root need; addressed collectively by FR1, FR2, FR3 |
| C22 | CTX | FR1 | Mapped: provides rationale for the six-stage structure |
| C23 | PROB | P4 | Mapped |
| C24 | CTX | FR4 | Mapped: provides rationale for on-demand loading |
| C25 | CTX | -- | Unmapped: context about typical user focus patterns; informs priority of FR2 and P3 |
| C26 | PROB | P3 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: Reviewer unavailable (iteration 1): quota_exhausted
