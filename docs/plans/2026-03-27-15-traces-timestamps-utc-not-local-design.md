# Design: Traces Timestamps UTC-to-Local Conversion Fix

## Problem

Timestamps on some pages display in UTC instead of the browser's local timezone,
requiring mental arithmetic to correlate with real events.

## Current State

Most pages already use the correct pattern: wrapping timestamps in
```<time class="local-time" datetime="...">``` elements, which are converted
client-side by the script in base.html:

```
document.querySelectorAll('.local-time').forEach(function(el) {
  var dt = el.getAttribute('datetime');
  if (dt) { el.textContent = new Date(dt).toLocaleString(); }
});
```

Pages already fixed:
- proxy_list.html (start_time column)
- proxy_trace.html (start time in header card)
- completions.html (finished_at column)
- analysis.html (created_at column)
- dashboard.js (uses toLocaleTimeString via fmtFinished)

## Remaining Issue

**item.html line 902**: The traces table in the work item detail page renders
created_at as a raw substring without local-time conversion:

```
{{ t.created_at[:16] if t.created_at else '---' }}
```

This needs to be wrapped in the same ```<time class="local-time">``` pattern.

## Fix

Replace the raw timestamp rendering in item.html with:

```
<time datetime="{{ t.created_at | e }}" class="local-time">
  {{ t.created_at[:16] if t.created_at else '---' }}
</time>
```

The existing base.html script handles conversion automatically.

## Key Files

- langgraph_pipeline/web/templates/item.html (fix needed)
- langgraph_pipeline/web/templates/base.html (conversion script - no changes)

## Design Decisions

1. Reuse existing local-time class pattern rather than introducing new utilities
2. Single-file fix since other pages are already converted
3. Preserve the fallback dash for missing timestamps
