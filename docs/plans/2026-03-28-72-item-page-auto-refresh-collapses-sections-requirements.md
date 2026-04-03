# Structured Requirements: 72 Item Page Auto Refresh Collapses Sections

Source: tmp/plans/.claimed/72-item-page-auto-refresh-collapses-sections.md
Generated: 2026-03-28T22:23:59.868089+00:00

## Requirements

### P1: Expanded content sections collapse on auto-refresh
Type: UI
Priority: high
Source clauses: [C2, C1, C5, C7]
Description: The work item detail page uses a meta http-equiv refresh tag that reloads the entire page every 10 seconds while the item is being processed. This makes it impossible to read expanded content sections (raw input, clause register, 5 whys, structured requirements, design, validation reports) because they collapse back to their closed state every time the page reloads. The current implementation is a simple full-page meta refresh in the HTML head, which reloads all content rather than selectively updating elements.
Acceptance Criteria:
- Do expanded details/summary sections remain open across refresh cycles? YES = pass, NO = fail
- Can a user read a long content section without it collapsing within the 10-second refresh interval? YES = pass, NO = fail

### P2: Full-page reload destroys DOM state for all elements
Type: UI
Priority: high
Source clauses: [C10, C12]
Description: The full-page reload mechanism destroys DOM state for all elements, including the open/closed state of details/summary sections. Any user interaction state (scroll position within sections, expanded panels) is lost every 10 seconds, making the page effectively unusable for reading content while an item is being processed.
Acceptance Criteria:
- Is the open/closed state of all details/summary elements preserved across refresh cycles? YES = pass, NO = fail
- Does the refresh mechanism avoid replacing or re-rendering static DOM elements? YES = pass, NO = fail

### UC1: Read and interact with expanded content sections during auto-refresh
Type: UI
Priority: high
Source clauses: [C15]
Description: Users must be able to expand and read content sections (raw input, clause register, 5 whys, structured requirements, design, validation reports) while the page auto-refreshes to show current processing state. The user's interaction with static content sections must not be interrupted by the mechanism that keeps dynamic status information current.
Acceptance Criteria:
- Can a user expand a content section, read it for more than 10 seconds, and find it still expanded? YES = pass, NO = fail
- Does the status badge continue to update while the user is reading an expanded section? YES = pass, NO = fail

### FR1: Selective refresh of dynamic elements only
Type: functional
Priority: high
Source clauses: [C3, C4, C8, C11]
Description: The page must refresh only the dynamic parts -- status badge, cost, duration, worker info, and token counts -- without reloading the static content sections (raw input, clause register, 5 whys, structured requirements, design, validation reports). The content sections do not change during the refresh interval, so there is no reason to reload them. The dynamic elements change as the item is being processed and must be updated to reflect current state.
Acceptance Criteria:
- Are the following dynamic elements updated on each refresh cycle: status badge, cost, duration, worker info, token counts? YES = pass, NO = fail
- Are the following static sections left untouched on each refresh cycle: raw input, clause register, 5 whys, structured requirements, design, validation reports? YES = pass, NO = fail
- Does the refresh interval remain approximately 10 seconds? YES = pass, NO = fail

### FR2: Replace meta refresh with JavaScript fetch-based updates
Type: refactoring
Priority: high
Source clauses: [C6, C13, C14]
Description: Replace the current full-page meta http-equiv refresh in the HTML head with a JavaScript fetch that updates only the dynamic elements and leaves the rest of the DOM (including details/summary open state) intact. Selective updates via JavaScript fetch must preserve the DOM structure and state while only modifying content that actually changed. This assumes JavaScript fetch is technically feasible without a full page reload (standard browser capability).
Acceptance Criteria:
- Has the meta http-equiv refresh tag been removed from the HTML head? YES = pass, NO = fail
- Does a JavaScript fetch call retrieve updated dynamic data from the server? YES = pass, NO = fail
- Does the JavaScript update only the dynamic element contents without replacing surrounding DOM nodes? YES = pass, NO = fail
- Is the details/summary open state preserved after a fetch-based update? YES = pass, NO = fail

### FR3: Decouple DOM structure preservation from content updates
Type: refactoring
Priority: medium
Source clauses: [C16, C9]
Description: The implementation must architecturally decouple DOM structure preservation (static sections) from content updates (dynamic elements). Static sections should be treated as inert DOM that is never touched by the refresh mechanism, while dynamic elements should be explicitly targeted for update. This separation eliminates the wasteful reloading of unchanged content and ensures the two concerns do not interfere with each other.
Acceptance Criteria:
- Are static content sections identified and excluded from the update mechanism? YES = pass, NO = fail
- Are dynamic elements explicitly enumerated and targeted by the update mechanism? YES = pass, NO = fail
- Can new dynamic elements be added to the update list without affecting static sections? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "The work item detail page uses a meta http-equiv refresh tag that reloads the entire page every 10 seconds while the item is being processed" | P1 |
| "This makes it impossible to read expanded content sections because they collapse back every time the page reloads" | P1, P2, UC1 |
| "The page should only refresh the dynamic parts (status badge, cost, duration, worker info, token counts) without reloading the static content sections (raw input, clause register, 5 whys, structured requirements, design, validation reports)" | FR1 |
| "The content sections don't change during the refresh interval so there's no reason to reload them" | FR1, FR3 |
| "The current implementation is a full-page meta refresh in the HTML head" | P1, FR2 |
| "Replace it with a JavaScript fetch that updates only the dynamic elements and leaves the rest of the DOM (including details/summary open state) intact" | FR2 |
| 5 Whys root need: "Enable users to read and interact with expanded content sections while the page auto-refreshes" | UC1 |
| 5 Whys root need: "by decoupling DOM structure preservation (static sections) from content updates (dynamic elements)" | FR3 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 | FACT | P1 | Mapped: provides context for the problem |
| C2 | PROB | P1, UC1 | Mapped |
| C3 | GOAL | FR1 | Mapped |
| C4 | FACT | FR1 | Mapped: justifies why static sections should not refresh |
| C5 | FACT | P1, FR2 | Mapped: describes current implementation being replaced |
| C6 | GOAL | FR2 | Mapped |
| C7 | FACT | P1 | Mapped: elaborates on the current implementation behavior |
| C8 | FACT | FR1 | Mapped: reinforces static nature of content sections |
| C9 | CTX | FR3 | Mapped: motivates the decoupling approach |
| C10 | PROB | P2 | Mapped |
| C11 | FACT | FR1 | Mapped: identifies which elements must be updated |
| C12 | CONS | P2 | Mapped: explains the technical cause of DOM state loss |
| C13 | GOAL | FR2 | Mapped |
| C14 | CONS | FR2 | Mapped: acknowledged assumption about JS fetch feasibility |
| C15 | GOAL | UC1 | Mapped |
| C16 | GOAL | FR3 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

**AC1:** Do expanded details/summary sections remain in their open state across refresh cycles? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse: "impossible to read expanded content because they collapse" -> "do they remain open?")
  Belongs to: P1
  Source clauses: [C2, C1]

**AC2:** Is the open/closed state of all details/summary elements preserved after each refresh cycle? YES = pass, NO = fail
  Origin: Derived from C10 [PROB] (inverse: "destroys the DOM state (open/closed details sections)" -> "is DOM state preserved?")
  Belongs to: P2
  Source clauses: [C10, C12]

**AC3:** Does the refresh mechanism avoid replacing or re-rendering static DOM elements? YES = pass, NO = fail
  Origin: Derived from C12 [CONS] (operationalized: if full-page reload destroys DOM state, the fix must not replace static DOM)
  Belongs to: P2
  Source clauses: [C12, C10]

**AC4:** Can a user expand a content section, read it for more than 10 seconds, and find it still expanded? YES = pass, NO = fail
  Origin: Derived from C15 [GOAL] (operationalized: "read and interact with expanded content sections while the page auto-refreshes")
  Belongs to: UC1
  Source clauses: [C15, C2]

**AC5:** Does the status badge continue to update while the user is reading an expanded section? YES = pass, NO = fail
  Origin: Derived from C15 [GOAL] (operationalized: "while the page auto-refreshes to show current processing state")
  Belongs to: UC1
  Source clauses: [C15, C11]

**AC6:** Are the following dynamic elements updated on each refresh cycle: status badge, cost, duration, worker info, token counts? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized: "refresh the dynamic parts (status badge, cost, duration, worker info, token counts)")
  Belongs to: FR1
  Source clauses: [C3, C11]

**AC7:** Are the following static sections left untouched on each refresh cycle: raw input, clause register, 5 whys, structured requirements, design, validation reports? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized: "without reloading the static content sections")
  Belongs to: FR1
  Source clauses: [C3, C4, C8]

**AC8:** Does the refresh interval remain approximately 10 seconds? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized: preserving the existing refresh cadence specified in C1)
  Belongs to: FR1
  Source clauses: [C3, C1]

**AC9:** Has the meta http-equiv refresh tag been removed from the HTML head? YES = pass, NO = fail
  Origin: Derived from C6 [GOAL] (operationalized: "Replace it with a JavaScript fetch")
  Belongs to: FR2
  Source clauses: [C6, C5, C7]

**AC10:** Does a JavaScript fetch call retrieve updated dynamic data from the server? YES = pass, NO = fail
  Origin: Derived from C6 [GOAL] (operationalized: "a JavaScript fetch that updates only the dynamic elements")
  Belongs to: FR2
  Source clauses: [C6, C14]

**AC11:** Does the JavaScript update only the dynamic element contents without replacing surrounding DOM nodes? YES = pass, NO = fail
  Origin: Derived from C13 [GOAL] (operationalized: "preserve the DOM structure and state while only modifying content that actually changed")
  Belongs to: FR2
  Source clauses: [C13, C6]

**AC12:** Is the details/summary open state preserved after a fetch-based update? YES = pass, NO = fail
  Origin: Derived from C13 [GOAL] (operationalized: "leaves the rest of the DOM (including details/summary open state) intact")
  Belongs to: FR2
  Source clauses: [C13, C6]

**AC13:** Are static content sections identified and excluded from the update mechanism? YES = pass, NO = fail
  Origin: Derived from C16 [GOAL] (operationalized: "decoupling DOM structure preservation (static sections)")
  Belongs to: FR3
  Source clauses: [C16, C9]

**AC14:** Are dynamic elements explicitly enumerated and targeted by the update mechanism? YES = pass, NO = fail
  Origin: Derived from C16 [GOAL] (operationalized: "content updates (dynamic elements)" as an explicit, bounded list)
  Belongs to: FR3
  Source clauses: [C16]

**AC15:** Can new dynamic elements be added to the update list without affecting static sections? YES = pass, NO = fail
  Origin: Derived from C16 [GOAL] (operationalized: decoupling implies the two concerns are independently extensible)
  Belongs to: FR3
  Source clauses: [C16, C9]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1 | 1 |
| P2 | AC2, AC3 | 2 |
| UC1 | AC4, AC5 | 2 |
| FR1 | AC6, AC7, AC8 | 3 |
| FR2 | AC9, AC10, AC11, AC12 | 4 |
| FR3 | AC13, AC14, AC15 | 3 |

---

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | FACT | AC1, AC8 | Provides context (refresh interval and mechanism) used to define testable conditions |
| C2 | PROB | AC1, AC4 | Inverse: "collapse back" -> "remain open" |
| C3 | GOAL | AC6, AC7, AC8 | Made testable: dynamic elements updated, static sections untouched, interval preserved |
| C4 | FACT | AC7 | Justifies excluding static sections; tested via AC7 ("left untouched") |
| C5 | FACT | AC9 | Describes artifact to remove; tested via AC9 ("meta refresh tag removed") |
| C6 | GOAL | AC9, AC10, AC11, AC12 | Made testable: meta removed, fetch retrieves data, targeted update, open state preserved |
| C7 | FACT | AC9 | Elaborates on C5 (same artifact); covered by AC9 |
| C8 | FACT | AC7 | Reinforces C4 (static nature); covered by AC7 |
| C9 | CTX | AC13, AC15 | Motivates decoupling; not independently testable but shapes FR3 criteria |
| C10 | PROB | AC2 | Inverse: "destroys DOM state" -> "DOM state preserved" |
| C11 | FACT | AC5, AC6 | Identifies which elements must update; tested via AC6 (enumerated list) and AC5 (status badge specifically) |
| C12 | CONS | AC2, AC3 | Explains technical cause; inverse tested via AC2 (state preserved) and AC3 (static DOM not replaced) |
| C13 | GOAL | AC11, AC12 | Made testable: targeted update without DOM replacement, open state preserved |
| C14 | CONS | AC10 | Assumption validated: if AC10 passes, JS fetch is confirmed feasible |
| C15 | GOAL | AC4, AC5 | Made testable: user can read expanded section >10s, status updates concurrently |
| C16 | GOAL | AC13, AC14, AC15 | Made testable: static excluded, dynamic enumerated, independently extensible |
