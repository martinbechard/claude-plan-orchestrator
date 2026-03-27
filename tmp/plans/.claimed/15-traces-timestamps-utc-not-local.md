# Traces page: timestamps displayed in UTC instead of local time

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

All timestamps on the traces page (start time, end time, created_at) display
in UTC. A trace started at 10:38 local time appears as 14:38, which is
confusing and requires mental arithmetic to correlate with real events.

## Affected Pages

- /proxy (trace list): created_at column
- /proxy/{run_id} (trace detail): start time in header card, axis labels
- /completions (once built): finished_at column

## Root Cause

Timestamps are stored in the SQLite DB as ISO 8601 strings with +00:00 UTC
offset (e.g. "2026-03-26T14:38:00+00:00"). The Jinja2 templates and JS
rendering display these strings as-is without converting to the browser's
local timezone.

## Fix

Two approaches (use both depending on context):

**Server-rendered pages (Jinja2):**
Add a Jinja2 filter that converts UTC ISO strings to local time. Since the
server does not know the client timezone, the cleanest approach is to render
timestamps as UTC in a data attribute and convert client-side with JS:

    <time datetime="2026-03-26T14:38:00Z" class="local-time">14:38:00</time>

Then a small JS snippet on page load:

    document.querySelectorAll('.local-time').forEach(el => {
      el.textContent = new Date(el.getAttribute('datetime')).toLocaleString();
    });

**SSE-driven pages (dashboard.js):**
fmtFinished() already uses toLocaleTimeString() which shows local time, so
the dashboard is fine. But verify all other timestamp displays also use
toLocaleString or equivalent.




## 5 Whys Analysis

Title: Timestamps displayed in UTC require timezone conversion for debugging context
Clarity: 4
5 Whys:
1. **Why are timestamps displayed in UTC instead of local time?** Because ISO 8601 UTC strings stored in the database are rendered directly in templates and JS without converting to the browser's local timezone.

2. **Why are timestamps stored as UTC strings without client-side conversion logic?** Because the system architecture stores all times in UTC to maintain consistency across distributed operations, but the UI layer was built without timezone conversion capability.

3. **Why wasn't timezone conversion implemented in the initial UI build?** Because the development approach separated concerns: the backend prioritized data correctness (UTC normalization), and frontend implementation deferred timezone handling as a lower-priority UX detail.

4. **Why does UTC display specifically frustrate users?** Because users experience incidents and events in their local timezone; seeing UTC times requires mental arithmetic to correlate trace data with known real-world events (e.g., "the user reported a problem at 10:38 AM local, but I see 14:38 UTC and need to convert").

5. **Why is fast timestamp correlation essential to the debugging workflow?** Because during incident investigation, users need to quickly match trace events to known problems without cognitive overhead; timezone confusion introduces delay and error risk, potentially causing critical traces to be missed or misinterpreted.

Root Need: Users need timestamps displayed in local timezone to rapidly and accurately map trace events to real-world incidents during debugging without requiring timezone conversion.

Summary: The real issue isn't technical correctness—UTC storage is right—but enabling fast cognitive mapping during time-sensitive debugging.

## LangSmith Trace: 4b6d29a7-c16d-45dc-a89a-10bfad0d2666
