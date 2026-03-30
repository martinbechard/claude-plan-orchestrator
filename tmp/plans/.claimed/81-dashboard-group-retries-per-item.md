# Dashboard: group retry attempts under a single item entry

When an item fails with outcome=warn and is retried, the completions table shows two separate rows (warn + success) that look like duplicate entries. The dashboard should group retry attempts under a single item, showing the final outcome prominently with the retry history accessible on demand (e.g. expandable row or tooltip showing previous attempts).

## LangSmith Trace: d95f1677-1bef-4aea-ba10-43ec0024d221


## 5 Whys Analysis

Title: Eliminate dashboard duplicate entry confusion when items are retried
Clarity: 4/5

5 Whys:

W1: Why do users see what appear to be duplicate entries in the dashboard?
    Because: When an item fails with outcome=warn and is retried, the completions table shows two separate rows (warn + success) [C1, C2]

W2: Why is this presentation a problem?
    Because: These rows look like duplicate entries [C3], creating confusion about whether they represent separate items or the same item's retry history

W3: Why do users need to see the retry information at all?
    Because: The dashboard should show the final outcome prominently [C5], but users also need the retry history accessible on demand [C6] to understand what happened and debug issues [ASSUMPTION]

W4: Why can't retry history just be discarded or permanently hidden?
    Because: The retry history (e.g. expandable row or tooltip showing previous attempts) [C7] is necessary context for understanding the item's complete journey and failure causes [ASSUMPTION]

W5: Why doesn't the current flat-row design work for this?
    Because: The current table structure treats each execution as an independent row [C1, C2], which makes it impossible to distinguish between separate items and retried items without context [ASSUMPTION]

Root Need: Users need a grouping mechanism that displays retried items as a single entry with the final outcome [C4, C5] while keeping the retry history (previous failed attempts) accessible without cluttering the main view [C6]. The current duplicate-row presentation [C3] undermines dashboard clarity and traceability [C1, C2].

Summary: The root need is to redesign the dashboard to hierarchically group retry attempts under a single visual item, showing final outcomes by default while allowing users to inspect the retry history on demand.
