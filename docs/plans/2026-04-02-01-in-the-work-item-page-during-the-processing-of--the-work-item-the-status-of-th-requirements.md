# Structured Requirements: 01 In The Work Item Page During The Processing Of  The Work Item The Status Of Th

Source: tmp/plans/.claimed/01-in-the-work-item-page-during-the-processing-of--the-work-item-the-status-of-th.md
Generated: 2026-04-02T23:43:35.958010+00:00

## Requirements

### P1: Phase status badge not displayed on work item page
Type: UI
Priority: high
Source clauses: [C1, C7]
Description: During work item processing, the work item page does not display the current pipeline phase as a status badge. Instead, the page component renders plan items as the primary status indicator rather than the phase state (e.g., Intake, Requirements, Planning, Execution, Verification).
Acceptance Criteria:
- Does the work item page display a phase status badge during processing? YES = pass, NO = fail
- Is the phase badge visually distinct from plan item content? YES = pass, NO = fail

### P2: First plan item shown instead of phase badge with no further updates
Type: UI
Priority: high
Source clauses: [C3, C6]
Description: The UI currently shows the first plan item with no further updates as processing progresses. The user sees a static plan item where they expect a phase badge labeled with values like Intake, Requirements, Planning, Execution, Verification. The display neither shows the correct component nor updates over time.
Acceptance Criteria:
- Is the phase badge displayed instead of (or clearly distinct from) plan item output? YES = pass, NO = fail
- Does the display update beyond the initial rendering as processing progresses? YES = pass, NO = fail

### P3: No instrumentation to translate phase transitions into UI state updates
Type: functional
Priority: high
Source clauses: [C8, C9]
Description: The system lacks instrumentation to translate internal phase transitions into UI-level state updates. There is no real-time binding or event stream feeding phase state transitions to the work item page. As a result, even if a badge were rendered, it would not reflect phase changes during processing.
Acceptance Criteria:
- Does the backend communicate phase transition events to the frontend? YES = pass, NO = fail
- Does the work item page receive phase state changes without requiring a manual page refresh? YES = pass, NO = fail

### FR1: Display a phase badge showing the current pipeline phase
Type: UI
Priority: high
Source clauses: [C2, C11]
Description: During work item processing, the work item page must display a badge that indicates the current pipeline phase. The badge must show phase labels such as Intake, Requirements, Planning, Execution, Verification, etc. The badge must reflect which phase the work item is currently in, replacing or clearly augmenting the static plan item output that is currently shown.
Acceptance Criteria:
- Does the work item page show a badge with the current phase name (e.g., Intake, Requirements, Planning, Execution, Verification)? YES = pass, NO = fail
- Is the badge displayed during active work item processing (not only before or after)? YES = pass, NO = fail
- Does the badge replace or clearly augment the previous plan item display as the primary status indicator? YES = pass, NO = fail

### FR2: Real-time phase badge updates as phases transition
Type: functional
Priority: high
Source clauses: [C11, C12]
Description: The phase status badge must update in real time as the work item transitions between phases during processing. The badge must not remain static at the initial phase; it must reflect each phase transition (e.g., from Intake to Requirements to Planning, etc.) as the backend progresses through the pipeline. This requires a live binding between backend phase state and the frontend badge component.
Acceptance Criteria:
- Does the phase badge update automatically when the backend transitions to a new phase? YES = pass, NO = fail
- Does the badge correctly reflect at least the phases: Intake, Requirements, Planning, Execution, Verification? YES = pass, NO = fail
- Can a user observe the badge changing from one phase to the next without refreshing the page? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "the status of the phase is not displayed properly" | P1 |
| "Expected: a badge that says Intake, Requirements, Planning, Execution, Verification etc." | FR1 |
| "Instead, we get the first plan item and no further updates" | P2 |
| "the work item page component renders plan items as the primary status indicator rather than phase state" | P1, P2 |
| "the system lacks instrumentation to translate internal phase transitions into UI-level state updates" | P3 |
| "there's no real-time binding or event stream feeding phase state transitions to the work item page" | P3 |
| "the work item page must display a live phase badge that reflects which phase the work item is currently in and updates as phases transition" | FR1, FR2 |
| "The work item page needs a real-time phase status badge that replaces or augments plan item display and updates throughout processing" | FR1, FR2 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [C-PROB] | PROB | P1 | Mapped |
| C2 [C-GOAL] | GOAL | FR1 | Mapped |
| C3 [C-PROB] | PROB | P2 | Mapped |
| C4 [C-CTX] | CTX | -- | Unmapped: diagnostic context noting the root cause is underspecified; informs P3 scope but not a requirement itself |
| C5 [C-CTX] | CTX | -- | Unmapped: analytical context identifying two sub-issues; addressed by splitting into P1/P2 |
| C6 [C-FACT] | FACT | P2 | Mapped |
| C7 [C-FACT] | FACT | P1 | Mapped |
| C8 [C-PROB] | PROB | P3 | Mapped |
| C9 [C-PROB] | PROB | P3 | Mapped |
| C10 [C-CTX] | CTX | -- | Unmapped: historical context explaining why the gap exists; not actionable as a requirement |
| C11 [C-GOAL] | GOAL | FR1, FR2 | Mapped |
| C12 [C-GOAL] | GOAL | FR1, FR2 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

AC1: Does the work item page display a phase status badge (not plan item content) during work item processing? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse: "status of the phase is not displayed properly" → is it displayed properly?)
  Belongs to: P1
  Source clauses: [C1, C7]

AC2: Is the phase status badge visually distinct from plan item content on the work item page? YES = pass, NO = fail
  Origin: Derived from C7 [FACT] (inverse: "renders plan items as the primary status indicator rather than phase state" → is phase state visually separated from plan items?)
  Belongs to: P1
  Source clauses: [C7]

AC3: Does the phase badge show a label matching the current pipeline phase (e.g., Intake, Requirements, Planning, Execution, Verification)? YES = pass, NO = fail
  Origin: Derived from C2 [GOAL] (operationalized: "a badge that says Intake, Requirements, Planning, Execution, Verification etc." → does the badge show these labels?)
  Belongs to: FR1
  Source clauses: [C2, C11]

AC4: Is the phase badge displayed as the primary status indicator, replacing or clearly augmenting the plan item output? YES = pass, NO = fail
  Origin: Derived from C11 [GOAL] (operationalized: "replacing or clearly augmenting the static plan item output")
  Belongs to: FR1
  Source clauses: [C11, C12]

AC5: Does the display update beyond its initial rendering as work item processing progresses through phases? YES = pass, NO = fail
  Origin: Derived from C3 [PROB] (inverse: "we get the first plan item and no further updates" → does the display update?)
  Belongs to: P2
  Source clauses: [C3, C6]

AC6: Is the phase badge shown instead of (or clearly distinct from) the static first plan item that was previously displayed? YES = pass, NO = fail
  Origin: Derived from C6 [FACT] (inverse: "shows the first plan item with no further updates, instead of a phase badge" → is the badge shown instead?)
  Belongs to: P2
  Source clauses: [C6, C3]

AC7: Does the backend emit phase transition events that the frontend can consume? YES = pass, NO = fail
  Origin: Derived from C8 [PROB] (inverse: "lacks instrumentation to translate internal phase transitions into UI-level state updates" → does instrumentation exist?)
  Belongs to: P3
  Source clauses: [C8]

AC8: Does the work item page receive phase state changes without requiring a manual page refresh? YES = pass, NO = fail
  Origin: Derived from C9 [PROB] (inverse: "no real-time binding or event stream feeding phase state transitions" → does a real-time binding exist?)
  Belongs to: P3
  Source clauses: [C9]

AC9: Is the phase badge displayed during active work item processing (not only before or after)? YES = pass, NO = fail
  Origin: Derived from C11 [GOAL] (operationalized: "during the processing of the work item" → is it visible during processing?)
  Belongs to: FR1
  Source clauses: [C11]

AC10: Does the phase badge update automatically when the backend transitions to a new phase, without user interaction? YES = pass, NO = fail
  Origin: Derived from C12 [GOAL] (operationalized: "real-time phase status badge that... updates throughout processing")
  Belongs to: FR2
  Source clauses: [C11, C12]

AC11: Can a user observe the badge changing from one phase to the next (e.g., Intake → Requirements → Planning) without refreshing the page? YES = pass, NO = fail
  Origin: Derived from C11 [GOAL] (operationalized: "updates as phases transition")
  Belongs to: FR2
  Source clauses: [C11, C12]

AC12: Does the badge correctly reflect at least the phases: Intake, Requirements, Planning, Execution, Verification? YES = pass, NO = fail
  Origin: Derived from C2 [GOAL] (operationalized: "Intake, Requirements, Planning, Execution, Verification etc.")
  Belongs to: FR2
  Source clauses: [C2, C11]

---

## Requirement -> AC Coverage
| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2 | 2 |
| P2 | AC5, AC6 | 2 |
| P3 | AC7, AC8 | 2 |
| FR1 | AC3, AC4, AC9 | 3 |
| FR2 | AC10, AC11, AC12 | 3 |

## Clause -> AC Coverage
| Clause | Type | AC | How |
|---|---|---|---|
| C1 | PROB | AC1 | Inverse |
| C2 | GOAL | AC3, AC12 | Made testable |
| C3 | PROB | AC5 | Inverse |
| C4 | CTX | -- | Diagnostic context noting root cause is underspecified; informs P3 scope but not directly testable |
| C5 | CTX | -- | Analytical context identifying two sub-issues; addressed structurally by P1/P2 split, not testable itself |
| C6 | FACT | AC6 | Inverse |
| C7 | FACT | AC2 | Inverse |
| C8 | PROB | AC7 | Inverse |
| C9 | PROB | AC8 | Inverse |
| C10 | CTX | -- | Historical context explaining why the gap exists (original spec omitted phase tracking); not actionable as a requirement |
| C11 | GOAL | AC4, AC9, AC10, AC11 | Made testable |
| C12 | GOAL | AC4, AC10, AC11 | Made testable |
