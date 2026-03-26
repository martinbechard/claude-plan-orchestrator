# Design: Traces timestamps in local time (defect 15)

## Problem

All timestamps on the traces pages display in raw UTC (e.g. 14:38) because the
Jinja2 templates render ISO 8601 strings as-is. Users see UTC offsets instead of
their local clock time.

## Affected templates

- `langgraph_pipeline/web/templates/proxy_list.html` — start time column
- `langgraph_pipeline/web/templates/proxy_trace.html` — start time in header card

The Gantt timeline axis shows elapsed offsets (+Xs, +Nm Xs), not absolute
timestamps, so it does not need to change.

## Approach

The server does not know the browser's timezone, so conversion must happen
client-side. The standard pattern is:

1. Render a `<time>` element whose `datetime` attribute holds the UTC ISO string
   and whose visible text is a UTC fallback (for no-JS environments).
2. A small JS snippet on page load replaces the text of every `.local-time`
   element with `new Date(el.getAttribute('datetime')).toLocaleString()`.

## Changes

### base.html

Add a `<script>` block before `</body>` that queries `.local-time` elements and
replaces their text content with the browser-local formatted string.

### proxy_list.html

Replace the `<time>` element in the Start time column:

    Before:
    <time datetime="{{ run.start_time | e }}">
      {{ run.start_time[:10] | e }} {{ run.start_time[11:19] | e }}
    </time>

    After:
    <time datetime="{{ run.start_time | e }}" class="local-time">
      {{ run.start_time[:10] | e }} {{ run.start_time[11:19] | e }}
    </time>

### proxy_trace.html

Replace the plain text start time in the header card with a `<time class="local-time">`
element carrying the full UTC ISO string as `datetime`.

## No backend changes needed

All timestamp values are already stored as ISO 8601 UTC strings. No Python code
changes are required.
