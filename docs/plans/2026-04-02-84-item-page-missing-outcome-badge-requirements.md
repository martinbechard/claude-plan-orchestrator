# Structured Requirements: 84 Item Page Missing Outcome Badge

Source: tmp/plans/.claimed/84-item-page-missing-outcome-badge.md
Generated: 2026-04-02T18:25:35.767816+00:00

## Requirements

### P1: Outcome badge missing from work item detail page
Type: UI
Priority: high
Source clauses: [C2, C5]
Description: The work item detail page does not display the outcome (success/warn/fail) from the completion record. Users visiting the page see status badges but have no visual indication of the final outcome, leaving them unable to determine at a glance whether the item succeeded, warned, or failed.
Acceptance Criteria:
- Does the work item detail page display the outcome (success/warn/fail) from the completion record? YES = pass, NO = fail
- Is the outcome badge visible on the work item detail page when a completion record exists? YES = pass, NO = fail

### P2: Badge rendering logic does not retrieve or display outcome data
Type: functional
Priority: high
Source clauses: [C11, C12]
Description: The completion record contains outcome data, but the badge rendering logic does not currently retrieve or display it. This is the implementation gap that causes the outcome to be absent from the status badge list despite the data being available in the system.
Acceptance Criteria:
- Does the badge rendering logic retrieve the outcome field from the completion record? YES = pass, NO = fail
- Does the badge rendering logic render the retrieved outcome as a visible badge? YES = pass, NO = fail

### UC1: User views work item outcome at a glance
Type: UI
Priority: high
Source clauses: [C4, C6]
Description: Users need to immediately see how a work item finished when viewing the work item detail page. The outcome should be visible without requiring additional clicks, scrolling, or investigation — a single glance at the status badge area should communicate the final result.
Acceptance Criteria:
- Can a user determine the outcome (success/warn/fail) of a work item immediately upon viewing the detail page? YES = pass, NO = fail
- Is the outcome visible without additional navigation or interaction beyond loading the page? YES = pass, NO = fail

### FR1: Display outcome as first badge in status badge list
Type: UI
Priority: high
Source clauses: [C1, C3, C7, C8]
Description: The outcome badge (success/warn/fail) must appear as the first badge in the existing status badge list on the work item detail page. The work item detail page already shows status badges; the outcome badge must be prepended to this list so it serves as the primary visual indicator. Appearing first ensures users see the final result before other status details.
Acceptance Criteria:
- Is the outcome badge rendered as the first item in the status badge list? YES = pass, NO = fail
- Does the outcome badge appear before all other status badges? YES = pass, NO = fail
- Does the badge display one of the three outcome values: success, warn, or fail? YES = pass, NO = fail

### FR2: Outcome badge is the primary visual indicator of work item result
Type: UI
Priority: medium
Source clauses: [C7, C9]
Description: The outcome (success/warn/fail) is the most important status signal for understanding whether work succeeded. The outcome badge must be visually prominent — serving as the primary visual indicator — so that it stands out from other badges in the list and communicates the completion result as the dominant status signal.
Acceptance Criteria:
- Is the outcome badge visually distinguishable from other status badges (e.g., via color, icon, or emphasis)? YES = pass, NO = fail
- Does the outcome badge convey the most important status signal (success/warn/fail) more prominently than secondary badges? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "shows status badges but does not display the outcome (success/warn/fail) from the completion record" | P1, P2, FR1 |
| "The outcome should appear as the first badge in the status badge list" | FR1 |
| "so users can immediately see how the item finished" | UC1 |
| W2: "Users need to immediately see how the item finished" | UC1 |
| W3: "The outcome should be the primary visual indicator—appearing first in the status badge list ensures users see the final result before other status details" | FR1, FR2 |
| W4: "The outcome (success/warn/fail) is the most important status signal for understanding whether work succeeded" | FR2 |
| W5: "The completion record contains outcome data, but the badge rendering logic doesn't currently retrieve or display it" | P2 |
| Root Need: "Provide immediate visual feedback on work item completion outcomes so users can assess success/failure at a glance" | UC1 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [FACT] | FACT | FR1 | Mapped — establishes existing badge list context |
| C2 [PROB] | PROB | P1 | Mapped |
| C3 [GOAL] | GOAL | FR1 | Mapped |
| C4 [GOAL] | GOAL | UC1 | Mapped |
| C5 [PROB] | PROB | P1 | Mapped |
| C6 [GOAL] | GOAL | UC1 | Mapped |
| C7 [GOAL] | GOAL | FR1, FR2 | Mapped |
| C8 [CONS] | CONS | FR1 | Mapped — constraint informing badge ordering |
| C9 [GOAL] | GOAL | FR2 | Mapped |
| C10 [CTX] | CTX | -- | Unmapped: assumption context only, not actionable |
| C11 [FACT] | FACT | P2 | Mapped — establishes data availability |
| C12 [PROB] | PROB | P2 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

AC1: Does the work item detail page display an outcome badge (success/warn/fail) when a completion record exists? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse: "does not display the outcome" → "does it display the outcome?")
  Belongs to: P1
  Source clauses: [C2, C5]

AC2: Does the badge rendering logic retrieve the outcome field from the completion record? YES = pass, NO = fail
  Origin: Derived from C12 [PROB] (inverse: "doesn't currently retrieve or display it" → "does it retrieve it?")
  Belongs to: P2
  Source clauses: [C11, C12]

AC3: Does the badge rendering logic render the retrieved outcome as a visible badge? YES = pass, NO = fail
  Origin: Derived from C12 [PROB] (inverse: rendering half of "doesn't currently retrieve or display it")
  Belongs to: P2
  Source clauses: [C12]

AC4: Can a user determine the outcome (success/warn/fail) of a work item immediately upon viewing the detail page, without additional clicks, scrolling, or navigation? YES = pass, NO = fail
  Origin: Derived from C4 [GOAL] and C6 [GOAL] (operationalized: "immediately see how the item finished" → verifiable glance test)
  Belongs to: UC1
  Source clauses: [C4, C6]

AC5: Is the outcome badge rendered as the first item in the status badge list, appearing before all other status badges? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized: "should appear as the first badge" → positional check)
  Belongs to: FR1
  Source clauses: [C1, C3, C8]

AC6: Does the outcome badge display one of exactly three values: success, warn, or fail? YES = pass, NO = fail
  Origin: Derived from C7 [GOAL] (operationalized: "primary visual indicator" requires correct value set)
  Belongs to: FR1
  Source clauses: [C3, C7]

AC7: Is the outcome badge visually distinguishable from other status badges (e.g., via color, icon, size, or emphasis)? YES = pass, NO = fail
  Origin: Derived from C7 [GOAL] and C9 [GOAL] (operationalized: "primary visual indicator" and "most important status signal" → visual prominence check)
  Belongs to: FR2
  Source clauses: [C7, C9]

AC8: Does the outcome badge convey the completion result more prominently than secondary status badges in the list? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized: "most important status signal" → comparative prominence check)
  Belongs to: FR2
  Source clauses: [C9]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1 | 1 |
| P2 | AC2, AC3 | 2 |
| UC1 | AC4 | 1 |
| FR1 | AC5, AC6 | 2 |
| FR2 | AC7, AC8 | 2 |

---

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | FACT | AC5 | Context — establishes the existing badge list that AC5 verifies position within |
| C2 | PROB | AC1 | Inverse ("does not display" → "does it display?") |
| C3 | GOAL | AC5, AC6 | Made testable (position and value constraints) |
| C4 | GOAL | AC4 | Made testable ("immediately see" → glance-test question) |
| C5 | PROB | AC1 | Inverse (synonym of C2, co-sourced) |
| C6 | GOAL | AC4 | Made testable (co-sourced with C4) |
| C7 | GOAL | AC6, AC7 | Made testable (correct values + visual prominence) |
| C8 | CONS | AC5 | Constraint encoded in positional check |
| C9 | GOAL | AC7, AC8 | Made testable ("most important signal" → prominence comparison) |
| C10 | CTX | -- | Assumption context only; provides rationale for prioritization but is not itself testable. Informs AC4/AC5 indirectly. |
| C11 | FACT | AC2 | Establishes data availability; AC2 verifies retrieval of the data C11 asserts exists. |
| C12 | PROB | AC2, AC3 | Inverse ("doesn't retrieve or display" → "does it retrieve?" + "does it render?") |
