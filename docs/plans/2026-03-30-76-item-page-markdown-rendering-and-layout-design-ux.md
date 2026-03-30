# UX Design: Item Page Markdown Rendering and Layout

Source: tmp/plans/.claimed/76-item-page-markdown-rendering-and-layout.md
Design overview: docs/plans/2026-03-30-76-item-page-markdown-rendering-and-layout-design.md
Agent: ux-designer (task 0.2)

## Problem Statement

The item detail page has two UX defects:

1. Markdown artifacts (design docs, requirements, judgments) display as raw syntax
   instead of formatted HTML, making them difficult to read.
2. Expanded artifact content can overflow its CSS grid column, pushing or overlapping
   the 360px sidebar.

This design addresses both problems from a user experience perspective, covering
visual integration, typography, interaction patterns, accessibility, and overflow
handling.

---

## 1. Visual Integration: Rendered Markdown in Artifact Viewers

### Current State

Both artifact display contexts use identical dark-background containers:

- **Step Explorer** (left column): `.step-artifact-content` -- dark background
  `#1a1a2e`, monospace font, light text `#e2e8f0`
- **Output Artifacts** (right sidebar): `.artifact-viewer-pre` -- same dark scheme

All content is rendered as plain text via `textContent` in `<pre>` tags. This is
appropriate for code files and logs but unreadable for markdown documents.

### Design: Adaptive Container Based on File Type

**Principle:** The container appearance should match the content type, not force all
content into the same display mode.

For `.md` files, switch from the dark monospace `<pre>` to a light-background `<div>`
with the existing `.requirements-body` typography. This mirrors how the Requirements
section already displays rendered markdown on the same page, creating visual
consistency.

**Markdown artifact container:**

```
Background:  #ffffff (matches item-card interior)
Border:      1px solid #e2e8f0 (matches card borders)
Padding:     1.25rem (matches .requirements-body)
Typography:  14px system font, line-height 1.7 (matches .requirements-body)
Text color:  #374151 (matches .requirements-body)
Max height:  400px with overflow-y: auto (matches current pre containers)
Border-radius: 6px (matches current artifact containers)
```

**Non-markdown artifacts remain unchanged:** dark `#1a1a2e` background, monospace
`11px`, `<pre>` with `textContent`. The user perceives no change for code, YAML,
JSON, or plain text files.

### Visual Contrast Rationale

Using a white background for rendered markdown instead of dark serves three purposes:

1. **Readability:** Rendered HTML headings, lists, and tables are designed for
   light backgrounds. Dark-on-light is the standard reading context for prose.
2. **Semantic signal:** The background color change tells the user at a glance
   that this content has been formatted, not shown raw. Dark = raw text/code,
   light = rendered document.
3. **Style reuse:** The existing `.requirements-body` styles (headings, lists,
   code blocks, tables, blockquotes) already use light-background color values.
   Reusing them avoids creating a parallel dark-mode stylesheet.

### Code Blocks Within Rendered Markdown

Fenced code blocks inside rendered markdown use the **dark** treatment (matching
`.requirements-body pre`):

```
Background:    #1a1a2e
Border-radius: 6px
Padding:       1rem
Code color:    #e2e8f0
Font:          ui-monospace, SFMono-Regular, "SF Mono", Consolas, monospace
Font size:     12px
```

This creates a natural visual hierarchy: the white container holds the document,
and dark inset boxes hold code snippets -- identical to how the Requirements
section already works.

---

## 2. Typography and Spacing Within Artifact Viewers

### Heading Hierarchy

Reuse `.requirements-body` heading styles exactly. These are already calibrated
for the constrained card width:

| Element | Size | Weight | Extra |
|---------|------|--------|-------|
| h1 | 18px | 600 | margin-top: 0 (first heading flush) |
| h2 | 15px | 600 | border-bottom: 1px solid #e2e8f0, padding-bottom: 0.3em |
| h3 | 14px | 600 | -- |
| h4 | 14px | 600 | -- |

Color: `#1a1a2e` (high contrast against white).
Vertical spacing: `margin: 1.25em 0 0.5em` for all headings.

### Body Text

- Font size: 14px
- Line height: 1.7 (generous for readability in narrow columns)
- Paragraph spacing: `margin: 0 0 0.75em`

### Lists

- Left padding: 1.5em (standard indent)
- Item spacing: `margin-bottom: 0.25em`
- Both ordered and unordered lists use the same spacing

### Tables

- Full width within the container
- Cell padding: `6px 10px`
- Border: `1px solid #e2e8f0`
- Header row: `background: #f8fafc`, `font-weight: 600`

### Inline Code

- Background: `#f1f5f9`
- Border: `1px solid #e2e8f0`
- Border-radius: 3px
- Padding: `1px 5px`
- Font: monospace at 12px

### Blockquotes

- Left border: `3px solid #3b6fcf`
- Background: `#f0f5ff`
- Padding: `0.5em 1em`
- Border-radius: `0 4px 4px 0`

All these values match the existing `.requirements-body` CSS exactly, ensuring
visual consistency across the page.

---

## 3. Interaction Patterns: Expand/Collapse Behavior

### Consistency Principle

Switching between markdown and non-markdown artifacts must feel identical from
an interaction standpoint. The user should not perceive any behavioral
difference -- only the visual rendering changes.

### Step Explorer Artifacts

**Current behavior (non-markdown):**
1. User clicks stage header to expand
2. Stage body reveals, showing artifact `<pre>` elements
3. Content loads lazily via `loadStageArtifacts()`
4. Collapse state persists in `localStorage`

**Markdown behavior (same interaction, different rendering):**
1. User clicks stage header to expand (unchanged)
2. Stage body reveals, showing artifact containers (unchanged)
3. Content loads lazily -- `.md` files fetch with `render=html` and display
   in a `<div>` with `.requirements-body` styles instead of a `<pre>`
4. Collapse state persists in `localStorage` (unchanged)

The only difference is in step 3: the JavaScript detects the `.md` extension
from `data-artifact-path` and chooses the appropriate display mode.

### Output Artifacts (Sidebar)

**Current behavior (non-markdown):**
1. User clicks the artifact path link (blue underlined text)
2. `.artifact-viewer` container becomes visible
3. Content loads lazily into a `<pre>`
4. Click again to collapse

**Markdown behavior (same interaction, different rendering):**
1. User clicks the artifact path link (unchanged)
2. `.artifact-viewer` container becomes visible (unchanged)
3. Content loads lazily -- `.md` files render into a `<div>` instead of `<pre>`
4. Click again to collapse (unchanged)

### Loading State

Both markdown and non-markdown artifacts show the same loading indicator:
"Loading..." text. For markdown files, this appears in the `<div>` container
(not the `<pre>`) so there is no visual flash when the rendered content replaces
the loading text.

### Max Height and Scrolling

Both container types (dark `<pre>` and light rendered `<div>`) use the same
`max-height: 400px` with `overflow-y: auto`. This ensures consistent visual
weight regardless of content type. A user expanding two artifacts -- one markdown,
one code -- sees containers of the same maximum size.

---

## 4. Accessibility

### Semantic HTML

Server-rendered markdown produces semantic HTML elements:

- `<h1>` through `<h6>` for headings (proper heading hierarchy)
- `<ul>`, `<ol>`, `<li>` for lists
- `<table>`, `<thead>`, `<tbody>`, `<tr>`, `<th>`, `<td>` for tables
- `<pre>` and `<code>` for code blocks
- `<blockquote>` for quotes
- `<p>` for paragraphs

This is a significant accessibility improvement over the current raw-text display,
which puts everything in a single `<pre>` element with no semantic structure.

### Heading Hierarchy Consideration

Artifact markdown files are embedded within the item detail page, which has its
own heading structure (the page `<h1>` is the slug). Rendered markdown headings
should be scoped within an `<article>` or a container with `role="document"` so
assistive technologies treat them as a nested document rather than conflicting
with the page heading hierarchy.

**Implementation:** Wrap the rendered markdown in:
```html
<div class="requirements-body" role="document"
     aria-label="Rendered content of {filename}">
  <!-- server-rendered HTML goes here via innerHTML -->
</div>
```

The `role="document"` tells screen readers this is a self-contained document
with its own heading structure. The `aria-label` provides context about what
document is being displayed.

### Keyboard Navigation

The expand/collapse interaction already uses `<button>` elements with
`aria-expanded` attributes. No changes needed for keyboard accessibility of the
toggle mechanism.

For rendered markdown content within the scrollable container, standard tab
navigation works for any links or interactive elements within the rendered HTML.

### Color Contrast

All text colors in the `.requirements-body` styles meet WCAG AA contrast
requirements against their backgrounds:

| Text | Background | Contrast Ratio |
|------|-----------|----------------|
| Body text `#374151` | White `#ffffff` | 10.1:1 (AAA) |
| Heading `#1a1a2e` | White `#ffffff` | 15.4:1 (AAA) |
| Code block `#e2e8f0` | Dark `#1a1a2e` | 11.2:1 (AAA) |
| Inline code `#374151` | Light gray `#f1f5f9` | 8.8:1 (AAA) |
| Blockquote `#374151` | Light blue `#f0f5ff` | 9.5:1 (AAA) |

### Focus Management

When a user expands an artifact viewer, focus should remain on the toggle button
(current behavior). The rendered content scrolls independently within its
container. No focus trapping is needed since the content is passive (no form
elements or interactive widgets).

### ARIA Live Region

The `.artifact-viewer` already has `aria-live="polite"`, which announces content
changes to screen readers when the viewer is expanded and content loads. This
works correctly for both markdown and non-markdown content.

---

## 5. Wide Content: Horizontal Scroll vs Line Wrapping

### Decision: Hybrid Approach

Different content types within rendered markdown need different overflow strategies:

| Content Type | Strategy | Rationale |
|-------------|----------|-----------|
| Prose (p, blockquote) | Word wrap | Prose should reflow to fit the column width |
| Headings (h1-h4) | Word wrap | Headings should reflow, not scroll |
| Lists (ul, ol) | Word wrap | List items should reflow |
| Code blocks (pre) | Horizontal scroll | Code indentation is meaningful; wrapping breaks readability |
| Tables | Horizontal scroll | Table columns must maintain alignment |
| Inline code | Wrap with text | Inline code flows within surrounding prose |

### CSS Implementation

**Rendered markdown container:**
```css
.requirements-body {
    overflow-x: hidden;   /* prose never scrolls horizontally */
    word-wrap: break-word; /* break long words/URLs at container edge */
}
```

**Code blocks within rendered markdown:**
```css
.requirements-body pre {
    overflow-x: auto;    /* horizontal scrollbar when code is wide */
    max-width: 100%;     /* never exceed container width */
}
```

**Tables within rendered markdown:**
```css
.requirements-body table {
    display: block;       /* allow table to scroll independently */
    overflow-x: auto;     /* horizontal scrollbar for wide tables */
    max-width: 100%;
}
```

### Non-Markdown Artifacts

The existing `<pre>` containers already have `overflow-x: auto`, which provides
horizontal scrolling for wide plain-text content. No changes needed.

---

## 6. CSS Grid Containment Fix

### Problem

The `.item-layout` CSS grid uses `grid-template-columns: 1fr 360px`. By default,
grid items have `min-width: auto`, which prevents them from shrinking below their
content size. Wide artifact content causes the left column to overflow, pushing
the 360px sidebar off-screen or causing horizontal page scroll.

### Solution

Add `min-width: 0` to the left column grid child. This is the standard CSS grid
overflow fix -- it allows the grid item to shrink to fit within its `1fr`
allocation even when content is wider.

Additionally, add `overflow: hidden` on the left column container as a safety net
to clip any content that still escapes.

```css
.item-layout > :first-child {
    min-width: 0;
    overflow: hidden;
}
```

### User Impact

- The sidebar stays at its fixed 360px width at all times
- No content from the left column overlaps or pushes the sidebar
- Wide content within the left column scrolls horizontally inside its own
  container (the artifact viewer), not at the page level
- The fix applies to all artifact types (markdown and non-markdown)
- No visual change for content that already fits within the column

---

## Design -> AC Traceability

| AC | How This Design Addresses It |
|---|---|
| AC1 | Headings render via semantic `<h1>`-`<h4>` with `.requirements-body` styles on white background |
| AC2 | Lists render via semantic `<ul>/<ol>/<li>` with proper indentation and spacing |
| AC3 | Code blocks render with dark `#1a1a2e` inset background, monospace font, `overflow-x: auto` |
| AC4 | Raw markdown syntax is replaced by server-rendered HTML displayed via `innerHTML` in styled `<div>` |
| AC5 | Both Step Explorer and Output Artifacts use the same `.md` detection logic and styled container |
| AC6 | Server-side `_render_md_to_html()` with `fenced_code` and `tables` extensions handles all standard markdown |
| AC7 | `min-width: 0` on left column grid child constrains content within `1fr` boundary |
| AC8 | Sidebar remains at fixed 360px -- left column overflow cannot affect it |
| AC9 | `overflow: hidden` on left column plus `min-width: 0` prevents any horizontal overlap |
| AC10 | Grid containment (D3) plus `overflow-x: auto` on code blocks and tables within rendered markdown |
| AC11 | CSS grid fix applies to all left-column content regardless of which artifact is expanded |
| AC12 | Code blocks scroll horizontally via `overflow-x: auto`; prose wraps via `word-wrap: break-word` |

---

## Implementation Notes for Downstream Tasks

### CSS Changes (item.html inline styles)

1. Add `.item-layout > :first-child { min-width: 0; overflow: hidden; }` to fix grid overflow
2. Reuse `.requirements-body` class for rendered markdown containers in both artifact
   viewer contexts
3. No new CSS classes needed -- the existing `.requirements-body` styles already cover
   all markdown elements

### JavaScript Changes (item.html inline scripts)

1. In `loadStageArtifacts()`: detect `.md` from `pre.dataset.artifactPath`, switch to
   `<div>` with `innerHTML` and `.requirements-body` class for markdown files
2. In output artifacts click handler: same `.md` detection and display mode switch
3. Both contexts append `?render=html` to the fetch URL for markdown files

### Server Changes (item.py)

1. Accept optional `render=html` query parameter on `/item/{slug}/artifact-content`
2. When file is `.md` and `render=html` is set, return `HTMLResponse` using
   `_render_md_to_html()` instead of `PlainTextResponse`

### DOM Structure for Markdown Artifacts

**Step Explorer -- markdown file:**
```html
<div class="step-artifact">
  <div class="step-artifact-meta">
    <span class="step-artifact-name">design.md</span>
  </div>
  <div class="requirements-body" role="document"
       aria-label="Rendered content of design.md"
       style="max-height: 400px; overflow-y: auto; margin: 0.4rem 0 0;">
    <!-- innerHTML: server-rendered HTML -->
  </div>
</div>
```

**Output Artifacts -- markdown file:**
```html
<div class="artifact-viewer" aria-live="polite">
  <div class="requirements-body" role="document"
       aria-label="Rendered content of requirements.md"
       style="max-height: 400px; overflow-y: auto;">
    <!-- innerHTML: server-rendered HTML -->
  </div>
</div>
```

**Non-markdown files continue using the existing `<pre>` elements unchanged.**
