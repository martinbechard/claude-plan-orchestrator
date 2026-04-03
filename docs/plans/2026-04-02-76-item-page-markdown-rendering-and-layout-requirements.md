# Structured Requirements: 76 Item Page Markdown Rendering And Layout

Source: tmp/plans/.claimed/76-item-page-markdown-rendering-and-layout.md
Generated: 2026-04-02T18:30:46.780288+00:00

## Requirements

### P1: Markdown files displayed as raw text instead of rendered HTML
Type: UI
Priority: high
Source clauses: [C1, C2]
Description: Markdown files in artifact content sections on the item detail page are currently shown as raw, unformatted text. These files were previously rendered as formatted HTML with proper headings, lists, code blocks, and other standard markdown elements. The rendering capability has regressed or been removed.
Acceptance Criteria:
- Are markdown files in artifact content sections rendered as formatted HTML (not raw text)? YES = pass, NO = fail
- Are headings, lists, and code blocks rendered correctly in artifact markdown content? YES = pass, NO = fail

### P2: Expanded artifact sections break two-column layout
Type: UI
Priority: high
Source clauses: [C4]
Description: When an artifact section is expanded on the item detail page, the expanded content takes the full page width. This pushes or overlaps the right column, which contains plan tasks, completion history, and other sidebar content. The layout integrity of the two-column design is broken during expansion.
Acceptance Criteria:
- Does an expanded artifact section remain within its designated column width? YES = pass, NO = fail
- Does the right column (plan tasks, completion history, etc.) remain visible and correctly positioned when an artifact section is expanded? YES = pass, NO = fail
- Is there no overlap between expanded artifact content and the sidebar? YES = pass, NO = fail

### FR1: Restore markdown rendering for all artifact content sections
Type: functional
Priority: high
Source clauses: [C3, C2]
Description: Re-implement or restore markdown-to-HTML rendering for all artifact content sections on the item detail page. The rendering must support standard markdown elements including headings, lists, code blocks, and other formatting. This applies to all artifact content sections, not a subset.
Acceptance Criteria:
- Is markdown rendering applied to all artifact content sections on the item page? YES = pass, NO = fail
- Does the rendering support headings, lists, code blocks, and standard markdown formatting? YES = pass, NO = fail

### FR2: Constrain expanded content to respect column boundaries
Type: UI
Priority: high
Source clauses: [C5]
Description: Implement layout constraints so that when artifact content sections are expanded, they stay within their designated column and do not affect the sidebar layout. The expanded content must not push, overlap, or reflow the right column containing plan tasks, completion history, and other sidebar elements.
Acceptance Criteria:
- Does expanded artifact content stay within its column boundary? YES = pass, NO = fail
- Does expanding an artifact section leave the sidebar layout unaffected? YES = pass, NO = fail
- Does content overflow (e.g., long lines, large code blocks) respect the column width via scrolling or wrapping? YES = pass, NO = fail

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "Markdown files are shown as raw text" | P1 |
| "They used to be rendered as formatted HTML (headings, lists, code blocks, etc.)" | P1, FR1 |
| "Restore markdown rendering for all artifact content sections" | FR1 |
| "When an artifact section is expanded, it takes the full page width and pushes or overlaps the right column (plan tasks, completion history, etc.)" | P2 |
| "Expanded content should stay within its column and not affect the sidebar layout" | FR2 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [PROB] | PROB | P1 | Mapped |
| C2 [CTX] | CTX | P1, FR1 | Mapped: provides specifics (headings, lists, code blocks) and confirms regression |
| C3 [GOAL] | GOAL | FR1 | Mapped |
| C4 [PROB] | PROB | P2 | Mapped |
| C5 [GOAL] | GOAL | FR2 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

AC1: Are markdown files in artifact content sections rendered as formatted HTML instead of raw text? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse: "shown as raw text" → "rendered as formatted HTML")
  Belongs to: P1
  Source clauses: [C1, C2]

AC2: Are headings, lists, and code blocks rendered correctly in artifact markdown content? YES = pass, NO = fail
  Origin: Derived from C2 [CTX] (operationalized: context specifying expected formatting elements made testable)
  Belongs to: P1
  Source clauses: [C2]

AC3: Is markdown rendering applied to all artifact content sections on the item page (not just a subset)? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized: "restore markdown rendering for all artifact content sections")
  Belongs to: FR1
  Source clauses: [C3, C2]

AC4: Does the markdown rendering support standard formatting including headings, lists, code blocks, inline code, bold, and italic? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized: "restore markdown rendering" made specific and testable)
  Belongs to: FR1
  Source clauses: [C3, C2]

AC5: Does an expanded artifact section remain within its designated column width without taking full page width? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse: "takes the full page width" → "remains within designated column width")
  Belongs to: P2
  Source clauses: [C4]

AC6: Does the right column (plan tasks, completion history, etc.) remain visible and correctly positioned when an artifact section is expanded? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse: "pushes or overlaps the right column" → "right column remains visible and correctly positioned")
  Belongs to: P2
  Source clauses: [C4]

AC7: Is there no overlap between expanded artifact content and the sidebar? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse: "overlaps the right column" → "no overlap")
  Belongs to: P2
  Source clauses: [C4]

AC8: Does expanded artifact content stay within its column boundary without affecting the sidebar layout? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: "should stay within its column and not affect the sidebar layout")
  Belongs to: FR2
  Source clauses: [C5]

AC9: Does content overflow (e.g., long lines, large code blocks) respect the column width via horizontal scrolling or wrapping rather than breaking the layout? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: implicit overflow handling required by "stay within its column")
  Belongs to: FR2
  Source clauses: [C5]

---

## Requirement -> AC Coverage
| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2 | 2 |
| P2 | AC5, AC6, AC7 | 3 |
| FR1 | AC3, AC4 | 2 |
| FR2 | AC8, AC9 | 2 |

## Clause -> AC Coverage
| Clause | Type | AC | How |
|---|---|---|---|
| C1 | PROB | AC1 | Inverse: "raw text" → "rendered as HTML" |
| C2 | CTX | AC2, AC3, AC4 | Provides specifics (headings, lists, code blocks) and confirms regression — operationalized into testable formatting checks |
| C3 | GOAL | AC3, AC4 | Made testable: "restore rendering" → coverage and format verification |
| C4 | PROB | AC5, AC6, AC7 | Inverse: "takes full width / pushes or overlaps" → "stays in column / no overlap / sidebar intact" |
| C5 | GOAL | AC8, AC9 | Made testable: "stay within column" → boundary constraint and overflow handling |
