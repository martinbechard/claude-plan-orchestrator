# Design: 76 Item Page Markdown Rendering and Layout

Source work item: tmp/plans/.claimed/76-item-page-markdown-rendering-and-layout.md
Requirements: docs/plans/2026-03-31-76-item-page-markdown-rendering-and-layout-requirements.md
Date: 2026-03-31

## Architecture Overview

The item detail page uses a two-column CSS grid layout (1fr 360px above 900px).
The left column contains a step explorer accordion that lazy-loads pipeline
stage artifacts via AJAX from /item/{slug}/artifact-content. The right column
sidebar contains plan tasks, output artifacts, validation results, and traces.

Two problems exist:

1. Markdown rendering regression (P1, FR1): Markdown files (.md) are displayed
   as raw text in both artifact loading paths. The backend already renders other
   markdown sections server-side via _render_md_to_html(), but AJAX-loaded
   artifact content bypasses this -- both loadStageArtifacts() and the
   artifact-path-link click handler use pre.textContent for all content.

2. Layout overflow (P2, FR2): Expanded artifact content lacks CSS constraints.
   The CSS Grid default min-width: auto allows content to expand beyond its
   track, pushing or overlapping the 360px sidebar.

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
  loadStageArtifacts() and artifact-link click handler, add div.md-rendered
  containers, add CSS for rendered markdown and layout fixes
- langgraph_pipeline/web/static/style.css -- optional overflow fixes if
  item-layout styles are defined here rather than inline

No backend changes required.

## Design Decisions

### D1: Client-side markdown rendering with marked.js

- Addresses: P1, FR1
- Satisfies: AC1, AC2, AC5, AC6
- Approach: Add the marked.js library (via CDN with SRI hash) to item.html. In
  both loadStageArtifacts() and the artifact-path-link click handler, after
  fetching artifact text, check the file path for .md extension. For markdown
  files, render through marked.parse() and display as innerHTML in a
  div.md-rendered container (hide the pre, show the div). For non-markdown
  files, keep the existing pre + textContent behavior. This provides full GFM
  support including headings, lists, code blocks, bold, italic, links, tables,
  and blockquotes.

  A shared helper function renderArtifactContent(pre, mdDiv, text, path) ensures
  both code paths use identical .md detection and rendering logic, satisfying
  AC5 (every artifact section) and AC6 (all common elements).

  AC1 is satisfied because markdown files are converted to HTML before display.
  AC2 is satisfied because marked.js handles headings, lists, and code blocks.
- Files: langgraph_pipeline/web/templates/item.html

### D2: CSS layout constraints for two-column stability

- Addresses: P2, FR2
- Satisfies: AC3, AC4, AC7, AC8
- Approach: Apply three CSS fixes:
  (a) Add min-width: 0 to .item-layout > * (grid children). This is the standard
      fix for CSS Grid blowout -- without it, grid items default to min-width:
      auto, allowing content to expand beyond the track.
  (b) Add max-width: 100% and overflow-x: auto to artifact content containers
      (pre.step-artifact-content, pre.artifact-viewer-pre, and div.md-rendered).
      Wide content scrolls horizontally within the container.
  (c) Add overflow: hidden to the step-explorer container to prevent any child
      overflow from escaping the left column.

  AC3 is satisfied because expanding artifacts no longer pushes or overlaps the
  right column -- min-width: 0 constrains the grid track.
  AC4 is satisfied because the right column remains at its fixed 360px width
  regardless of left column content.
  AC7 is satisfied because content stays within column bounds via min-width: 0
  + max-width: 100%.
  AC8 is satisfied because sidebar layout is unaffected -- CSS constraints are
  static rules independent of expand/collapse state.
  Wide content (e.g. code blocks) gets overflow-x: auto for horizontal scrolling
  instead of breaking layout, further ensuring AC7 containment.
- Files: langgraph_pipeline/web/templates/item.html (inline styles section)

### D3: Dark-theme markdown content styling

- Addresses: P1, FR1
- Satisfies: AC1, AC2, AC6
- Approach: Add CSS rules for .md-rendered that style rendered markdown elements
  within the dark-themed artifact viewer: headings with scaled sizes (h1 at
  1.3em down to h6 at 0.85em), lists with indentation and proper bullet/number
  styling, code blocks with slightly darker background and monospace font
  matching existing pre styling, inline code with subtle background, links with
  visible coloring, tables with cell borders, blockquotes with left-border
  accent. Reuse the existing dark color scheme (#1a1a2e background, #e2e8f0
  text) for visual consistency. The div.md-rendered container uses the same
  background, padding, and border-radius as pre.step-artifact-content so
  markdown and non-markdown artifacts look cohesive.

  AC1 is reinforced because rendered HTML is visually styled (not just
  structurally correct). AC2 is reinforced because headings, lists, and code
  blocks have distinct visual treatment. AC6 is reinforced because all common
  elements (bold, italic, links, tables, blockquotes) have styled CSS rules.
- Files: langgraph_pipeline/web/templates/item.html (inline styles)

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1: Markdown rendered as formatted HTML | D1, D3 | marked.js parses markdown to HTML; D3 styles rendered output in dark theme |
| AC2: Headings, lists, code blocks render correctly | D1, D3 | marked.js converts markdown constructs to HTML elements; D3 styles them with scaled sizes, indentation, and monospace code blocks |
| AC3: Expanding avoids pushing/overlapping right column | D2 | min-width: 0 on grid children prevents left column from exceeding its track |
| AC4: Right column remains visible and in position | D2 | Grid constraints keep left column within 1fr allocation; 360px sidebar unaffected |
| AC5: Markdown-to-HTML applied to every artifact section | D1 | Both loadStageArtifacts() and artifact-link handler share renderArtifactContent() helper with identical .md detection |
| AC6: All common markdown elements rendered correctly | D1, D3 | marked.js supports full GFM (headings, lists, code, bold, italic, links, tables, blockquotes); D3 provides dark-theme CSS for each |
| AC7: Expanded content within column bounds | D2 | min-width: 0 + max-width: 100% + overflow: hidden on step-explorer constrain content; overflow-x: auto for horizontal scrolling |
| AC8: Sidebar unaffected on expand/collapse | D2 | CSS grid constraints are static rules -- stable regardless of toggle state |
