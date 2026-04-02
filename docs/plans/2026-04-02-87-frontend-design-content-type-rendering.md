# Frontend Implementation Design: Content-Type-Aware Rendering

Competition entry for task 0.3 (frontend-coder agent).
Parent design: docs/plans/2026-04-02-87-item-page-content-type-aware-rendering-design.md
Requirements: docs/plans/2026-04-02-87-item-page-content-type-aware-rendering-requirements.md
Work item: tmp/plans/.claimed/87-item-page-content-type-aware-rendering.md

## Scope

All changes confined to a single file: langgraph_pipeline/web/templates/item.html.
Extends the existing renderArtifactContent(pre, mdDiv, text, path) function and the
marked.js CDN / .md-rendered div pattern established by feature 76.

## 1. CDN Resources to Add

Add immediately after the existing marked.js script tag (line 1153-1155 of item.html):

### highlight.js Core + Languages

```html
<!-- highlight.js dark theme CSS -->
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css"
      crossorigin="anonymous">
<!-- highlight.js core -->
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"
        crossorigin="anonymous"></script>
<!-- Language modules (loaded individually to minimize bundle) -->
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/json.min.js"
        crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/yaml.min.js"
        crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/python.min.js"
        crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/typescript.min.js"
        crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/xml.min.js"
        crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/css.min.js"
        crossorigin="anonymous"></script>
```

### Bundle Size Impact

- highlight.js core: ~50 KB gzipped
- Each language module: 2-8 KB gzipped
- github-dark.min.css: ~3 KB gzipped
- Total additional load: ~80 KB gzipped (comparable to marked.js at ~40 KB)
- All loaded from jsdelivr CDN (same origin as marked.js, benefiting from HTTP/2 multiplexing)

### Why highlight.js over Prism.js

- highlight.js has a simpler CDN integration (single core + per-language modules)
- Auto-detection capability as fallback (not used here, but available)
- github-dark theme matches the existing #1a1a2e dark background closely
- Language module loading matches the marked.js CDN pattern already in use

## 2. Extension Dispatch Architecture

Replace the current renderArtifactContent function body with an extension-based dispatcher.

### Extension-to-Language Mapping

```javascript
/* Extension-to-renderer mapping. */
var HLJS_LANGUAGE_MAP = {
    'json': 'json',
    'yaml': 'yaml',
    'yml': 'yaml',
    'py': 'python',
    'ts': 'typescript',
    'html': 'xml',
    'css': 'css'
};

var MARKDOWN_EXTENSIONS = { 'md': true };
var LOG_EXTENSIONS = { 'log': true };
```

### Dispatch Function

```javascript
/**
 * Render artifact text with content-type awareness.
 * Routes to markdown, JSON, YAML, log, or code renderers based on file extension.
 * Falls back to raw pre.textContent for unrecognized extensions.
 *
 * @param {HTMLPreElement} pre - The raw content pre element
 * @param {HTMLDivElement} mdDiv - The .md-rendered container div
 * @param {string} text - The file content
 * @param {string} path - The file path (used for extension extraction)
 */
function renderArtifactContent(pre, mdDiv, text, path) {
    var ext = extractExtension(path);

    if (MARKDOWN_EXTENSIONS[ext] && typeof marked !== 'undefined') {
        renderMarkdown(pre, mdDiv, text);
    } else if (ext === 'json') {
        renderJson(pre, mdDiv, text);
    } else if (LOG_EXTENSIONS[ext]) {
        renderLog(pre, mdDiv, text);
    } else if (HLJS_LANGUAGE_MAP[ext] && typeof hljs !== 'undefined') {
        renderHighlighted(pre, mdDiv, text, HLJS_LANGUAGE_MAP[ext]);
    } else {
        renderPlainText(pre, mdDiv, text);
    }
}

function extractExtension(path) {
    if (!path) { return ''; }
    var parts = path.split('.');
    return parts.length > 1 ? parts.pop().toLowerCase() : '';
}
```

### Design Rationale for Dispatch Order

1. **Markdown first** - preserves feature 76 behavior as the primary path
2. **JSON second** - most common artifact type; needs pretty-printing before highlighting
3. **Log third** - needs custom renderer (not highlight.js)
4. **Code fourth** - all other highlight.js-supported extensions
5. **Plain text last** - fallback for unrecognized extensions

This order matters because JSON is dispatched separately from the generic highlight.js
path: it needs JSON.parse + JSON.stringify pretty-printing before highlighting.

## 3. Renderer Implementations

### 3.1 showFormatted / showPlain Helpers

Common show/hide pattern extracted to avoid repetition:

```javascript
/** Show formatted content in mdDiv, hide raw pre. */
function showFormatted(pre, mdDiv) {
    pre.hidden = true;
    mdDiv.hidden = false;
}

/** Show raw pre, hide mdDiv. */
function showPlain(pre, mdDiv) {
    pre.hidden = false;
    if (mdDiv) { mdDiv.hidden = true; }
}
```

### 3.2 Markdown Renderer (Existing - Preserved)

```javascript
function renderMarkdown(pre, mdDiv, text) {
    showFormatted(pre, mdDiv);
    mdDiv.innerHTML = marked.parse(text);
}
```

This is the existing feature 76 behavior, unchanged.

### 3.3 JSON Renderer (Pretty-Print + Highlight)

```javascript
var JSON_INDENT_SPACES = 2;

function renderJson(pre, mdDiv, text) {
    var formatted;
    try {
        var parsed = JSON.parse(text);
        formatted = JSON.stringify(parsed, null, JSON_INDENT_SPACES);
    } catch (e) {
        /* Malformed JSON: fall back to plain text display */
        renderPlainText(pre, mdDiv, text);
        return;
    }
    renderHighlighted(pre, mdDiv, formatted, 'json');
}
```

**Key decisions:**
- Pretty-prints with 2-space indent before highlighting (AC1, AC12)
- try/catch for malformed JSON falls back to plain text (AC15)
- Reuses renderHighlighted for syntax coloring (AC13, AC14)

### 3.4 Generic Highlighted Renderer (YAML, Python, TypeScript, HTML, CSS)

```javascript
/**
 * Render text with highlight.js syntax coloring.
 * Produces: mdDiv > pre > code.hljs with colored span children.
 *
 * @param {HTMLPreElement} pre - Raw content pre
 * @param {HTMLDivElement} mdDiv - .md-rendered container
 * @param {string} text - Content to highlight
 * @param {string} language - highlight.js language identifier
 */
function renderHighlighted(pre, mdDiv, text, language) {
    if (typeof hljs === 'undefined') {
        renderPlainText(pre, mdDiv, text);
        return;
    }
    var result = hljs.highlight(text, { language: language });
    var codeEl = document.createElement('code');
    codeEl.className = 'hljs';
    codeEl.innerHTML = result.value;
    var preEl = document.createElement('pre');
    preEl.appendChild(codeEl);
    mdDiv.innerHTML = '';
    mdDiv.appendChild(preEl);
    showFormatted(pre, mdDiv);
}
```

**DOM structure produced:**
```
div.md-rendered
  pre
    code.hljs
      span.hljs-attr "key"
      span.hljs-string "value"
      span.hljs-number 42
      span.hljs-literal true/false/null
      span.hljs-comment "# comment"
```

This structure is directly testable by Playwright:
- `.md-rendered pre code.hljs` confirms highlighting was applied
- `.md-rendered .hljs-attr` confirms key coloring (JSON/YAML)
- `.md-rendered .hljs-string` confirms string coloring
- `.md-rendered .hljs-keyword` confirms keyword coloring (Python/TS)

### 3.5 Log File Renderer

```javascript
var LOG_HEADER_PATTERN = /^={2,}\s.*={2,}$/;
var LOG_JSON_START_PATTERN = /\{/;

/**
 * Render log file with header detection and embedded JSON extraction.
 * Headers get bold styling; embedded JSON objects get pretty-printed.
 */
function renderLog(pre, mdDiv, text) {
    var lines = text.split('\n');
    var preEl = document.createElement('pre');
    preEl.className = 'log-content';

    var i = 0;
    while (i < lines.length) {
        var line = lines[i];

        if (LOG_HEADER_PATTERN.test(line)) {
            /* Section header: == Title == or === Title === */
            var headerSpan = document.createElement('span');
            headerSpan.className = 'log-header';
            headerSpan.textContent = line;
            preEl.appendChild(headerSpan);
            preEl.appendChild(document.createTextNode('\n'));
            i++;
            continue;
        }

        /* Check for embedded JSON object starting on this line */
        var jsonResult = tryExtractJson(lines, i);
        if (jsonResult) {
            var jsonPre = document.createElement('span');
            jsonPre.className = 'log-embedded-json';
            try {
                var parsed = JSON.parse(jsonResult.text);
                jsonPre.textContent = JSON.stringify(parsed, null, JSON_INDENT_SPACES);
            } catch (e) {
                jsonPre.textContent = jsonResult.text;
            }
            preEl.appendChild(jsonPre);
            preEl.appendChild(document.createTextNode('\n'));
            i = jsonResult.endLine + 1;
            continue;
        }

        /* Plain log line */
        preEl.appendChild(document.createTextNode(line));
        if (i < lines.length - 1) {
            preEl.appendChild(document.createTextNode('\n'));
        }
        i++;
    }

    mdDiv.innerHTML = '';
    mdDiv.appendChild(preEl);
    showFormatted(pre, mdDiv);
}

/**
 * Attempt to extract a JSON object starting at lineIndex.
 * Looks for lines starting with { and accumulates until matching } is found.
 * Returns { text, endLine } on success, null on failure.
 */
function tryExtractJson(lines, lineIndex) {
    var line = lines[lineIndex];
    var bracePos = line.indexOf('{');
    if (bracePos === -1) { return null; }

    /* Accumulate lines until braces balance */
    var depth = 0;
    var jsonLines = [];
    for (var j = lineIndex; j < lines.length; j++) {
        var current = j === lineIndex ? line.substring(bracePos) : lines[j];
        jsonLines.push(current);
        for (var k = 0; k < current.length; k++) {
            if (current[k] === '{') { depth++; }
            else if (current[k] === '}') { depth--; }
            if (depth === 0) {
                var candidate = jsonLines.join('\n');
                try {
                    JSON.parse(candidate);
                    return { text: candidate, endLine: j };
                } catch (e) {
                    return null;
                }
            }
        }
    }
    return null;
}
```

**Header detection regex:** `/^={2,}\s.*={2,}$/`
- Matches lines like `== Section Header ==` or `=== Title ===`
- Requires at least 2 equals signs on each side with content in between

**Embedded JSON extraction:**
- Scans for `{` character, then accumulates lines tracking brace depth
- Validates with JSON.parse before treating as JSON
- Falls back to plain text if parsing fails

### 3.6 Plain Text Renderer (Fallback)

```javascript
function renderPlainText(pre, mdDiv, text) {
    pre.textContent = text;
    showPlain(pre, mdDiv);
}
```

## 4. CSS Additions

Add these styles inside the existing style block, after the .md-rendered rules
(before the closing style tag):

### 4.1 highlight.js Theme Overrides

```css
/* ── highlight.js dark theme overrides (match .md-rendered background) ── */
.md-rendered pre {
    background: #0f0f1e;
    margin: 0;
    padding: 0.5rem 0.75rem;
    border-radius: 4px;
}

.md-rendered pre code.hljs {
    background: transparent;
    padding: 0;
    font-family: ui-monospace, SFMono-Regular, "SF Mono", Consolas, monospace;
    font-size: 11px;
    line-height: 1.5;
    color: #e2e8f0;
}
```

The github-dark theme from highlight.js sets its own background (#0d1117), but these
overrides ensure consistency with the existing .md-rendered pre rules from feature 76.
The .md-rendered pre rule already exists (line 1085-1094); the code.hljs rule adds
specificity for highlighted code blocks.

### 4.2 Log Renderer Styles

```css
/* ── Log file rendering ────────────────────────────────────────────── */
.md-rendered .log-content {
    background: #0f0f1e;
    margin: 0;
    padding: 0.5rem 0.75rem;
    border-radius: 4px;
    font-family: ui-monospace, SFMono-Regular, "SF Mono", Consolas, monospace;
    font-size: 11px;
    line-height: 1.5;
    color: #e2e8f0;
    white-space: pre-wrap;
    word-break: break-word;
}

.md-rendered .log-header {
    display: block;
    font-weight: 700;
    color: #7ba8e8;
    background: rgba(123, 168, 232, 0.08);
    padding: 2px 6px;
    margin: 0.5em -6px;
    border-radius: 3px;
}

.md-rendered .log-header:first-child {
    margin-top: 0;
}

.md-rendered .log-embedded-json {
    display: block;
    color: #a0d0a0;
    padding-left: 1em;
    border-left: 2px solid rgba(160, 208, 160, 0.3);
}
```

**Visual design choices:**
- Log headers: bold, blue (#7ba8e8 matches existing link color), subtle background
- Embedded JSON: green tint (#a0d0a0), left border indent to distinguish from surrounding log text
- Both use display:block to ensure they occupy their own line

## 5. DOM Structure Summary (for Playwright Verification)

### JSON Files (.json)
```
pre.artifact-viewer-pre[hidden]
div.md-rendered:not([hidden])
  pre
    code.hljs
      span.hljs-attr       (key names - distinct color)
      span.hljs-string     (string values - distinct color)
      span.hljs-number     (numbers - distinct color)
      span.hljs-literal    (true/false/null - distinct color)
      span.hljs-punctuation
```

**Playwright assertions:**
```javascript
await expect(page.locator('.md-rendered pre code.hljs')).toBeVisible();
await expect(page.locator('.md-rendered .hljs-attr')).toHaveCount({ minimum: 1 });
await expect(page.locator('.artifact-viewer-pre')).toHaveAttribute('hidden', '');
```

### YAML Files (.yaml, .yml)
```
pre.artifact-viewer-pre[hidden]
div.md-rendered:not([hidden])
  pre
    code.hljs
      span.hljs-attr       (keys)
      span.hljs-string     (string values)
      span.hljs-number     (numbers)
      span.hljs-literal    (booleans)
      span.hljs-comment    (# comments)
```

### Code Files (.py, .ts, .html, .css)
```
pre.artifact-viewer-pre[hidden]
div.md-rendered:not([hidden])
  pre
    code.hljs
      span.hljs-keyword    (language keywords)
      span.hljs-string     (string literals)
      span.hljs-comment    (comments)
      span.hljs-function   (function names)
      span.hljs-number     (numeric literals)
```

### Log Files (.log)
```
pre.artifact-viewer-pre[hidden]
div.md-rendered:not([hidden])
  pre.log-content
    span.log-header        (section headers)
    #text                  (plain log lines)
    span.log-embedded-json (pretty-printed JSON blocks)
```

**Playwright assertions:**
```javascript
await expect(page.locator('.md-rendered .log-header')).toHaveCount({ minimum: 1 });
await expect(page.locator('.md-rendered .log-embedded-json')).toBeVisible();
```

### Markdown Files (.md) - Unchanged
```
pre.artifact-viewer-pre[hidden]
div.md-rendered:not([hidden])
  (markdown HTML rendered by marked.js - unchanged from feature 76)
```

### Plain Text (unrecognized extensions)
```
pre.artifact-viewer-pre:not([hidden])
div.md-rendered[hidden]
```

## 6. Acceptance Criteria Traceability

| AC | Covered By | How |
|---|---|---|
| AC1 | Section 3.3 | JSON.parse + JSON.stringify(_, null, 2) pretty-prints JSON |
| AC2 | Section 3.4 | hljs.highlight with language:'yaml' colors keys vs values |
| AC3 | Section 3.5 | LOG_HEADER_PATTERN regex detects == headers ==, bold+color styling |
| AC4 | Section 3.4 | HLJS_LANGUAGE_MAP routes .py/.ts/.html/.css to highlight.js |
| AC5 | Section 2 | Extension dispatch replaces single .md check |
| AC6 | Section 2 | extractExtension() uses path.split('.').pop().toLowerCase() |
| AC7 | Section 2 | Dispatch function routes to markdown/json/log/highlighted/plain |
| AC8 | Section 3.6 | renderPlainText fallback for unrecognized extensions |
| AC9 | Section 3.1 | showFormatted helper uses mdDiv for all formatted content |
| AC10 | Section 3.1 | showFormatted sets pre.hidden=true, mdDiv.hidden=false |
| AC11 | Section 3.6 | showPlain sets pre.hidden=false, mdDiv.hidden=true |
| AC12 | Section 3.3 | JSON uses mdDiv via renderHighlighted -> showFormatted |
| AC13 | Section 3.4 | hljs.highlight produces pre > code.hljs with colored spans |
| AC14 | Sections 3.4, 4.1 | github-dark theme + overrides give distinct token colors |
| AC15 | Section 3.3 | try/catch around JSON.parse; catch falls back to plain text |
| AC16 | Section 5 | Pretty-printed JSON has newlines; hljs produces span children |
| AC17 | Section 3.4 | YAML uses mdDiv via renderHighlighted -> showFormatted |
| AC18 | Section 4.1 | github-dark theme colors .hljs-attr vs .hljs-string distinctly |
| AC19 | Section 3.4 | hljs YAML module highlights comments as .hljs-comment |
| AC20 | Section 3.4 | hljs highlights .hljs-string and .hljs-literal for YAML |
| AC21 | Section 3.5 | tryExtractJson extracts and pretty-prints embedded JSON |
| AC22 | Section 4.1 | Theme overrides harmonize hljs with .md-rendered background |
| AC23 | Section 1 | highlight.js loaded via CDN, same pattern as marked.js |
| AC24 | Section 5 | DOM structures documented with Playwright-queryable selectors |
| AC25 | Section 3.1 | showFormatted sets pre[hidden] for all formatted types |
| AC26 | Section 5 | .md-rendered visible with .hljs-* class child spans |
| AC27 | Section 5 | Span classes carry distinct computed colors per token type |
| AC28 | Entire doc | All changes in item.html only (CDN tags, CSS, JS) |
| AC29 | Section 2 | Extends renderArtifactContent and .md-rendered pattern |

## 7. Implementation Sequence

Recommended order for implementation tasks (for the planner agent):

1. **CDN additions** - Add highlight.js core, language modules, and github-dark CSS
   after the marked.js script tag. No behavior change yet.

2. **Dispatch refactor** - Replace renderArtifactContent body with extension dispatch.
   Add HLJS_LANGUAGE_MAP, extractExtension, showFormatted, showPlain helpers.
   Add renderMarkdown (same as current .md path) and renderPlainText (same as
   current else path). Behavior should be identical at this point.

3. **JSON renderer** - Add renderJson with pretty-print + highlight. Add
   renderHighlighted as the shared highlighting function.

4. **YAML + Code renderers** - These are handled by renderHighlighted already.
   Just verify the dispatch routes .yaml/.yml/.py/.ts/.html/.css correctly.

5. **Log renderer** - Add renderLog, LOG_HEADER_PATTERN, tryExtractJson.
   Add log-specific CSS (log-content, log-header, log-embedded-json).

6. **CSS overrides** - Add highlight.js theme overrides for .md-rendered context.

7. **E2E tests** - Playwright tests verifying DOM structure for each content type.

## 8. Risk Mitigation

### highlight.js CDN Availability
If the CDN is unreachable, the typeof hljs === 'undefined' guard in renderHighlighted
falls back to plain text. No functionality is lost -- just syntax coloring.

### Malformed JSON
JSON.parse failure in renderJson triggers renderPlainText fallback. The user sees
the raw content rather than an error.

### Large Files
The existing max-height: 400px with overflow-y: auto on .md-rendered handles large
files with scrolling. No additional size guards needed.

### highlight.js Version Pinning
Using version 11.9.0 pinned via CDN URL (not @latest). This prevents breaking
changes from affecting production.

### CSS Specificity
The .md-rendered pre code.hljs selector has higher specificity than the github-dark
theme's generic .hljs selector, ensuring our background/font overrides win.
