# Structured Requirements: 76 Item Page Markdown Rendering And Layout

Source: tmp/plans/.claimed/76-item-page-markdown-rendering-and-layout.md
Generated: 2026-03-30T16:30:40.735963+00:00

## Requirements

### P1: Markdown artifact content displayed as raw text
Type: UI
Priority: high
Source clauses: [C1, C2]
Description: Markdown files in artifact content sections on the item detail page are displayed as raw, unformatted text. This is a regression — the content was previously rendered as formatted HTML with proper headings, lists, code blocks, and other markdown elements. Users currently see raw markdown syntax instead of the expected formatted output.
Acceptance Criteria:
- Are markdown headings (h1–h6) rendered as styled HTML headings in artifact content sections? YES = pass, NO = fail
- Are markdown lists (ordered and unordered) rendered as proper HTML lists? YES = pass, NO = fail
- Are markdown code blocks rendered with appropriate formatting (monospace, background)? YES = pass, NO = fail
- Is all other standard markdown syntax (bold, italic, links, blockquotes, tables) rendered as formatted HTML? YES = pass, NO = fail
- Is raw markdown syntax (e.g., `#`, `*`, triple-backtick fences) hidden from the user in favor of rendered output? YES = pass, NO = fail

### P2: Expanded artifact section breaks two-column layout
Type: UI
Priority: high
Source clauses: [C4]
Description: When a user expands an artifact section on the item detail page, the expanded content takes the full page width. This causes the right-hand column (which contains plan tasks, completion history, and other sidebar content) to be pushed down or overlapped, breaking the intended two-column layout.
Acceptance Criteria:
- Does expanding an artifact section keep the right column (plan tasks, completion history) visible and in its expected position? YES = pass, NO = fail
- Does the expanded artifact content remain within the boundaries of its own column? YES = pass, NO = fail
- Is the right column free from overlap or occlusion by expanded artifact content? YES = pass, NO = fail

### FR1: Restore markdown rendering for all artifact content sections
Type: functional
Priority: high
Source clauses: [C3, C2]
Description: The system must apply markdown-to-HTML conversion to all artifact content sections on the item detail page, restoring the rendering behavior that previously existed. This includes processing headings, lists, code blocks, and all other standard markdown elements into their HTML equivalents before display.
Acceptance Criteria:
- Does every artifact content section on the item page pass its content through a markdown-to-HTML renderer before display? YES = pass, NO = fail
- Does the rendering apply to all artifact sections (not just a subset)? YES = pass, NO = fail

### FR2: Constrain expanded content to respect two-column layout
Type: UI
Priority: high
Source clauses: [C5]
Description: The system must enforce width and overflow constraints on artifact content sections so that when they are expanded, the content stays within its designated column. The sidebar layout (right column containing plan tasks, completion history, etc.) must remain unaffected by content expansion in the left column.
Acceptance Criteria:
- Does the expanded artifact section enforce a maximum width that does not exceed its column boundary? YES = pass, NO = fail
- Does long or wide content (e.g., wide code blocks, large tables) use horizontal scrolling or wrapping rather than overflowing into the sidebar? YES = pass, NO = fail
- Does the two-column layout remain stable and intact regardless of how many artifact sections are expanded simultaneously? YES = pass, NO = fail

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "Markdown files are shown as raw text" | P1 |
| "They used to be rendered as formatted HTML (headings, lists, code blocks, etc.)" | P1, FR1 |
| "Restore markdown rendering for all artifact content sections" | FR1 |
| "When an artifact section is expanded, it takes the full page width and pushes or overlaps the right column (plan tasks, completion history, etc.)" | P2 |
| "Expanded content should stay within its column and not affect the sidebar layout" | FR2 |
| 5 Whys analysis — W1/W2/W3 (markdown rendering root cause) | P1, FR1 |
| 5 Whys analysis — W4/W5 (layout overflow root cause) | P2, FR2 |
| Root Need summary | P1, P2, FR1, FR2 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 | PROB | P1 | Mapped |
| C2 | FACT | P1, FR1 | Mapped — provides regression context and specifies expected rendering elements |
| C3 | GOAL | FR1 | Mapped |
| C4 | PROB | P2 | Mapped |
| C5 | GOAL | FR2 | Mapped |
| C6 | CTX | -- | Unmapped: title context only, captured in requirement titles |
| C7 | CTX | -- | Unmapped: clarity rating metadata, not a requirement |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

**AC1**: Are markdown headings (h1--h6) rendered as styled HTML headings in artifact content sections? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse: "shown as raw text" -> "rendered as styled HTML"), informed by C2 [FACT] (specifies headings as expected element)
  Belongs to: P1
  Source clauses: [C1, C2]

**AC2**: Are markdown lists (ordered and unordered) rendered as proper HTML lists in artifact content sections? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse), informed by C2 [FACT] (specifies lists as expected element)
  Belongs to: P1
  Source clauses: [C1, C2]

**AC3**: Are markdown code blocks rendered with appropriate formatting (monospace font, background shading) in artifact content sections? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse), informed by C2 [FACT] (specifies code blocks as expected element)
  Belongs to: P1
  Source clauses: [C1, C2]

**AC4**: Is all other standard markdown syntax (bold, italic, links, blockquotes, tables) rendered as formatted HTML in artifact content sections? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse: raw text -> formatted HTML for full markdown spec)
  Belongs to: P1
  Source clauses: [C1, C2]

**AC5**: Is raw markdown syntax (e.g., #, *, triple-backtick fences) hidden from the user, replaced by rendered output? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse: "shown as raw text" -> raw syntax no longer visible)
  Belongs to: P1
  Source clauses: [C1]

**AC6**: Does every artifact content section on the item page pass its content through a markdown-to-HTML renderer before display? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized: "restore markdown rendering" -> verifiable rendering pipeline check)
  Belongs to: FR1
  Source clauses: [C3, C2]

**AC7**: Does the markdown rendering apply to all artifact content sections on the page, not just a subset? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized: "all artifact content sections" -> universality check)
  Belongs to: FR1
  Source clauses: [C3]

**AC8**: Does expanding an artifact section keep the right column (plan tasks, completion history) visible and in its expected position? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse: "pushes or overlaps the right column" -> right column stays in place)
  Belongs to: P2
  Source clauses: [C4]

**AC9**: Is the right column free from overlap or occlusion by expanded artifact content? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse: "overlaps the right column" -> no overlap)
  Belongs to: P2
  Source clauses: [C4]

**AC10**: Does the expanded artifact content remain within the boundaries of its designated column? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: "stay within its column" -> boundary containment check)
  Belongs to: FR2
  Source clauses: [C5]

**AC11**: Does long or wide content (e.g., wide code blocks, large tables) use horizontal scrolling or wrapping rather than overflowing into the sidebar? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: "not affect the sidebar layout" -> overflow handling mechanism)
  Belongs to: FR2
  Source clauses: [C5]

**AC12**: Does the two-column layout remain stable and intact regardless of how many artifact sections are expanded simultaneously? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: "not affect the sidebar layout" -> multi-expansion stress test)
  Belongs to: FR2
  Source clauses: [C5]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2, AC3, AC4, AC5 | 5 |
| P2 | AC8, AC9 | 2 |
| FR1 | AC6, AC7 | 2 |
| FR2 | AC10, AC11, AC12 | 3 |

---

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | PROB | AC1, AC2, AC3, AC4, AC5 | Inverse ("raw text" -> "rendered as HTML" for each markdown element class) |
| C2 | FACT | -- | Not directly testable. Provides regression context and enumerates expected rendering elements (headings, lists, code blocks). Informs AC1--AC4 and AC6 but is not the origin of any AC. |
| C3 | GOAL | AC6, AC7 | Operationalized ("restore rendering for all sections" -> renderer pipeline check + universality check) |
| C4 | PROB | AC8, AC9 | Inverse ("pushes or overlaps right column" -> right column stays positioned and unoccluded) |
| C5 | GOAL | AC10, AC11, AC12 | Operationalized ("stay within column, not affect sidebar" -> boundary containment, overflow handling, multi-expansion stability) |
| C6 | CTX | -- | Title metadata only. Captured in requirement titles; not testable. |
| C7 | CTX | -- | Clarity rating metadata. Internal process signal; not testable. |
