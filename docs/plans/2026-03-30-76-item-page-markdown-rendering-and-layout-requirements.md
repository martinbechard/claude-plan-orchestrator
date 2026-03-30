# Requirements: 76 Item Page Markdown Rendering and Layout

Source: tmp/plans/.claimed/76-item-page-markdown-rendering-and-layout.md

## Problem Statement

The item detail page has two display defects affecting artifact content:

1. Markdown files (.md) are displayed as raw text with visible syntax characters
   (hashes, asterisks, backtick fences) instead of rendered HTML. The server-side
   markdown rendering infrastructure exists (_render_md_to_html in item.py) but is
   not used by the artifact-content endpoint.

2. When an artifact section is expanded, its content can overflow the CSS grid
   left column and push or overlap the 360px right sidebar. The grid child lacks
   min-width: 0, so grid items cannot shrink below their intrinsic content width.

## Priorities

- P1: Restore markdown rendering for all artifact content sections (.md files)
- P2: Constrain expanded artifact content within the left column without
  affecting the sidebar layout

## Functional Requirements

- FR1: Markdown files fetched via the artifact-content endpoint must be
  rendered as formatted HTML (headings, lists, code blocks, tables,
  blockquotes) instead of raw text
- FR2: All artifact content (rendered markdown and plain text) must remain
  within the left column boundary of the two-column grid layout, with
  horizontal scrolling for content that exceeds the available width

## Use Cases

- UC1: A user expands a step explorer stage containing a markdown artifact
  (e.g., a design document or requirements file). The content appears with
  formatted headings, bulleted lists, and syntax-highlighted code blocks
  instead of raw markdown syntax.

- UC2: A user clicks an output artifact link for a .md file in the right
  sidebar. The inline viewer shows rendered HTML content with proper
  typography, matching the style used for requirements display elsewhere
  on the page.

- UC3: A user expands an artifact containing a wide code block or table. The
  content scrolls horizontally within its container rather than overflowing
  the column and pushing the sidebar.

- UC4: A user expands a non-markdown artifact (.json, .yaml, .py). The content
  continues to display as monospace plain text in a pre element, unchanged
  from current behavior.

## Acceptance Criteria

### Markdown Rendering (P1, FR1)

- AC1: Markdown headings (h1-h4) render as styled HTML heading elements in
  artifact viewers
- AC2: Markdown lists (ordered and unordered) render as styled HTML list
  elements in artifact viewers
- AC3: Fenced code blocks render with monospace font and dark background in
  artifact viewers
- AC4: Raw markdown syntax (hashes, asterisks, backtick fences) is not
  visible in the rendered output for .md files
- AC5: Both step explorer artifacts and output artifact viewers render
  markdown files as HTML
- AC6: Tables and blockquotes render correctly in artifact viewers when
  present in markdown files

### Layout Containment (P2, FR2)

- AC7: The left column content does not extend beyond the 1fr grid
  allocation at any viewport width above 900px
- AC8: The right sidebar maintains its 360px width when any artifact is
  expanded in the left column
- AC9: Expanded artifact content does not visually overlap or push the
  right sidebar
- AC10: Narrow viewport (below 900px) continues to stack columns
  vertically with full-width content
- AC11: Layout containment applies regardless of which artifact section
  is expanded

### Overflow Handling (FR2)

- AC12: Wide content (long lines, wide tables, wide code blocks) within
  artifact viewers scrolls horizontally rather than breaking the layout

## Non-Functional Requirements

- NF1: The artifact-content endpoint must remain backward compatible --
  requests without the render parameter return plain text as before
- NF2: No new JavaScript libraries are introduced; markdown rendering
  happens server-side using the existing Python markdown library
- NF3: Rendered markdown styles should reuse or extend the existing
  .requirements-body CSS class to maintain visual consistency
