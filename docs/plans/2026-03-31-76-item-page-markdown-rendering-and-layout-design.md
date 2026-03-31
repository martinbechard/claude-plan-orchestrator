# Design: 76 Item Page Markdown Rendering and Layout

Source work item: tmp/plans/.claimed/76-item-page-markdown-rendering-and-layout.md
Requirements: docs/plans/2026-03-31-76-item-page-markdown-rendering-and-layout-requirements.md
Date: 2026-03-31

## Architecture Overview

The item detail page uses a step explorer accordion (left column) and an output
artifacts list (right column sidebar) to display pipeline artifacts. Each artifact's
content is fetched on-demand via AJAX from the /item/{slug}/artifact-content endpoint
(PlainTextResponse) and displayed as plain text in pre elements.

Two problems exist:

1. Markdown rendering regression (P1, FR1): Markdown files (.md) are displayed as
   raw text. Two JS code paths load artifact content and both use pre.textContent:
   (a) loadStageArtifacts() for step explorer accordion artifacts
   (b) artifact-path-link click handler for output artifact viewer entries
   The backend already renders other markdown sections (requirements_html,
   five_whys_html) server-side, but AJAX-loaded artifact content bypasses this.
   Fix: detect .md files by extension and render through a client-side markdown
   library (marked.js) before display, in both code paths.

2. Layout overflow (P2, FR2): Expanded artifact content containers lack CSS
   constraints to prevent overflow beyond the left column, breaking the two-column
   grid layout. The CSS Grid default min-width: auto allows content to expand
   beyond its track. Fix: add min-width: 0 on grid children and overflow-x: auto
   on content containers.

The fix is purely frontend. No backend changes are needed.

### Current Content Loading Flow

Step explorer artifacts:
1. Template renders pre.step-artifact-content with data-artifact-path attribute
2. User clicks stage header -> JS calls loadStageArtifacts()
3. JS fetches from /item/{slug}/artifact-content?path={path}
4. Content set via pre.textContent = text (no markdown processing)

Output artifact viewer:
1. Template renders pre.artifact-viewer-pre inside .artifact-viewer (hidden)
2. User clicks .artifact-path-link button -> toggle visibility
3. JS fetches from /item/{slug}/artifact-content?path={path}
4. Content set via pre.textContent = text (no markdown processing)

### Proposed Content Loading Flow

Both code paths gain markdown detection:
1. JS fetches text from /item/{slug}/artifact-content?path={path}
2. JS checks file extension from data-artifact-path (or button dataset)
3. For .md files: render through marked.parse(), display as innerHTML in a
   div.md-rendered sibling container (hide the pre, show the div)
4. For non-.md files: display as textContent in pre (current behavior)

## Key Files to Modify

- langgraph_pipeline/web/templates/item.html -- add marked.js CDN, modify
  loadStageArtifacts() and artifact-link click handler, add div.md-rendered containers
- langgraph_pipeline/web/static/style.css -- add .md-rendered styles, fix layout

No backend changes required.

## Design Decisions

### D1: Client-side markdown rendering with marked.js

- Addresses: P1, FR1
- Satisfies: AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8
- Approach: Add the marked.js library (via CDN with SRI hash) to item.html. In
  both loadStageArtifacts() and the artifact-path-link click handler, after fetching
  artifact text, check the file path for .md extension. For markdown files, render
  through marked.parse() and display as innerHTML in a div.md-rendered container
  (hide the pre, show the div). For non-markdown files, keep the existing
  pre + textContent behavior. This provides full GFM support including headings
  (AC2), lists (AC3), code blocks (AC4), inline formatting (AC5), links, tables,
  and blockquotes (AC8). AC6 and AC7 are satisfied because both artifact loading
  code paths share the same .md extension detection and rendering logic -- every
  artifact section with a .md path gets rendered through marked. A shared helper
  function (e.g. renderArtifactContent(pre, mdDiv, text, path)) ensures consistency.
- Files: langgraph_pipeline/web/templates/item.html

### D2: CSS layout constraints for two-column stability

- Addresses: P2, FR2
- Satisfies: AC9, AC10, AC11, AC12, AC13
- Approach: Apply three CSS fixes:
  (a) Add min-width: 0 to the direct children of .item-layout grid. This is the
      standard fix for CSS Grid blowout -- without it, grid items default to
      min-width: auto, allowing content to expand beyond the track.
  (b) Add max-width: 100% and overflow-x: auto to artifact content containers
      (both pre.step-artifact-content, pre.artifact-viewer-pre, and div.md-rendered).
      Wide content scrolls horizontally within the container.
  (c) Add overflow: hidden to the step-explorer container to prevent any child
      overflow from escaping.
  These constraints keep all content within the left column (AC11), preserve the
  right sidebar position and visibility (AC9, AC10), use in-column scrolling for
  overflow (AC12), and remain static CSS rules that apply regardless of how many
  sections are expanded (AC13).
- Files: langgraph_pipeline/web/templates/item.html (inline styles section),
  langgraph_pipeline/web/static/style.css

### D3: Dark-theme markdown content styling

- Addresses: P1
- Satisfies: AC1, AC2, AC3, AC4, AC5, AC8
- Approach: Add CSS rules for .md-rendered that style rendered markdown elements
  within the dark-themed artifact viewer: headings with scaled sizes (h1 at 1.3em
  down to h6 at 0.85em), lists with indentation and proper bullet/number styling,
  code blocks with slightly darker background and monospace font matching existing
  pre styling, inline code with subtle background, links with visible coloring,
  tables with cell borders, blockquotes with left-border accent. Reuse the existing
  dark color scheme (#1a1a2e background, #e2e8f0 text) for visual consistency. The
  div.md-rendered container uses the same background, padding, and border-radius as
  pre.step-artifact-content so markdown and non-markdown artifacts look cohesive.
- Files: langgraph_pipeline/web/templates/item.html (inline styles),
  langgraph_pipeline/web/static/style.css

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1: Markdown rendered as formatted HTML | D1, D3 | marked.js parses markdown to HTML; D3 styles rendered output in dark theme |
| AC2: Headings (h1-h6) rendered as styled elements | D1, D3 | marked.js converts # headings to h1-h6; D3 sizes them with scaled em values |
| AC3: Lists rendered as HTML list elements | D1, D3 | marked.js converts -/* and 1. to ul/ol; D3 styles with indentation and bullets |
| AC4: Code blocks with code formatting | D1, D3 | marked.js converts fenced blocks; D3 styles with dark bg + monospace font |
| AC5: Inline formatting (bold, italic, etc.) | D1, D3 | marked.js converts **bold** *italic* etc.; D3 inherits text color from theme |
| AC6: All artifact sections use renderer | D1 | Both loadStageArtifacts() and artifact-link handler share renderArtifactContent() |
| AC7: Markdown-to-HTML conversion before display | D1 | JS detects .md extension and passes through marked.parse() before DOM insertion |
| AC8: All standard constructs supported | D1, D3 | marked.js supports full GFM; D3 styles links, tables, blockquotes, emphasis |
| AC9: Right column stays visible on expand | D2 | min-width: 0 on grid children prevents left column from exceeding its track |
| AC10: No overlap or visual obstruction | D2 | max-width: 100% + overflow constraints contain all content within its column |
| AC11: Content within column boundaries | D2 | min-width: 0 + max-width: 100% + overflow: hidden on step-explorer container |
| AC12: Overflow scrolls/wraps instead of spilling | D2 | overflow-x: auto on .step-artifact-content, .artifact-viewer-pre, .md-rendered |
| AC13: Sidebar stable on expand/collapse | D2 | CSS grid constraints are static rules -- stable regardless of toggle state |
