# Traces page: timestamps displayed in UTC instead of local time

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

## LangSmith Trace: d3406e99-bf5e-449a-8551-2633d52a839b
