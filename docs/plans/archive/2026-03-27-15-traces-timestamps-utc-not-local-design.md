# Design: Traces Timestamps UTC-to-Local Conversion

## Problem

Timestamps on traces pages display in UTC instead of the browser's local timezone,
requiring mental arithmetic to correlate with real events.

## Architecture

The fix uses a two-layer approach:

1. **Server side (Jinja2 templates):** All timestamp values are wrapped in
   `<time datetime="UTC_ISO" class="local-time">fallback</time>` elements.
   The fallback text shows the raw UTC value for non-JS browsers.

2. **Client side (base.html global script):** A script at the bottom of base.html
   queries all `.local-time` elements and replaces their text content with
   `new Date(datetime).toLocaleString()`, converting to the browser's local timezone.

3. **SSE/dashboard:** `dashboard.js` already uses `toLocaleTimeString()` for its
   timestamp formatting, so no changes needed there.

4. **Timeline axis:** Uses relative elapsed-time offsets (e.g. +0s, +5s), not
   absolute timestamps, so no conversion needed.

## Key Files

| File | Role |
|------|------|
| `langgraph_pipeline/web/templates/base.html` (lines 41-46) | Global `.local-time` JS converter |
| `langgraph_pipeline/web/templates/proxy_list.html` (lines 151-154) | Trace list start_time |
| `langgraph_pipeline/web/templates/proxy_trace.html` (lines 57-60) | Trace detail start_time |
| `langgraph_pipeline/web/templates/completions.html` (lines 177-179) | Completions finished_at |
| `langgraph_pipeline/web/templates/analysis.html` (lines 239-241) | Analysis created_at |
| `langgraph_pipeline/web/templates/item.html` (lines 902-908) | Item traces created_at |
| `langgraph_pipeline/web/static/dashboard.js` (line 55) | SSE dashboard toLocaleTimeString |

## Design Decisions

1. Client-side conversion (server cannot know client timezone)
2. Global script in base.html avoids per-page duplication
3. `datetime` attribute is source of truth; `textContent` is display value
4. Preserve fallback dash for missing timestamps
