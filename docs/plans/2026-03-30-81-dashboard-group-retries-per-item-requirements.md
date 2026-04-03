# Structured Requirements: 81 Dashboard Group Retries Per Item

Source: tmp/plans/.claimed/81-dashboard-group-retries-per-item.md
Generated: 2026-03-30T16:56:48.029027+00:00

## Requirements

I'll analyze the three specific rejections and trace the correct clause attributions from the raw input.

**Rejection 1 — FR1 [C2, C4, C5] → [C4, C5]:** C2 is the factual detail "(warn + success)" — a description of row contents, not a goal driving the grouping requirement. The Root Need says "a grouping mechanism that displays retried items as a single entry with the final outcome [C4, C5]" — those two clauses are the direct sources.

**Rejection 2 — UC1 [C4, C7] → [C6, C7]:** C4 is "single entry with final outcome" — that's the grouping display (FR1's territory). UC1 is about *inspecting retry history*, which maps to C6 ("retry history accessible on demand") and C7 ("expandable row or tooltip showing previous attempts").

**Rejection 3 — P2 [C6] → [C1, C3]:** C6 is about feature availability ("accessible on demand"), not the distinguishability problem. The inability to distinguish retried items from separate items stems from C1 (each execution as an independent row) and C3 (rows "look like duplicate entries" — i.e., visually indistinguishable from separate items). W2 and W5 describe this problem and trace it back to these structural/perceptual facts.

---

### P1: Retried items appear as duplicate rows in completions table
Type: UI
Priority: high
Source clauses: [C1, C3, C5]
Description: When an item fails with outcome=warn and is retried, the completions table shows two separate rows (e.g., warn + success) that look like duplicate entries. This is caused by the current table structure treating each execution as an independent row, with no visual or structural indication that two rows represent the same item at different retry stages.
Acceptance Criteria:
- When an item has been retried, does the default completions table view show only ONE row per item (not one per attempt)? YES = pass, NO = fail
- Is the final outcome (e.g., success) the prominently displayed status for a retried item? YES = pass, NO = fail

### P2: Cannot distinguish retried items from separate items
Type: UI
Priority: high
Source clauses: [C1, C3]
Description: The flat-row layout provides no context to differentiate between an item that was retried (same item, multiple executions) and genuinely separate items. Because each execution is treated as an independent row [C1] and retried items look like duplicate entries [C3], users must mentally correlate item names or IDs to determine whether two rows are related, which is error-prone and time-consuming.
Acceptance Criteria:
- Can a user visually distinguish a retried item (grouped entry) from two separate items at a glance, without reading item IDs or names? YES = pass, NO = fail

### P3: Dashboard clarity and traceability undermined by duplicate-row presentation
Type: UI
Priority: medium
Source clauses: [C1, C2, C3]
Description: The duplicate-row presentation for retried items undermines overall dashboard clarity and traceability. Users lose confidence in the dashboard as a source of truth when the same logical item appears multiple times, making it harder to assess the true state of the pipeline at a glance.
Acceptance Criteria:
- After grouping is implemented, does the completions table present a clear, non-redundant view where each logical item appears exactly once in the default view? YES = pass, NO = fail
- Is the total item count in the dashboard accurate (counting logical items, not individual execution attempts)? YES = pass, NO = fail

### FR1: Group retry attempts hierarchically under a single item entry
Type: functional
Priority: high
Source clauses: [C4, C5]
Description: The dashboard must be redesigned to hierarchically group retry attempts under a single visual item entry. The system should detect when multiple executions belong to the same item (via retry relationship) and collapse them into a single row. The final outcome must be displayed prominently as the item's status. This grouping mechanism must show retried items as a single entry with the final outcome by default, while keeping the retry history (previous failed attempts) accessible without cluttering the main view. The suggested UX patterns include an expandable row or a tooltip showing previous attempts.
Acceptance Criteria:
- Does the system automatically detect and group executions that are retries of the same item? YES = pass, NO = fail
- Is the grouped row's displayed outcome the FINAL attempt's outcome (not the first or worst)? YES = pass, NO = fail
- Does the main completions table default to collapsed/grouped view (one row per item)? YES = pass, NO = fail
- Are items that were never retried displayed identically to before (no empty expand controls or visual noise)? YES = pass, NO = fail

### UC1: User inspects retry history on demand
Type: UI
Priority: high
Source clauses: [C6, C7]
Description: A user viewing the completions table can access the full retry history for any retried item on demand, without the retry history cluttering the default view. The retry history provides necessary context for understanding the item's complete journey and failure causes. The interaction mechanism (e.g., expandable row, tooltip, or detail panel) should reveal all previous attempts, including their outcomes (e.g., warn), timestamps, and any relevant diagnostic information. This allows users to debug issues and understand what happened during prior attempts.
Acceptance Criteria:
- Can a user reveal the retry history for a grouped item via a single interaction (click/expand)? YES = pass, NO = fail
- Does the expanded retry history show the outcome of each previous attempt? YES = pass, NO = fail
- Is the retry history hidden by default so it does not clutter the main table view? YES = pass, NO = fail
- After expanding, can the user collapse the retry history back to the grouped single-row view? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "When an item fails with outcome=warn and is retried, the completions table shows two separate rows (warn + success) that look like duplicate entries" | P1, P2 |
| "The dashboard should group retry attempts under a single item, showing the final outcome prominently" | FR1 |
| "with the retry history accessible on demand (e.g. expandable row or tooltip showing previous attempts)" | UC1 |
| W1: Two separate rows for retried items | P1 |
| W2: Rows look like duplicate entries, creating confusion | P1, P2 |
| W3: Final outcome shown prominently, retry history accessible on demand | FR1, UC1 |
| W4: Retry history necessary for understanding item journey and failure causes | UC1 |
| W5: Current flat-row design makes it impossible to distinguish separate vs. retried items | P2, P3 |
| Root Need: Grouping mechanism with final outcome and accessible retry history without cluttering main view | FR1, UC1, P3 |
| Summary: Hierarchically group retry attempts, final outcomes by default, inspect history on demand | FR1, UC1 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 | FACT | P1, P2, P3 | Mapped — structural cause: each execution as independent row; drives the duplicate-row and distinguishability problems |
| C2 | FACT | P3 | Mapped — factual detail (warn + success outcomes) contributing to clarity/traceability concern |
| C3 | PROB | P1, P2, P3 | Mapped — perceptual problem: rows look like duplicates, making retried items indistinguishable from separate items |
| C4 | CONS | FR1 | Mapped — constraint requiring retried items displayed as single entry |
| C5 | FACT | P1, FR1 | Mapped — final outcome prominence as factual basis and grouping requirement |
| C6 | GOAL | UC1 | Mapped — retry history accessible on demand without cluttering the view |
| C7 | GOAL | UC1 | Mapped — expandable row / tooltip mechanism for retry history |

## Validation

Status: ACCEPTED
Iterations: 3
Reviewer notes: ACCEPT


## Acceptance Criteria

AC1: When an item has been retried, does the default completions table view show only one row per logical item (not one per execution attempt)? YES = pass, NO = fail
  Origin: Derived from C3 [PROB] (inverse: "look like duplicate entries" → "single non-duplicate row per item")
  Belongs to: P1
  Source clauses: [C1, C3]

AC2: Is the final attempt's outcome (e.g., success) displayed as the grouped row's primary status, not the first or worst attempt's outcome? YES = pass, NO = fail
  Origin: Derived from C2 [GOAL] (operationalized: "showing the final outcome prominently")
  Belongs to: P1
  Source clauses: [C2, C5]

AC3: Can a user visually distinguish a retried item (grouped entry) from two separate unrelated items at a glance, without manually correlating item names or IDs? YES = pass, NO = fail
  Origin: Derived from C6 [PROB] (inverse: "impossible to distinguish" → "distinguishable at a glance")
  Belongs to: P2
  Source clauses: [C1, C3, C6]

AC4: Does the UI provide a visual indicator (e.g., retry badge, attempt count, or expand affordance) that signals an item was retried? YES = pass, NO = fail
  Origin: Derived from C6 [PROB] (inverse: "impossible to distinguish without context" → "context provided via visual indicator")
  Belongs to: P2
  Source clauses: [C6]

AC5: After grouping is implemented, does the completions table present a non-redundant view where each logical item appears exactly once in the default view? YES = pass, NO = fail
  Origin: Derived from C8 [PROB] (inverse: "undermines dashboard clarity" → "clear, non-redundant default view")
  Belongs to: P3
  Source clauses: [C8]

AC6: Is the total item count in the dashboard accurate, counting logical items rather than individual execution attempts? YES = pass, NO = fail
  Origin: Derived from C8 [PROB] (inverse: "undermines traceability" → "accurate counts reflecting logical items")
  Belongs to: P3
  Source clauses: [C1, C8]

AC7: Does the system automatically detect and group executions that are retries of the same item into a single row? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized: "hierarchically group retry attempts under a single visual item")
  Belongs to: FR1
  Source clauses: [C5, C9]

AC8: Does the main completions table default to a collapsed/grouped view showing one row per logical item? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized: "showing final outcomes by default")
  Belongs to: FR1
  Source clauses: [C9]

AC9: Are items that were never retried displayed without empty expand controls, retry badges, or other visual noise? YES = pass, NO = fail
  Origin: Derived from C7 [GOAL] (operationalized: "without cluttering the main view" — non-retried items must be unaffected)
  Belongs to: FR1
  Source clauses: [C7]

AC10: Can a user reveal the retry history for a grouped item via a single interaction (e.g., click to expand)? YES = pass, NO = fail
  Origin: Derived from C7 [GOAL] (operationalized: "retry history accessible on demand")
  Belongs to: UC1
  Source clauses: [C7]

AC11: Does the expanded retry history show the outcome of each previous attempt? YES = pass, NO = fail
  Origin: Derived from C4 [CONS] (operationalized: "necessary context for understanding the item's complete journey")
  Belongs to: UC1
  Source clauses: [C4]

AC12: Does the expanded retry history show the timestamp of each previous attempt? YES = pass, NO = fail
  Origin: Derived from C4 [CONS] (operationalized: "necessary context for understanding failure causes" — temporal ordering required for journey reconstruction)
  Belongs to: UC1
  Source clauses: [C4]

AC13: Is the retry history hidden by default so it does not clutter the main table view? YES = pass, NO = fail
  Origin: Derived from C7 [GOAL] (operationalized: "without cluttering the main view")
  Belongs to: UC1
  Source clauses: [C7]

AC14: After expanding retry history, can the user collapse it back to the grouped single-row view? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized: "inspect the retry history on demand" — on-demand implies togglable expand/collapse)
  Belongs to: UC1
  Source clauses: [C9]

## Requirement -> AC Coverage
| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2 | 2 |
| P2 | AC3, AC4 | 2 |
| P3 | AC5, AC6 | 2 |
| FR1 | AC7, AC8, AC9 | 3 |
| UC1 | AC10, AC11, AC12, AC13, AC14 | 5 |

## Clause -> AC Coverage
| Clause | Type | AC | How |
|---|---|---|---|
| C1 | FACT | AC1, AC3, AC6 | Source context — C1 describes the broken state (two separate rows); its inverse is directly captured by AC1 (single row per item). Not independently testable as a standalone AC because C1 states the current behavior, not a requirement. |
| C2 | GOAL | AC2 | Operationalized: "showing the final outcome prominently" → final attempt's outcome is the displayed status |
| C3 | PROB | AC1, AC3 | Inverse: "look like duplicate entries" → single non-duplicate row (AC1); "creating confusion" → visually distinguishable (AC3) |
| C4 | CONS | AC11, AC12 | Operationalized: "necessary context for understanding journey and failure causes" → outcomes and timestamps of each attempt shown |
| C5 | FACT | AC2, AC7 | Source context — C5 describes the structural cause (independent rows); its inverse is captured by AC7 (automatic grouping). Like C1, it states current architecture, not a requirement. |
| C6 | PROB | AC3, AC4 | Inverse: "impossible to distinguish" → distinguishable at a glance (AC3); visual indicator provided (AC4) |
| C7 | GOAL | AC9, AC10, AC13 | Operationalized: "single entry without cluttering" → no noise on non-retried items (AC9); "accessible on demand" → single-interaction expand (AC10); "without cluttering" → hidden by default (AC13) |
| C8 | PROB | AC5, AC6 | Inverse: "undermines clarity" → non-redundant view (AC5); "undermines traceability" → accurate item counts (AC6) |
| C9 | GOAL | AC7, AC8, AC14 | Operationalized: "hierarchically group" → auto-detect and group (AC7); "final outcomes by default" → collapsed default (AC8); "on demand" → collapsible back (AC14) |
