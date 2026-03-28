# Work Item Detail Page - Design Document

## Overview

The work item detail page (`/item/<slug>`) already exists with a comprehensive
implementation including header card, requirements rendering, plan tasks, completion
history, traces, and validation results. This plan addresses the remaining gaps:
drill-down navigation links from other pages and any UI polish issues.

## Current State

### What exists

- **Route**: `GET /item/{slug}` in `langgraph_pipeline/web/routes/item.py`
- **Template**: `langgraph_pipeline/web/templates/item.html` (29.7 KB)
- **Features**: Header with badges, requirements markdown, plan tasks table,
  completions table, validation results, console output, traces section
- **Completions page**: Already has `/item/` links on slug column

### What is missing

1. **Dashboard drill-down links**: Active worker cards display slug as plain text
   (`span.worker-slug`). Recent completion rows display slug as plain text
   (`td.completion-slug`). Both need to become clickable links to `/item/<slug>`.

2. **Queue page drill-down links**: Queue rows display slug as plain text
   (`td.queue-slug`). These should link to `/item/<slug>`.

3. **UI polish**: The backlog item requests a polished two-column layout. The
   existing template should be reviewed against the design criteria (two-column
   on wide screens, section separators, task checkboxes, outcome color coding).

## Key Files to Modify

| File | Change |
|------|--------|
| `langgraph_pipeline/web/templates/dashboard.html` | Wrap slug text in `<a href="/item/...">` for active worker cards and recent completion rows |
| `langgraph_pipeline/web/templates/queue.html` | Wrap slug text in `<a href="/item/...">` for queue rows |
| `langgraph_pipeline/web/templates/item.html` | Review and polish layout per UI design criteria |
| `langgraph_pipeline/web/static/style.css` | Any needed styles for two-column layout or polish |

## Design Decisions

1. **Incremental fix, not rewrite**: The page exists and works. We fix the navigation
   gaps and validate UI quality rather than rebuilding.

2. **Link style**: Slug links should be styled consistently across all pages - use
   the same anchor styling as the completions page already uses.

3. **Two-column layout**: If not already implemented, use CSS grid or flexbox with
   a media query breakpoint for responsive two-column (requirements left, plan +
   history right) on wide screens.
