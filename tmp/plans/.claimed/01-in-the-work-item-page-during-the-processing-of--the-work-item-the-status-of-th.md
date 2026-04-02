# in the work item page, during the processing of  the work item, the status of th

## Status: Open

## Priority: Medium

## Summary

in the work item page, during the processing of  the work item, the status of the phase is not displayed properly. Expected: a badge that says Intake, Requirements, Planning, Execution, Verification etc. Instead, we get the first plan item and no further updates

## Source

Created from Slack message by U0AEWQYSLF9 at 1775165059.653199.

## LangSmith Trace: b880e034-135d-4448-9df0-cbf4324acfa7


## 5 Whys Analysis

Title: Phase status badge not updating during work item processing

Clarity: 3/5 (The observable problem is clear—wrong component displayed—but the root cause is underspecified. The summary conflates two separate issues: displaying the wrong component AND the lack of updates.)

5 Whys:

W1: Why is the phase status not displayed properly?
    Because the UI shows the first plan item with no further updates, instead of a phase badge labeled Intake, Requirements, Planning, Execution, Verification. (C3, C5)

W2: Why is a plan item being rendered instead of a phase badge?
    Because the work item page component renders plan items as the primary status indicator rather than phase state. (C5) [ASSUMPTION]

W3: Why is the phase state not being surfaced to the UI during work item processing?
    Because during the processing of the work item (C2), the system lacks instrumentation to translate internal phase transitions into UI-level state updates. (C2, C4) [ASSUMPTION]

W4: Why doesn't the backend communicate phase changes to the frontend?
    Because there's no real-time binding or event stream feeding phase state transitions to the work item page (C1, C2). [ASSUMPTION]

W5: Why wasn't phase visibility built into the work item page design?
    Because the original feature spec didn't define phase tracking as a required status indicator, only plan items. (C1, C4) [ASSUMPTION]

Root Need: During work item processing (C2), the work item page (C1) must display a live phase badge (C4) that reflects which phase the work item is currently in and updates as phases transition, rather than showing static plan item output (C5).

Summary: The work item page needs a real-time phase status badge that replaces or augments plan item display and updates throughout processing.
