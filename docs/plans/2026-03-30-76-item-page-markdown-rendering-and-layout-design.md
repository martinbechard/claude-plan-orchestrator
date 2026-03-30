# Design: 76 Item Page Markdown Rendering and Layout

Source: tmp/plans/.claimed/76-item-page-markdown-rendering-and-layout.md
Requirements: docs/plans/2026-03-30-76-item-page-markdown-rendering-and-layout-requirements.md
Agent: systems-designer (task 0.1)

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
- HTMLResponse is already imported in item.py

## Data Flow

### Current Flow (all artifacts as plain text)

```
User expands stage / clicks artifact link
    |
    v
JS: fetch('/item/{slug}/artifact-content?path={path}')
    |
    v
Python: item_artifact_content()
    - Validates path within project root
    - Reads file as UTF-8 text
    - Returns PlainTextResponse(content=text)
    |
    v
JS: response.text()
    |
    v
JS: pre.textContent = text   (renders as monospace plain text)
```

### Proposed Flow (markdown files rendered as HTML)

```
User expands stage / clicks artifact link
    |
    v
JS: detect if path ends with '.md'
    |
    +-- NOT .md --> fetch('/item/{slug}/artifact-content?path={path}')
    |                   |
    |                   v
    |               Python: Returns PlainTextResponse (unchanged)
    |                   |
    |                   v
    |               JS: pre.textContent = text  (unchanged)
    |
    +-- IS .md ---> fetch('/item/{slug}/artifact-content?path={path}&render=html')
                        |
                        v
                    Python: item_artifact_content()
                        - Validates path within project root
                        - Detects .md extension + render=html param
                        - Calls _render_md_to_html(requested_path)
                        - Returns HTMLResponse(content=html_string)
                        |
                        v
                    JS: response.text()
                        |
                        v
                    JS: create div.rendered-markdown (or reuse existing)
                        div.innerHTML = html_string
                        hide pre element, show div element
```

### Content-Type Contract

| Condition | Response Type | Content-Type Header |
|---|---|---|
| No render param | PlainTextResponse | text/plain; charset=utf-8 |
| render=html but file is not .md | PlainTextResponse | text/plain; charset=utf-8 |
| render=html and file is .md | HTMLResponse | text/html; charset=utf-8 |

The client can use the response Content-Type header as a secondary signal to
confirm rendering mode, but the primary decision is made client-side based on
the file extension before the fetch.

## Design Decisions

### D1: Server-side markdown rendering via artifact-content endpoint

Addresses: P1, FR1
Satisfies: AC1, AC2, AC3, AC4, AC5, AC6
Files: langgraph_pipeline/web/routes/item.py

**Approach:** Modify the GET /item/{slug}/artifact-content endpoint to accept an
optional render=html query parameter. When the file has a .md extension and
render=html is requested, use the existing _render_md_to_html() infrastructure
to return an HTMLResponse instead of PlainTextResponse. This reuses the proven
server-side rendering pipeline rather than introducing a new client-side library.

**Endpoint signature change:**

```python
@router.get("/item/{slug}/artifact-content")
def item_artifact_content(
    slug: str,
    path: str = Query(..., description="Relative path to the artifact file"),
    render: Optional[str] = Query(None, description="Set to 'html' for markdown rendering"),
) -> PlainTextResponse | HTMLResponse:
```

Note: Remove response_class=PlainTextResponse from the decorator since the
function now returns either PlainTextResponse or HTMLResponse depending on
the render parameter and file extension.

**Rendering logic (appended before the final return):**

```python
    content = requested.read_text(encoding="utf-8", errors="replace")

    if render == "html" and requested.suffix.lower() == ".md":
        html = _render_md_to_html(requested)
        if html:
            return HTMLResponse(content=html)
        # Fall through to plain text if rendering fails

    return PlainTextResponse(content=content)
```

**Key decisions:**
- The render parameter is optional and defaults to None, preserving backward
  compatibility (NF1). Existing callers that omit the parameter get plain text.
- Only .md files are eligible for HTML rendering. Requesting render=html on a
  .py or .json file returns plain text silently (no error).
- If _render_md_to_html returns an empty string (error case), the endpoint
  falls back to plain text. This is a graceful degradation -- the user sees
  raw markdown rather than an error page.
- The function reads the file content once for the plain-text path. The
  _render_md_to_html function reads the file independently (it takes a Path,
  not a string). This is acceptable because the file is small (typical
  markdown artifacts are under 100KB) and the code path only runs for .md files.

**Security considerations:**
- The existing path validation (directory traversal protection) remains unchanged
  and runs before any rendering logic.
- _render_md_to_html already handles exceptions internally, returning "" on error.
- The rendered HTML is trusted content from the project's own files, not
  user-uploaded content, so XSS is not a concern in this context.

### D2: Client-side markdown-aware display in artifact viewers

Addresses: P1, FR1
Satisfies: AC1, AC2, AC3, AC4, AC5, AC6, AC7
Files: langgraph_pipeline/web/templates/item.html

**Approach:** Modify the JavaScript in both artifact viewer contexts (step explorer
loadStageArtifacts and output artifacts click handler) to detect .md file extensions
from the artifact path. For markdown files: (a) fetch with render=html parameter,
(b) display the returned HTML using innerHTML in a styled div element instead of
textContent in a pre element. For non-markdown files, keep the existing pre/textContent
behavior unchanged. The styled div reuses the existing .requirements-body CSS class
which already handles headings, lists, code blocks, and tables.

**Markdown detection function:**

```javascript
function isMdFile(path) {
    return path && path.toLowerCase().endsWith('.md');
}
```

**Step explorer loadStageArtifacts modification:**

For each .step-artifact-content element, the current code sets pre.textContent.
The modification adds a sibling div element for markdown content:

```javascript
function loadStageArtifacts(stageEl) {
    stageEl.querySelectorAll('.step-artifact-content').forEach(function (pre) {
        if (pre.dataset.loaded) { return; }
        pre.dataset.loaded = '1';
        var artifactPath = pre.dataset.artifactPath;
        var isMd = isMdFile(artifactPath);
        var url = '/item/' + encodeURIComponent(slug) +
            '/artifact-content?path=' + encodeURIComponent(artifactPath);
        if (isMd) { url += '&render=html'; }

        pre.hidden = false;
        pre.textContent = 'Loading...';

        fetch(url)
            .then(function (r) {
                if (!r.ok) { throw new Error('HTTP ' + r.status); }
                return r.text();
            })
            .then(function (content) {
                if (isMd) {
                    // Create a div sibling for rendered markdown
                    var mdDiv = document.createElement('div');
                    mdDiv.className = 'step-artifact-content rendered-markdown requirements-body';
                    mdDiv.innerHTML = content;
                    pre.hidden = true;
                    pre.parentNode.insertBefore(mdDiv, pre.nextSibling);
                } else {
                    pre.textContent = content;
                }
            })
            .catch(function (err) { pre.textContent = 'Failed to load: ' + err.message; });
    });
}
```

**Output artifacts click handler modification:**

Same pattern -- detect .md, fetch with render=html, create a styled div:

```javascript
if (pre.dataset.loaded) { return; }
pre.dataset.loaded = '1';
var artifactPath = btn.dataset.artifactPath;
var isMd = isMdFile(artifactPath);
var url = '/item/' + encodeURIComponent(slug) +
    '/artifact-content?path=' + encodeURIComponent(artifactPath);
if (isMd) { url += '&render=html'; }

fetch(url)
    .then(function (r) {
        if (!r.ok) { throw new Error('HTTP ' + r.status); }
        return r.text();
    })
    .then(function (content) {
        if (isMd) {
            var mdDiv = document.createElement('div');
            mdDiv.className = 'artifact-viewer-content rendered-markdown requirements-body';
            mdDiv.innerHTML = content;
            pre.hidden = true;
            pre.parentNode.insertBefore(mdDiv, pre.nextSibling);
        } else {
            pre.textContent = content;
        }
    })
    .catch(function (err) { pre.textContent = 'Failed to load: ' + err.message; });
```

**Template changes:**

No structural changes to item.html template are needed. The pre elements remain
in the template as the initial container. The JavaScript dynamically creates div
elements when markdown content is loaded. This avoids template-level branching
and keeps the server-rendered HTML simple.

**Key decisions:**
- The div is created dynamically rather than pre-existing in the template. This
  avoids adding complexity to the Jinja2 template and means no changes to the
  server-side template context.
- The pre element is hidden (not removed) when markdown is displayed. This keeps
  the DOM structure stable for the data-loaded caching logic.
- The div gets both requirements-body (for existing markdown styles) and
  rendered-markdown (for any artifact-specific overrides needed).
- innerHTML is used for trusted server-rendered HTML. The content comes from
  _render_md_to_html which processes project files, not user-uploaded content.

### D3: CSS grid overflow containment for two-column layout

Addresses: P2, FR2
Satisfies: AC8, AC9, AC10, AC12
Files: langgraph_pipeline/web/templates/item.html

**Approach:** Add min-width: 0 to the left column grid child (the first child of
.item-layout). This is the standard CSS grid overflow fix -- by default, grid items
have min-width: auto, which prevents them from shrinking below their content size.
Setting min-width: 0 allows the grid item to shrink to fit within the 1fr allocation.
Additionally, add overflow: hidden on the left column container to clip any content
that still attempts to escape.

**CSS changes:**

```css
/* Fix grid overflow: allow left column to shrink below content width */
.item-layout > :first-child {
    min-width: 0;
    overflow: hidden;
}
```

**Why min-width: 0:**

CSS grid specification defines that grid items have an implicit min-width: auto,
which resolves to the item's content minimum size. For a grid with columns
"1fr 360px", if the left column content is wider than the 1fr allocation (e.g.,
a 2000px pre element), the grid item refuses to shrink below 2000px, pushing
the 360px sidebar to the right.

Setting min-width: 0 overrides this behavior, telling the grid item it is
allowed to be narrower than its content. The content then overflows the item
(clipped by overflow: hidden) rather than expanding the grid cell.

**Why overflow: hidden (not overflow: auto):**

- overflow: hidden clips content that exceeds the column width. This is correct
  for the column-level container because individual artifact viewers have their
  own overflow-x: auto for horizontal scrolling.
- overflow: auto on the column would add a horizontal scrollbar to the entire
  left column, which is visually wrong -- the scroll should be on each artifact
  viewer, not the column.
- overflow: hidden also establishes a new block formatting context, which
  provides an additional layer of containment for floated or positioned content.

**Tradeoff analysis (min-width: 0 vs overflow: hidden alone):**

| Approach | Pros | Cons |
|---|---|---|
| min-width: 0 only | Standards-compliant grid fix, no content clipping | Content could still visually overflow if child lacks overflow handling |
| overflow: hidden only | Clips overflow visually | Does not fix the grid sizing -- the column still expands internally |
| Both (chosen) | Grid sizes correctly AND visual overflow is clipped | Children must handle their own horizontal scrolling |

Using both together is the robust solution. The grid sizes the column correctly
(min-width: 0), and any edge cases where content still tries to escape are
caught by overflow: hidden on the column.

**Viewport behavior:**

- Above 900px: Two-column grid (1fr 360px). The fix applies to the left column.
- Below 900px: Single column (1fr). min-width: 0 and overflow: hidden remain
  harmless because the single column already fills the viewport width.

### D4: Overflow scrolling for wide content within artifacts

Addresses: FR2
Satisfies: AC10, AC11
Files: langgraph_pipeline/web/templates/item.html

**Approach:** Ensure all artifact content containers have proper overflow handling.
The existing pre tags already have overflow-x: auto. For the new rendered markdown
div containers, add overflow-x: auto and max-width: 100%. Within rendered markdown,
pre and code blocks must also have overflow-x: auto so wide code examples scroll
horizontally rather than breaking out of the column.

**CSS for rendered markdown containers:**

```css
.rendered-markdown {
    overflow-x: auto;
    max-width: 100%;
}
```

The .requirements-body class already defines overflow-x: auto on pre elements
within it. This means code blocks inside rendered markdown will scroll
horizontally. No additional CSS is needed for code blocks specifically.

**Existing .requirements-body pre styles (already in item.html):**

```css
.requirements-body pre {
    background: #1a1a2e;
    border-radius: 6px;
    padding: 1rem;
    overflow-x: auto;       /* already handles wide code blocks */
    margin: 0 0 0.75em;
}
```

**Overflow cascade:**

```
.item-layout > :first-child      overflow: hidden  (column-level clip)
    |
    +-- .step-artifact-content    overflow-x: auto  (pre, already exists)
    |
    +-- .rendered-markdown        overflow-x: auto  (new div for md content)
        |
        +-- pre (code blocks)    overflow-x: auto  (via .requirements-body pre)
        |
        +-- table                width: 100%        (via .requirements-body table)
```

**Key decisions:**
- Tables use width: 100% (already in .requirements-body) which constrains them
  to the container width. Very wide tables will compress columns rather than
  overflow. If table content cannot compress (e.g., long unbreakable strings),
  the container-level overflow-x: auto provides a scrollbar.
- max-width: 100% on .rendered-markdown ensures the div never exceeds the
  parent container, even if the HTML content includes elements with explicit
  width attributes.

## Styling Strategy for Rendered Markdown in Artifact Viewers

The existing .requirements-body CSS class provides comprehensive markdown styling
for a white-background context (the requirements section of the item page). The
artifact viewers, however, use a dark background (#1a1a2e) for pre elements.

**Two contexts for rendered markdown:**

1. **Step explorer artifacts** (left column): Currently dark background pre.
   Rendered markdown should switch to a light/white background to match the
   requirements styling, since formatted text with headings and lists reads
   poorly on dark backgrounds.

2. **Output artifact viewers** (right sidebar): Currently dark background pre
   inside a bordered viewer container. Same treatment -- rendered markdown
   switches to light background.

**Styling approach:**

The rendered-markdown div gets the requirements-body class, which provides
white-background styling with appropriate typography. The dark-background pre
element is hidden when markdown is displayed, so there is no visual conflict.

**Artifact-specific overrides:**

```css
/* Step explorer markdown: constrain height like the pre element */
.step-artifact .rendered-markdown {
    max-height: 400px;
    overflow-y: auto;
    padding: 0.75rem 1rem;
    border-radius: 6px;
    border: 1px solid #e2e8f0;
}

/* Output artifact markdown: match the viewer container style */
.artifact-viewer .rendered-markdown {
    max-height: 400px;
    overflow-y: auto;
    padding: 0.75rem 1rem;
}
```

These overrides preserve the height constraint (max-height: 400px) that the
existing pre elements have, and add vertical scrolling for long documents.

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1, D2 | Server renders markdown headings to HTML via _render_md_to_html(); client displays via innerHTML in styled div |
| AC2 | D1, D2 | Server renders markdown lists to HTML; client displays rendered output in requirements-body styled container |
| AC3 | D1, D2 | Server renders fenced code blocks via fenced_code extension; .requirements-body pre styles code blocks |
| AC4 | D1, D2 | Python markdown library with fenced_code and tables extensions covers bold, italic, links, blockquotes, tables |
| AC5 | D1, D2 | Raw markdown syntax converted to HTML server-side; client uses innerHTML so raw syntax never visible |
| AC6 | D1, D2 | Both artifact viewer contexts (step explorer, output artifacts) detect .md and fetch with render=html |
| AC7 | D2 | Same isMdFile() detection and fetch logic applied in both loadStageArtifacts() and output artifact click handler |
| AC8 | D3 | min-width: 0 on left column grid child allows proper 1fr sizing; sidebar stays at fixed 360px |
| AC9 | D3 | overflow: hidden on left column clips any remaining overflow; sidebar unaffected |
| AC10 | D3, D4 | Grid containment (D3) keeps content in column; overflow-x: auto (D4) provides horizontal scroll |
| AC11 | D4 | overflow-x: auto on .rendered-markdown and pre within .requirements-body enables horizontal scrolling |
| AC12 | D3 | min-width: 0 and overflow: hidden apply to all left-column content regardless of how many sections are expanded |

## Risk Assessment

| Risk | Mitigation |
|---|---|
| innerHTML with server-rendered HTML could be an XSS vector | Content is from project files on the local filesystem, not user-uploaded. _render_md_to_html processes trusted content. |
| _render_md_to_html returns empty string on error | Endpoint falls back to PlainTextResponse, user sees raw markdown rather than an error |
| min-width: 0 could cause unexpected shrinking of left column content | overflow-x: auto on individual artifact containers provides horizontal scrolling for content that needs it |
| .requirements-body styles may not cover all markdown constructs | The existing styles cover h1-h4, lists, code blocks, tables, and blockquotes -- the same extensions used by _render_md_to_html |
| Dynamic DOM manipulation (creating div, hiding pre) could break caching | The data-loaded attribute is on the pre element, which remains in the DOM. The caching logic checks pre.dataset.loaded before fetching, so it works regardless of whether the content is in the pre or a sibling div |
