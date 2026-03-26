# Design: Timeline Bar Colors Too Similar

## Overview

The Gantt timeline in `proxy_trace.html` uses three bar color categories (LLM calls, tool calls, other) that are too visually similar, especially for users with color vision differences. This fix updates the color palette to use clearly distinct colors.

## Affected Files

- `langgraph_pipeline/web/templates/proxy_trace.html` — contains `bar_color()` and `text_color()` Jinja macros and the legend rect fills

## Design Decision

Replace the current palette with:

| Category | Old Color | New Color |
|----------|-----------|-----------|
| LLM calls | #16a34a (mid green) | #7c3aed (violet) |
| Tool calls | #2563eb (mid blue) | #0891b2 (cyan/teal) |
| Other/chain | #64748b (slate grey) | #f59e0b (amber) |

Text contrast colors must also be updated to maintain readability on each new background.

## Scope

Single-file change in the HTML template. No backend, route, or Python changes required.
