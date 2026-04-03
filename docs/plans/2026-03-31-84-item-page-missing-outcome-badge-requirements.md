# Structured Requirements: 84 Item Page Missing Outcome Badge

Source: tmp/plans/.claimed/84-item-page-missing-outcome-badge.md
Generated: 2026-03-31T21:06:50.715009+00:00

## Requirements

### P1: Outcome not displayed on work item detail page
Type: UI
Priority: high
Source clauses: [C2, C11]
Description: The work item detail page does not display the outcome (success/warn/fail) from the completion record. The badge rendering logic does not currently retrieve or display the outcome data, even though the completion record contains it.
Acceptance Criteria:
- Does the work item detail page display the outcome (success/warn/fail) from the completion record? YES = pass, NO = fail
- Does the badge rendering logic retrieve outcome data from the completion record? YES = pass, NO = fail

### UC1: User sees how a work item finished at a glance
Type: UI
Priority: high
Source clauses: [C4, C5, C14]
Description: Users need to immediately see how a work item finished (succeeded, warned, or failed) without additional investigation. When viewing a work item detail page, the completion outcome must be visible at a glance so users can assess success or failure instantly.
Acceptance Criteria:
- Can a user determine whether a work item succeeded, warned, or failed by glancing at the detail page without clicking or scrolling? YES = pass, NO = fail
- Is the outcome visible without requiring additional investigation beyond opening the work item detail page? YES = pass, NO = fail

### FR1: Display outcome as the first status badge
Type: UI
Priority: high
Source clauses: [C3, C6, C13, C15, C16]
Description: The system must render the work item completion outcome (success/warn/fail) as a badge and position it as the first badge in the status badge list. The outcome badge must serve as the primary visual indicator, appearing before all other status badges, to provide immediate visual feedback on how the item finished. The three outcome states to support are: succeeded, warned, and failed.
Acceptance Criteria:
- Does the outcome badge appear as the first badge in the status badge list? YES = pass, NO = fail
- Does the outcome badge render for all three states: success, warn, and fail? YES = pass, NO = fail
- Is the outcome badge visually distinct as the primary status indicator (positioned before other status details)? YES = pass, NO = fail
- Does the system provide immediate visual feedback on work item completion outcomes? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "does not display the outcome (success/warn/fail) from the completion record" | P1 |
| "the badge rendering logic doesn't currently retrieve or display it" | P1 |
| "users can immediately see how the item finished" | UC1 |
| "users can assess success/failure at a glance without additional investigation" | UC1 |
| "The outcome should appear as the first badge in the status badge list" | FR1 |
| "The outcome should be the primary visual indicator" | FR1 |
| "Provide immediate visual feedback on work item completion outcomes" | FR1 |
| "Display work item completion outcome as the first status badge" | FR1 |
| "give users immediate visibility into whether items succeeded, warned, or failed" | FR1 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 | FACT | -- | Unmapped: background context establishing that status badges already exist |
| C2 | PROB | P1 | Mapped |
| C3 | GOAL | FR1 | Mapped |
| C4 | GOAL | UC1 | Mapped |
| C5 | GOAL | UC1 | Mapped |
| C6 | GOAL | FR1 | Mapped |
| C7 | CONS | -- | Unmapped: design rationale justifying first-position placement (captured in FR1 description) |
| C8 | CONS | -- | Unmapped: design rationale justifying outcome importance (captured in UC1 and FR1 descriptions) |
| C9 | CTX | -- | Unmapped: assumption about user research providing background motivation |
| C10 | FACT | -- | Unmapped: background context establishing that outcome data exists in completion records |
| C11 | PROB | P1 | Mapped |
| C12 | CTX | -- | Unmapped: assumption about why the gap exists; context only |
| C13 | GOAL | FR1 | Mapped |
| C14 | GOAL | UC1 | Mapped |
| C15 | GOAL | FR1 | Mapped |
| C16 | GOAL | FR1 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT
