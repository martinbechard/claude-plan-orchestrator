# Design: 76 Item Page Markdown Rendering and Layout

Source: tmp/plans/.claimed/76-item-page-markdown-rendering-and-layout.md
Requirements: docs/plans/2026-03-30-76-item-page-markdown-rendering-and-layout-requirements.md

## Architecture Overview

The item detail page (item.html + item.py) has two artifact display contexts:

1. **Step Explorer** (left column) -- pipeline stage artifacts loaded lazily via
   GET /item/{slug}/artifact-content, displayed in pre tags with textContent
2. **Output Artifacts** (right column sidebar) -- text files loaded lazily via
   the same endpoint, also displayed in pre tags with textContent

Both currently treat all content as plain text. Markdown files (which are common
in this pipeline -- design docs, requirements, judgments, etc.) appear as raw
markdown syntax instead of formatted HTML.

The two-column layout uses CSS grid with grid-template-columns: 1fr 360px. The
left column grid child lacks min-width: 0, which means content that is wider than
the available space (like long pre-formatted lines or expanded artifact content)
can overflow the grid cell and push/overlap the 360px sidebar.

### Key Files

| File | Role |
|---|---|
| langgraph_pipeline/web/templates/item.html | Template, inline CSS, and inline JS for the item detail page |
| langgraph_pipeline/web/routes/item.py | Backend route with artifact-content endpoint and _render_md_to_html() |

### Existing Infrastructure

- _render_md_to_html(md_path) in item.py already converts markdown files to HTML
  using Python markdown library with fenced_code and tables extensions
- Inline CSS in item.html already has .requirements-body styles for rendered
  markdown (h1-h4, lists, code blocks, tables, blockquotes)
- The /item/{slug}/artifact-content endpoint returns PlainTextResponse for all files

## Design Decisions

### D1: Server-side markdown rendering via artifact-content endpoint

Addresses: P1, FR1
Satisfies: AC1, AC2, AC3, AC4, AC5, AC6
Approach: Modify the GET /item/{slug}/artifact-content endpoint to accept an
optional render=html query parameter. When the file has a .md extension and
render=html is requested, use the existing _render_md_to_html() infrastructure
to return an HTMLResponse instead of PlainTextResponse. This reuses the proven
server-side rendering pipeline rather than introducing a new client-side library.
Files: langgraph_pipeline/web/routes/item.py

### D2: Client-side markdown-aware display in artifact viewers

Addresses: P1, FR1
Satisfies: AC1, AC2, AC3, AC4, AC5, AC6
Approach: Modify the JavaScript in both artifact viewer contexts (step explorer
loadStageArtifacts and output artifacts click handler) to detect .md file extensions
from the artifact path. For markdown files: (a) fetch with render=html parameter,
(b) display the returned HTML using innerHTML in a styled div element instead of
textContent in a pre element. For non-markdown files, keep the existing pre/textContent
behavior unchanged. The styled div reuses the existing .requirements-body CSS class
which already handles headings, lists, code blocks, and tables.
Files: langgraph_pipeline/web/templates/item.html

### D3: CSS grid overflow containment for two-column layout

Addresses: P2, FR2
Satisfies: AC7, AC8, AC9, AC10, AC11
Approach: Add min-width: 0 to the left column grid child (the first child of
.item-layout). This is the standard CSS grid overflow fix -- by default, grid items
have min-width: auto, which prevents them from shrinking below their content size.
Setting min-width: 0 allows the grid item to shrink to fit within the 1fr allocation.
Additionally, add overflow: hidden on the left column container to clip any content
that still attempts to escape.
Files: langgraph_pipeline/web/templates/item.html

### D4: Overflow scrolling for wide content within artifacts

Addresses: FR2
Satisfies: AC10, AC12
Approach: Ensure all artifact content containers have proper overflow handling.
The existing pre tags already have overflow-x: auto. For the new rendered markdown
div containers, add overflow-x: auto and max-width: 100%. Within rendered markdown,
pre and code blocks must also have overflow-x: auto so wide code examples scroll
horizontally rather than breaking out of the column.
Files: langgraph_pipeline/web/templates/item.html

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1, D2 | Server renders markdown headings to HTML; client displays as innerHTML in styled div |
| AC2 | D1, D2 | Server renders markdown lists to HTML; client displays rendered output |
| AC3 | D1, D2 | Server renders fenced code blocks via fenced_code extension; client shows in styled div |
| AC4 | D1, D2 | Raw markdown syntax converted to HTML by server; client never shows raw text for .md files |
| AC5 | D1, D2 | All artifact sections use the same JS detection logic; any .md file gets rendered display |
| AC6 | D1, D2 | Python markdown library with fenced_code and tables extensions covers all standard constructs |
| AC7 | D3 | min-width: 0 on left column grid child constrains content within 1fr boundary |
| AC8 | D3 | Sidebar remains at fixed 360px allocation, unaffected by left column content |
| AC9 | D3 | min-width: 0 plus overflow: hidden prevents any horizontal overlap |
| AC10 | D3, D4 | Grid containment (D3) plus overflow-x: auto on content containers (D4) |
| AC11 | D3 | CSS grid fix applies regardless of which artifact is expanded |
| AC12 | D4 | Wide code blocks and long lines scroll horizontally within their container |
