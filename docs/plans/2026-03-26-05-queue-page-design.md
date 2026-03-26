# Queue Page Design

## Overview

A read-only `/queue` page that lists all pending backlog items across the three
backlog directories. Users can see type, filename, and age of each item, and
click a row to read the raw markdown inline without leaving the page.

## Architecture

Follows the same pattern as all existing routes:

- `langgraph_pipeline/web/routes/queue.py` — FastAPI router with `GET /queue`
  and `GET /api/queue` (JSON data endpoint for polling)
- `langgraph_pipeline/web/templates/queue.html` — Jinja2 template extending
  `base.html`
- `langgraph_pipeline/web/templates/base.html` — add Queue nav link

## Backlog Directories

Three directories are scanned for `*.md` files:

| item_type  | directory               |
|------------|-------------------------|
| defect     | docs/defect-backlog     |
| feature    | docs/feature-backlog    |
| analysis   | docs/analysis-backlog   |

Each directory may not exist; the route handles missing dirs gracefully.

## Data Model

Each queue item returned by the backend:

```python
{
  "slug": str,        # filename without .md extension
  "item_type": str,   # "defect" | "feature" | "analysis"
  "mtime": float,     # Unix timestamp of last file modification
  "age_seconds": int, # seconds since mtime
  "content": str,     # raw markdown content
}
```

Items are sorted by `item_type` (alphabetical), then `age_seconds` descending
(oldest first).

## Endpoints

### GET /queue

Renders `queue.html` as an HTML page.

### GET /api/queue

Returns `{"items": [...]}` JSON for client-side polling refresh. The template
fetches this endpoint every `QUEUE_POLL_INTERVAL_SECONDS` (12 seconds) and
re-renders the table in-place.

## Frontend Behaviour

- Table columns: Type badge | Slug | Age
- Type badge uses CSS classes (`badge-defect`, `badge-feature`, `badge-analysis`)
  matching the colour scheme in `style.css`
- Clicking a row toggles an inline `<details>` panel containing the raw markdown
  rendered as `<pre>` (no markdown-to-HTML conversion needed)
- Auto-refresh every 12 seconds via `setInterval` + `fetch /api/queue`
- The refresh does NOT collapse open detail panels (row state preserved by slug key)
- Dashboard queue count links to `/queue`

## Key Files

| Action   | Path |
|----------|------|
| Create   | `langgraph_pipeline/web/routes/queue.py` |
| Create   | `langgraph_pipeline/web/templates/queue.html` |
| Modify   | `langgraph_pipeline/web/templates/base.html` (add Queue nav link) |
| Modify   | `langgraph_pipeline/web/server.py` (register queue router) |
| Modify   | `langgraph_pipeline/web/templates/dashboard.html` (link queue count) |

## Design Decisions

- **Poll, not SSE**: Queue changes are rare; a 12-second `setInterval` fetch is
  simpler and adequate.
- **Raw `<pre>` for markdown**: Avoids adding a markdown renderer dependency;
  the content is primarily plain text.
- **No write operations**: The page is entirely read-only.
- **Missing dirs handled gracefully**: If `docs/analysis-backlog` does not exist
  the route skips it silently.
