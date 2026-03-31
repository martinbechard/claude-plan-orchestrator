# Design: 76 Item Page Markdown Rendering and Layout

Source work item: tmp/plans/.claimed/76-item-page-markdown-rendering-and-layout.md
Requirements: docs/plans/2026-03-31-76-item-page-markdown-rendering-and-layout-requirements.md
Date: 2026-03-31

## Architecture Overview

The item detail page uses a step explorer accordion to display pipeline artifacts.
Each artifact's content is fetched on-demand via AJAX from the
/item/{slug}/artifact-content endpoint and displayed as plain text in pre elements.

Two problems exist:

1. Markdown rendering regression (P1, FR1): Markdown files (.md) are displayed as
   raw text. The JS function loadStageArtifacts() fetches content and sets it via
   pre.textContent, which escapes all HTML. The backend already renders other markdown
   sections (requirements_html, five_whys_html) server-side, but AJAX-loaded artifact
   content bypasses this. Fix: detect .md files by extension and render through a
   client-side markdown library before display.

2. Layout overflow (P2, FR2): Expanded artifact content containers lack CSS constraints
   to prevent overflow beyond the left column, breaking the two-column grid layout.
   The CSS Grid default min-width: auto allows content to expand beyond its track.
   Fix: add min-width: 0 on grid children and overflow-x: auto on content containers.

The fix is purely frontend. No backend changes are needed.

### Current Content Loading Flow

1. Template renders pre.step-artifact-content with data-artifact-path attribute
2. User clicks stage header -> JS calls loadStageArtifacts()
3. JS fetches from /item/{slug}/artifact-content?path={path}
4. Content set via pre.textContent = text (no markdown processing)

### Proposed Content Loading Flow

1. Same template structure, pre for non-markdown and div.md-rendered for markdown
2. User clicks stage header -> JS calls loadStageArtifacts()
3. JS fetches text from /item/{slug}/artifact-content?path={path}
4. JS checks file extension from data-artifact-path
5. For .md files: render through marked.parse(), display as innerHTML in div.md-rendered
6. For non-.md files: display as textContent in pre (current behavior unchanged)

## Key Files to Modify

- langgraph_pipeline/web/templates/item.html -- add marked.js, modify loadStageArtifacts()
- langgraph_pipeline/web/static/style.css -- add markdown styles, fix layout constraints

No backend changes required.

## Design Decisions

### D1: Client-side markdown rendering with marked.js

- Addresses: P1, FR1
- Satisfies: AC1, AC2, AC3
- Approach: Add the marked.js library (via CDN with SRI hash) to item.html. In
  loadStageArtifacts(), after fetching artifact text, check the data-artifact-path
  attribute for .md extension. For markdown files, render through marked.parse()
  and display as innerHTML in a div.md-rendered container (hide the pre, show the
  div). For non-markdown files, keep the existing pre + textContent behavior.
  This provides full GFM support (headings, lists, code blocks, inline formatting,
  links, tables, blockquotes). AC3 is satisfied because all artifact sections share
  the same loadStageArtifacts() code path -- every section with a .md path gets
  rendered through marked.
- Files: langgraph_pipeline/web/templates/item.html

### D2: CSS layout constraints for two-column stability

- Addresses: P2, FR2
- Satisfies: AC4, AC5, AC6
- Approach: Apply three CSS fixes:
  (a) Add min-width: 0 to the left grid column child (step-explorer container).
      This is the standard fix for CSS Grid blowout -- without it, grid items
      default to min-width: auto, allowing content to expand beyond the track.
  (b) Add max-width: 100% and overflow-x: auto to artifact content containers
      (both pre and div.md-rendered). Wide content scrolls horizontally within
      the container rather than expanding the column.
  (c) For pre elements, use white-space: pre-wrap to allow line wrapping.
  These constraints keep all content within the left column (AC4), preserve the
  right sidebar position (AC5), and use in-column scrolling for overflow (AC6).
- Files: langgraph_pipeline/web/static/style.css, langgraph_pipeline/web/templates/item.html

### D3: Dark-theme markdown content styling

- Addresses: P1
- Satisfies: AC1, AC2
- Approach: Add CSS rules for .md-rendered that style rendered markdown elements
  within the dark-themed artifact viewer: headings with scaled sizes (h1 at 1.3em,
  h2 at 1.15em, etc.), lists with indentation and proper bullet/number styling,
  code blocks with dark background and monospace font matching existing
  .step-artifact-content pre styling, inline code with subtle background, links
  with visible coloring, tables with borders, blockquotes with left-border accent.
  Reuse the existing dark color scheme for visual consistency. The rendered content
  container uses the same background and border-radius as pre.step-artifact-content.
- Files: langgraph_pipeline/web/static/style.css

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1: Markdown rendered as formatted HTML | D1, D3 | marked.js parses markdown to HTML; D3 styles rendered elements for dark theme |
| AC2: Headings, lists, code blocks render correctly | D1, D3 | marked.js handles element conversion; D3 styles each element type appropriately |
| AC3: Every artifact section applies markdown-to-HTML | D1 | All sections share loadStageArtifacts() code path with .md extension detection |
| AC4: Expanded section stays within column width | D2 | min-width: 0 on grid child + max-width: 100% on content containers |
| AC5: Right column remains visible on expand/collapse | D2 | CSS grid constraints prevent left column from exceeding its track width |
| AC6: Overflow handled via in-column scrolling | D2 | overflow-x: auto on .step-artifact-content and .md-rendered containers |
