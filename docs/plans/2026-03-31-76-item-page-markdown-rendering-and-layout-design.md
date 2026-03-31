# Design: 76 Item Page Markdown Rendering and Layout

Source work item: tmp/plans/.claimed/76-item-page-markdown-rendering-and-layout.md
Requirements: docs/plans/2026-03-31-76-item-page-markdown-rendering-and-layout-requirements.md
Date: 2026-03-31

## Architecture Overview

The item detail page uses a step explorer accordion (built in item #74) to display
pipeline artifacts. Each artifact's content is fetched via AJAX from the
/item/{slug}/artifact-content endpoint and displayed as plain text in pre elements.

Two problems exist:

1. Markdown rendering regression: Markdown files (.md) are displayed as raw text
   instead of rendered HTML. The backend already converts markdown to HTML via
   Python's markdown library for template variables (requirements_html,
   original_request_html, etc.), but the step explorer's AJAX-loaded content
   bypasses this -- the endpoint returns plain text and the JS sets it via
   .textContent on a pre element.

2. Layout overflow: The step explorer's artifact content containers lack CSS
   constraints to prevent overflow beyond the left column, potentially breaking
   the two-column grid layout when wide content (long lines, wide code blocks)
   is displayed.

The fix is purely frontend: add client-side markdown rendering for AJAX-loaded
artifact content and enforce CSS width constraints on artifact containers.

### Current Content Loading Flow

1. Template renders pre.step-artifact-content with data-artifact-path attribute
2. User clicks stage header -> JS calls loadStageArtifacts()
3. JS fetches from /item/{slug}/artifact-content?path={path}
4. Content set via pre.textContent = text (no markdown processing)
5. Content cached in localStorage

### Proposed Content Loading Flow

1. Same template structure, but with both pre (for non-markdown) and div (for markdown)
2. User clicks stage header -> JS calls loadStageArtifacts()
3. JS fetches from /item/{slug}/artifact-content?path={path}
4. JS checks file extension from data-artifact-path
5. For .md files: render through marked.js, display as innerHTML in styled div
6. For non-.md files: display as textContent in pre (current behavior)
7. Content cached in localStorage

## Key Files to Modify

- langgraph_pipeline/web/templates/item.html -- add markdown library, modify artifact loading JS
- langgraph_pipeline/web/static/style.css -- add markdown content styling, fix layout constraints

No backend changes required. The /item/{slug}/artifact-content endpoint continues to
return plain text for all files.

## Design Decisions

### D1: Client-side markdown rendering with marked.js

- Addresses: P1, P3, FR1
- Satisfies: AC1, AC2, AC3, AC4, AC8, AC9, AC12, AC13, AC14
- Approach: Add the marked.js library (via CDN with SRI hash) to item.html. When
  artifact content is fetched via AJAX, check the file path extension from the
  data-artifact-path attribute. For markdown files (.md, .markdown), render through
  marked.parse() and display as innerHTML in a styled div container (replacing the
  hidden pre). For non-markdown files, continue using the current pre element with
  textContent. This provides full GFM support (headings, lists, code blocks, inline
  formatting, links, tables) without backend changes. The marked.js library is
  well-maintained, small (~40KB), and supports GitHub Flavored Markdown.
- Files: item.html

### D2: CSS layout constraints for two-column stability

- Addresses: P2, P4, FR2
- Satisfies: AC5, AC6, AC7, AC10, AC11, AC15, AC16, AC17
- Approach: Apply three CSS fixes to prevent layout breakage:
  (a) Add min-width: 0 to the left grid column child (the step-explorer container).
      This is the standard fix for CSS Grid blowout -- without it, grid items default
      to min-width: auto, which allows content to expand beyond the grid cell.
  (b) Add max-width: 100% and overflow-x: auto to artifact content containers
      (both pre and the new markdown div). This ensures wide content scrolls
      horizontally within its container rather than expanding the column.
  (c) For pre elements, use white-space: pre-wrap to allow line wrapping for
      very long lines, reducing the need for horizontal scrolling.
  These constraints keep all content within the left column boundary regardless
  of content width, preserving the right sidebar position.
- Files: style.css, item.html

### D3: Markdown content styling within artifact sections

- Addresses: P1, FR1
- Satisfies: AC1, AC2, AC3, AC13
- Approach: Add CSS rules for rendered markdown inside artifact sections using a
  .md-rendered class on the container div. Style headings with scaled sizes appropriate
  for embedded context (h1 at 1.3em, h2 at 1.15em, etc.). Lists with proper indentation
  and bullet/number styling. Code blocks with dark background, monospace font, and
  horizontal scroll. Inline code with subtle background. Links with visible coloring.
  Tables with borders and readable spacing. Blockquotes with left border accent.
  Reuse existing color scheme from the dark-themed artifact containers already in
  style.css. The rendered content container uses the same background and border-radius
  as the existing pre.step-artifact-content for visual consistency.
- Files: style.css

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1, D3 | marked.js renders # headings to h1-h6 elements; CSS styles with scaled sizes |
| AC2 | D1, D3 | marked.js renders - and 1. to ul/ol elements; CSS styles with indentation |
| AC3 | D1, D3 | marked.js renders fenced code blocks; CSS adds dark bg, monospace, scroll |
| AC4 | D1 | marked.js converts all raw syntax (#, *, ```) to HTML elements |
| AC5 | D2 | min-width: 0 on grid child prevents blowout; right column stays visible |
| AC6 | D2 | max-width: 100% on content containers constrains to left column |
| AC7 | D2 | overflow-x: auto prevents content from overlapping into sidebar area |
| AC8 | D1 | marked.parse() called on fetched content before display for .md files |
| AC9 | D1 | All artifact sections use the same loadStageArtifacts() code path |
| AC10 | D2 | max-width: 100%, overflow-x: auto enforce column width limit |
| AC11 | D2 | overflow-x: auto enables horizontal scroll for wide code blocks/lines |
| AC12 | D1 | Every artifact section with .md extension goes through marked.parse() |
| AC13 | D1, D3 | marked.js supports full GFM; CSS styles all standard elements |
| AC14 | D1 | Extension check covers .md and .markdown; rendering is not origin-dependent |
| AC15 | D2 | Grid layout structurally preserved via min-width: 0 on left column |
| AC16 | D2 | max-width + overflow prevent content from crossing column boundary |
| AC17 | D2 | CSS grid layout is structurally independent of content expansion state |
