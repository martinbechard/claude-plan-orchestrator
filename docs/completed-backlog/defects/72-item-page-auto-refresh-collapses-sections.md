# Item page auto-refresh collapses expanded sections

The work item detail page uses a meta http-equiv refresh tag that reloads the entire page every 10 seconds while the item is being processed. This makes it impossible to read expanded content sections because they collapse back every time the page reloads.

The page should only refresh the dynamic parts (status badge, cost, duration, worker info, token counts) without reloading the static content sections (raw input, clause register, 5 whys, structured requirements, design, validation reports). The content sections don't change during the refresh interval so there's no reason to reload them.

The current implementation is a full-page meta refresh in the HTML head. Replace it with a JavaScript fetch that updates only the dynamic elements and leaves the rest of the DOM (including details/summary open state) intact.




## 5 Whys Analysis

Title: Item page auto-refresh collapses expanded sections
Clarity: 5
5 Whys:
W1: Why are expanded content sections collapsing every 10 seconds?
    Because: The entire page is being reloaded via meta http-equiv refresh tag [C1, C2]

W2: Why is a full-page reload being used?
    Because: The current implementation uses a simple meta refresh approach in the HTML head, which reloads all content rather than selectively updating elements [C5]

W3: Why is selective updating needed instead of a simple full reload?
    Because: The static content sections (raw input, clause register, 5 whys, requirements, design, validation reports) don't change during the refresh interval, so reloading them is wasteful and destroys the DOM state (open/closed details sections) [C4]

W4: Why do we need any refresh at all if some sections are static?
    Because: The dynamic elements (status badge, cost, duration, worker info, token counts) change as the item is being processed and must be updated to reflect current state [C3]

W5: Why can't dynamic and static sections be updated with the same mechanism?
    Because: Full-page reload destroys DOM state for all elements; selective updates via JavaScript fetch preserve the DOM structure and state while only modifying content that actually changed [C6] [ASSUMPTION: JavaScript fetch is technically feasible without full reload]

Root Need: Enable users to read and interact with expanded content sections while the page auto-refreshes to show current processing state, by decoupling DOM structure preservation (static sections) from content updates (dynamic elements) [C2, C3]

Summary: Replace full-page meta refresh with JavaScript-based selective DOM updates to preserve user interaction state while keeping dynamic information current.
