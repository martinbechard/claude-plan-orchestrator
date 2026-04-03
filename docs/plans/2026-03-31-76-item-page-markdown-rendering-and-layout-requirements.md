# Structured Requirements: 76 Item Page Markdown Rendering And Layout

Source: tmp/plans/.claimed/76-item-page-markdown-rendering-and-layout.md
Generated: 2026-03-31T21:03:58.161288+00:00

## Requirements

### P1: Markdown files displayed as raw text instead of rendered HTML
Type: UI
Priority: high
Source clauses: [C1, C2]
Description: Markdown files in artifact content sections are currently shown as raw text. These files previously rendered as formatted HTML with proper headings, lists, code blocks, and other markdown elements. The rendering capability has regressed or been removed.
Acceptance Criteria:
- Are markdown artifact files rendered as formatted HTML (not raw text) in all artifact content sections? YES = pass, NO = fail
- Are headings, lists, and code blocks rendered correctly in artifact content? YES = pass, NO = fail

### P2: Expanded artifact sections break two-column layout
Type: UI
Priority: high
Source clauses: [C4]
Description: When an artifact section is expanded on the item detail page, the expanded content takes the full page width. This pushes or overlaps the right column, which contains plan tasks, completion history, and other sidebar content. The layout integrity of the two-column design is broken during expansion.
Acceptance Criteria:
- Does expanding an artifact section avoid pushing or overlapping the right column (plan tasks, completion history)? YES = pass, NO = fail
- Does the right column remain fully visible and correctly positioned when an artifact section is expanded? YES = pass, NO = fail

### FR1: Restore markdown rendering for all artifact content sections
Type: UI
Priority: high
Source clauses: [C3]
Description: The system should apply markdown-to-HTML conversion for all artifact content sections on the item detail page, restoring the previously working rendering behavior. All standard markdown elements (headings, lists, code blocks, etc.) must be supported.
Acceptance Criteria:
- Does the system convert markdown to rendered HTML in every artifact content section? YES = pass, NO = fail
- Are all standard markdown elements (headings, lists, code blocks, emphasis, links) rendered correctly? YES = pass, NO = fail

### FR2: Constrain expanded content to its column in two-column layout
Type: UI
Priority: high
Source clauses: [C5]
Description: Expanded artifact content should remain constrained within its column and must not affect the sidebar layout. The two-column page structure (artifact content on the left, plan tasks/completion history on the right) must be preserved regardless of expansion state.
Acceptance Criteria:
- Does expanded artifact content stay within its designated column width? YES = pass, NO = fail
- Does expanding or collapsing artifact content leave the sidebar layout unaffected? YES = pass, NO = fail
- Does content that exceeds the column width handle overflow gracefully (e.g., scrolling or wrapping) without breaking the layout? YES = pass, NO = fail

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "Markdown files are shown as raw text" | P1 |
| "They used to be rendered as formatted HTML (headings, lists, code blocks, etc.)" | P1 |
| "Restore markdown rendering for all artifact content sections" | FR1 |
| "When an artifact section is expanded, it takes the full page width and pushes or overlaps the right column (plan tasks, completion history, etc.)" | P2 |
| "Expanded content should stay within its column and not affect the sidebar layout" | FR2 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [PROB] | PROB | P1 | Mapped |
| C2 [FACT] | FACT | P1 | Mapped |
| C3 [GOAL] | GOAL | FR1 | Mapped |
| C4 [PROB] | PROB | P2 | Mapped |
| C5 [GOAL] | GOAL | FR2 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

AC1: Are markdown artifact files rendered as formatted HTML (not raw text) in all artifact content sections? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse: "shown as raw text" -> "rendered as formatted HTML")
  Belongs to: P1
  Source clauses: [C1, C2]

AC2: Are headings, lists, and code blocks rendered correctly in markdown artifact content? YES = pass, NO = fail
  Origin: Derived from C2 [FACT] (operationalized: previously working elements verified)
  Belongs to: P1
  Source clauses: [C2]

AC3: Does expanding an artifact section avoid pushing or overlapping the right column (plan tasks, completion history)? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse: "pushes or overlaps" -> "avoids pushing or overlapping")
  Belongs to: P2
  Source clauses: [C4]

AC4: Does the right column remain fully visible and correctly positioned when an artifact section is expanded? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse: "takes full page width" -> "right column remains visible")
  Belongs to: P2
  Source clauses: [C4]

AC5: Does the system convert markdown to rendered HTML in every artifact content section? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized: "restore markdown rendering" -> verified per section)
  Belongs to: FR1
  Source clauses: [C3]

AC6: Are all standard markdown elements (headings, lists, code blocks, emphasis, links) rendered correctly? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized: "all artifact content sections" -> element-level verification)
  Belongs to: FR1
  Source clauses: [C3, C2]

AC7: Does expanded artifact content stay within its designated column width? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: "stay within its column" -> column width constraint verified)
  Belongs to: FR2
  Source clauses: [C5]

AC8: Does expanding or collapsing artifact content leave the sidebar layout unaffected? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: "not affect the sidebar layout" -> sidebar unchanged on toggle)
  Belongs to: FR2
  Source clauses: [C5]

AC9: Does content that exceeds the column width handle overflow gracefully (e.g., scrolling or wrapping) without breaking the layout? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: implicit edge case from column constraint)
  Belongs to: FR2
  Source clauses: [C5]

## Requirement -> AC Coverage
| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2 | 2 |
| P2 | AC3, AC4 | 2 |
| FR1 | AC5, AC6 | 2 |
| FR2 | AC7, AC8, AC9 | 3 |

## Clause -> AC Coverage
| Clause | Type | AC | How |
|---|---|---|---|
| C1 | PROB | AC1 | Inverse ("raw text" -> "rendered as HTML") |
| C2 | FACT | AC2, AC6 | Operationalized (previously working elements verified); C2 provides no testable requirement on its own -- it supplies context for what "rendered" means, consumed by AC2 and AC6 |
| C3 | GOAL | AC5, AC6 | Made testable ("restore rendering" -> per-section and per-element checks) |
| C4 | PROB | AC3, AC4 | Inverse ("pushes/overlaps" -> "avoids pushing/overlapping", "right column remains visible") |
| C5 | GOAL | AC7, AC8, AC9 | Made testable ("stay within column, not affect sidebar" -> width constraint, sidebar stability, overflow handling) |
