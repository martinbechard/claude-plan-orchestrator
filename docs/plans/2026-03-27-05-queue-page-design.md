# Queue Page - Validation Design

## Status

This feature was previously implemented and requires validation against acceptance
criteria. All key files already exist.

## Architecture Overview

The queue page is a read-only view of pending work items across backlog directories.

- **Backend**: FastAPI route in routes/queue.py with GET /queue (HTML) and GET /api/queue (JSON)
- **Frontend**: Jinja2 template queue.html with client-side polling (12s interval)
- **Data source**: Scans BACKLOG_DIRECTORIES (analysis, defect, feature) for *.md files
- **Navigation**: Queue link in base.html nav bar; dashboard queue count links to /queue

## Key Files

| File | Purpose |
|------|---------|
| langgraph_pipeline/web/routes/queue.py | Queue endpoints (HTML + JSON API) |
| langgraph_pipeline/web/templates/queue.html | Queue page template with polling |
| langgraph_pipeline/web/templates/base.html | Nav bar with Queue link |
| langgraph_pipeline/web/templates/dashboard.html | Dashboard queue count linking to /queue |
| langgraph_pipeline/web/dashboard_state.py | Queue count computation for SSE stream |
| langgraph_pipeline/shared/paths.py | BACKLOG_DIRS constant |

## Design Decisions

1. **Validation-only approach**: The implementation exists; the plan validates acceptance
   criteria and fixes any gaps rather than reimplementing.
2. **Single task**: Since the feature is already built, one validation pass covers all
   criteria (nav link, item listing, type/slug/age display, sort order, auto-refresh,
   expandable content).
