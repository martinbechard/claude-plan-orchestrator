# Systems Design: 87 Item Page Content-Type-Aware Rendering

Source: tmp/plans/.claimed/87-item-page-content-type-aware-rendering.md
Requirements: docs/plans/2026-04-02-87-item-page-content-type-aware-rendering-requirements.md
Design overview: docs/plans/2026-04-02-87-item-page-content-type-aware-rendering-design.md

This document is a Phase 0 design competition entry (systems-designer agent).

---

## 1. Architectural Constraints

All changes are confined to a single file: langgraph_pipeline/web/templates/item.html.

The file is a Jinja2 template that includes inline CSS (in extra_head block) and inline
JavaScript (in a script tag at the bottom). There is no build system, bundler, or module
loader -- all dependencies are loaded via CDN script tags. The existing pattern from
feature 76 is:

```
<script src="https://cdn.jsdelivr.net/npm/marked@9.1.6/marked.min.js"
        integrity="sha384-..." crossorigin="anonymous"></script>
```

The backend (item.py) serves artifact content as PlainTextResponse via an AJAX endpoint.
All formatting is client-side JavaScript that runs after the fetch completes. The DOM
structure pairs a raw pre element with a .md-rendered div for each artifact viewer slot.

---

## 2. Extension Dispatch Architecture

### 2.1 Current State (feature 76)

```
renderArtifactContent(pre, mdDiv, text, path)
  if path ends with .md AND marked is available:
    hide pre, show mdDiv, mdDiv.innerHTML = marked.parse(text)
  else:
    pre.textContent = text, show pre, hide mdDiv
```

### 2.2 Proposed Dispatch

Replace the single .md check with extension extraction and a dispatch map.

```javascript
/* Manifest constants for extension groups */
var EXT_MARKDOWN = ['md'];
var EXT_JSON     = ['json'];
var EXT_YAML     = ['yaml', 'yml'];
var EXT_LOG      = ['log'];
var EXT_CODE     = {
    py:   'python',
    ts:   'typescript',
    js:   'javascript',
    html: 'xml',
    css:  'css',
    xml:  'xml',
    sh:   'bash',
    bash: 'bash'
};
```

The dispatch logic:

```
renderArtifactContent(pre, mdDiv, text, path):
  ext = extractExtension(path)   // path.split('.').pop().toLowerCase()

  if ext in EXT_MARKDOWN:
    renderMarkdown(pre, mdDiv, text)
  else if ext in EXT_JSON:
    renderJson(pre, mdDiv, text)
  else if ext in EXT_YAML:
    renderHighlighted(pre, mdDiv, text, 'yaml')
  else if ext in EXT_CODE:
    renderHighlighted(pre, mdDiv, text, EXT_CODE[ext])
  else if ext in EXT_LOG:
    renderLog(pre, mdDiv, text)
  else:
    renderPlainText(pre, mdDiv, text)
```

Each render function follows the same contract:
- Formatted output: set pre.hidden = true, mdDiv.hidden = false, populate mdDiv
- Plain fallback: set pre.textContent = text, pre.hidden = false, mdDiv.hidden = true

This satisfies AC5 (dispatch exists), AC6 (extension extraction), AC7 (distinct paths),
AC8 (fallback for unrecognized), AC9 (single styled container), AC10/AC11 (show/hide).

### 2.3 Extension Extraction

```javascript
function extractExtension(path) {
    if (!path) return '';
    var parts = path.split('.');
    return parts.length > 1 ? parts.pop().toLowerCase() : '';
}
```

Files without extensions (e.g., Makefile, Dockerfile) return empty string and hit the
plain text fallback. This is correct behavior -- no false positive formatting.

### 2.4 Why a Dispatch Map Instead of a Switch

The coding rules (section 8) recommend avoiding large switch statements in favor of
lookup maps. The EXT_CODE object serves as a map from file extension to highlight.js
language name. The dispatch itself uses if/else-if because there are only 5 branches
(markdown, JSON, YAML, code, log) plus the default -- well within the acceptable range
for readability.

---

## 3. CDN Library Selection: highlight.js

### 3.1 Comparison: highlight.js vs Prism.js

| Criterion | highlight.js | Prism.js |
|---|---|---|
| API model | hljs.highlight(text, {language}) returns {value} with HTML | Prism.highlight(text, grammar, lang) returns HTML |
| CDN availability | jsdelivr, cdnjs, unpkg -- all with SRI | Same |
| Language bundles | Individual language files loadable separately | Plugin architecture, separate language files |
| Auto-detection | Built-in auto-detect (not needed here) | Manual |
| Dark themes | 10+ built-in dark themes via CDN CSS | Themes available via CDN CSS |
| Bundle size (core) | ~47 KB minified (core only) | ~6 KB minified (core only) |
| Bundle size (per language) | 1-8 KB each | 1-5 KB each |
| API simplicity | Simple: hljs.highlight(text, {language}).value | Requires Prism.languages loaded |
| DOM injection model | Returns HTML string for innerHTML | Returns HTML string for innerHTML |
| Community adoption | 23M+ weekly npm downloads | 14M+ weekly npm downloads |

### 3.2 Decision: highlight.js

Rationale:
1. The API is simpler for our use case. We know the language from the file extension and
   do not need auto-detection, but hljs.highlight(text, {language}) is a one-liner that
   returns ready-to-use HTML.
2. Built-in dark themes (github-dark, atom-one-dark) are available as single CSS files
   from the same CDN. No theme customization plugin needed.
3. highlight.js produces output with .hljs-* CSS classes on span elements. These classes
   are stable, well-documented, and ideal for Playwright assertions (AC24-AC27).
4. The marked.js CDN pattern is already established. highlight.js follows the same
   pattern: a core script, language scripts, and a theme CSS.

### 3.3 CDN URLs and Bundle Strategy

highlight.js version: 11.9.0 (latest stable as of 2026-04).

Core + languages needed:

```
<!-- highlight.js core -->
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"
        integrity="..." crossorigin="anonymous"></script>

<!-- Language modules (loaded after core) -->
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/json.min.js"
        integrity="..." crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/yaml.min.js"
        integrity="..." crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/python.min.js"
        integrity="..." crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/typescript.min.js"
        integrity="..." crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/css.min.js"
        integrity="..." crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/xml.min.js"
        integrity="..." crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/bash.min.js"
        integrity="..." crossorigin="anonymous"></script>

<!-- Dark theme CSS -->
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css"
      integrity="..." crossorigin="anonymous">
```

### 3.4 Bundle Size Analysis

| Component | Size (minified, gzipped) |
|---|---|
| highlight.js core | ~18 KB gzip |
| json.min.js | ~1 KB gzip |
| yaml.min.js | ~1 KB gzip |
| python.min.js | ~3 KB gzip |
| typescript.min.js | ~3 KB gzip |
| css.min.js | ~1 KB gzip |
| xml.min.js | ~2 KB gzip |
| bash.min.js | ~1 KB gzip |
| github-dark.min.css | ~2 KB gzip |
| **Total additional** | **~32 KB gzip** |

For comparison, the existing marked.min.js is ~14 KB gzip. The total highlight.js
footprint is roughly 2.3x the existing marked.js cost. This is acceptable for an
internal tool page where initial load is not the bottleneck (the AJAX content fetches
dominate perceived latency).

### 3.5 Loading Strategy

All CDN scripts load synchronously in the extra_head block, matching the marked.js
pattern. Rationale:

1. highlight.js is needed the moment any artifact content loads (which can happen
   automatically for in_progress stages that auto-expand).
2. The scripts are small and cached by the CDN (jsdelivr serves with long Cache-Control).
3. Lazy loading would add complexity (dynamic script injection, load callbacks, race
   conditions) for minimal benefit on an internal tool page.
4. The typeof hljs !== 'undefined' guard (matching the existing typeof marked guard)
   provides graceful degradation if CDN fails -- content falls back to plain text.

Disable highlight.js auto-highlighting to prevent it from scanning the page on load:

```html
<script>
    if (typeof hljs !== 'undefined') { hljs.configure({ignoreUnescapedHTML: true}); }
</script>
```

We call hljs.highlight() manually with explicit language names. No auto-detection needed.

---

## 4. Renderer Implementations

### 4.1 renderMarkdown (existing, unchanged)

```javascript
function renderMarkdown(pre, mdDiv, text) {
    if (typeof marked === 'undefined') {
        renderPlainText(pre, mdDiv, text);
        return;
    }
    pre.hidden = true;
    mdDiv.hidden = false;
    mdDiv.innerHTML = marked.parse(text);
}
```

Feature-76 behavior preserved exactly. (AC29)

### 4.2 renderJson

```javascript
function renderJson(pre, mdDiv, text) {
    var formatted;
    try {
        var parsed = JSON.parse(text);
        formatted = JSON.stringify(parsed, null, JSON_INDENT_SPACES);
    } catch (e) {
        /* Malformed JSON: fall back to plain text display (AC15) */
        renderPlainText(pre, mdDiv, text);
        return;
    }
    renderHighlighted(pre, mdDiv, formatted, 'json');
}
```

Where JSON_INDENT_SPACES = 2 is a manifest constant.

Flow: parse -> stringify with indent -> highlight. If parse fails, plain text. (AC1,
AC12, AC13, AC14, AC15, AC16)

### 4.3 renderHighlighted (shared for JSON, YAML, code)

```javascript
function renderHighlighted(pre, mdDiv, text, language) {
    if (typeof hljs === 'undefined') {
        renderPlainText(pre, mdDiv, text);
        return;
    }
    var result = hljs.highlight(text, { language: language });
    pre.hidden = true;
    mdDiv.hidden = false;
    mdDiv.innerHTML = '';
    var codeBlock = document.createElement('pre');
    var codeEl = document.createElement('code');
    codeEl.className = 'hljs language-' + language;
    codeEl.innerHTML = result.value;
    codeBlock.appendChild(codeEl);
    mdDiv.appendChild(codeBlock);
}
```

DOM structure produced:

```html
<div class="md-rendered">
  <pre>
    <code class="hljs language-json">
      <span class="hljs-attr">"key"</span>:
      <span class="hljs-string">"value"</span>
    </code>
  </pre>
</div>
```

This satisfies AC13 (pre > code structure with colored spans). The .hljs-* classes are
styled by the github-dark theme CSS to produce distinct colors for each token type
(AC14, AC18, AC19, AC20, AC22).

### 4.4 renderLog

```javascript
var LOG_HEADER_PATTERN = /^(={2,})\s+(.+?)\s+\1\s*$/;

function renderLog(pre, mdDiv, text) {
    var lines = text.split('\n');
    pre.hidden = true;
    mdDiv.hidden = false;
    mdDiv.innerHTML = '';

    var logPre = document.createElement('pre');
    logPre.className = 'log-content';

    for (var i = 0; i < lines.length; i++) {
        var line = lines[i];

        /* Check for section header (AC3) */
        if (LOG_HEADER_PATTERN.test(line)) {
            var headerSpan = document.createElement('span');
            headerSpan.className = 'log-header';
            headerSpan.textContent = line;
            logPre.appendChild(headerSpan);
            logPre.appendChild(document.createTextNode('\n'));
            continue;
        }

        /* Check for embedded JSON (AC21) */
        var jsonStart = line.indexOf('{');
        if (jsonStart !== -1) {
            var jsonCandidate = line.substring(jsonStart);
            try {
                var parsed = JSON.parse(jsonCandidate);
                /* Prefix before JSON */
                if (jsonStart > 0) {
                    logPre.appendChild(
                        document.createTextNode(line.substring(0, jsonStart))
                    );
                }
                /* Pretty-printed embedded JSON */
                var jsonSpan = document.createElement('span');
                jsonSpan.className = 'log-embedded-json';
                jsonSpan.textContent = JSON.stringify(parsed, null, JSON_INDENT_SPACES);
                logPre.appendChild(jsonSpan);
                logPre.appendChild(document.createTextNode('\n'));
                continue;
            } catch (e) {
                /* Not valid JSON, render as plain line */
            }
        }

        /* Plain log line */
        logPre.appendChild(document.createTextNode(line + '\n'));
    }

    mdDiv.appendChild(logPre);
}
```

DOM structure produced:

```html
<div class="md-rendered">
  <pre class="log-content">
    <span class="log-header">=== STDOUT ===</span>
    plain text line
    <span class="log-embedded-json">{
  "key": "value"
}</span>
    more plain text
  </pre>
</div>
```

The log-header and log-embedded-json classes are Playwright-queryable (AC24, AC27).

### 4.5 renderPlainText

```javascript
function renderPlainText(pre, mdDiv, text) {
    pre.textContent = text;
    pre.hidden = false;
    if (mdDiv) { mdDiv.hidden = true; }
}
```

Unchanged from current behavior. Used as fallback for unrecognized extensions and
malformed JSON. (AC8, AC11, AC15)

---

## 5. CSS Additions

### 5.1 highlight.js Theme Override

The github-dark theme CSS provides all .hljs-* token colors. We need minor overrides
to match the existing .md-rendered container:

```css
/* Ensure highlight.js code blocks inherit the .md-rendered dark theme */
.md-rendered pre {
    background: #0f0f1e;  /* matches existing .md-rendered pre */
    border-radius: 4px;
    padding: 0.5rem 0.75rem;
    overflow-x: auto;
    margin: 0;
}

.md-rendered code.hljs {
    background: transparent;  /* let the pre background show through */
    padding: 0;
    font-family: ui-monospace, SFMono-Regular, "SF Mono", Consolas, monospace;
    font-size: 12px;
    line-height: 1.5;
    color: #e2e8f0;
}
```

The existing .md-rendered pre and .md-rendered pre code rules from feature 76 already
handle most of this. We only need to ensure .hljs class does not override the background.

### 5.2 Log-Specific CSS

```css
/* Log file section headers (AC3) */
.log-header {
    display: block;
    font-weight: 700;
    color: #7ba8e8;         /* blue accent matching existing link color */
    background: rgba(123, 168, 232, 0.08);
    padding: 2px 6px;
    margin: 0.25em 0;
    border-radius: 3px;
}

/* Log embedded JSON (AC21) */
.log-embedded-json {
    color: #a8d8a8;         /* soft green for embedded data */
    display: inline;
}

/* Log content container */
.log-content {
    background: #0f0f1e;
    color: #e2e8f0;
    font-family: ui-monospace, SFMono-Regular, "SF Mono", Consolas, monospace;
    font-size: 12px;
    line-height: 1.5;
    padding: 0.5rem 0.75rem;
    margin: 0;
    overflow-x: auto;
    white-space: pre-wrap;
    word-wrap: break-word;
}
```

---

## 6. Fallback Behavior for Malformed Content

| Scenario | Behavior | AC |
|---|---|---|
| JSON with syntax errors | JSON.parse throws; renderPlainText shows raw text | AC15 |
| YAML (any content) | highlight.js YAML grammar is lenient; renders with best-effort | -- |
| highlight.js CDN fails to load | typeof hljs === 'undefined'; all code/JSON/YAML fall back to plain text | AC8 |
| marked.js CDN fails to load | typeof marked === 'undefined'; markdown falls back to plain text | AC8 |
| File with no extension | extractExtension returns ''; dispatch hits plain text fallback | AC8 |
| Unknown extension (.xyz) | Not in any extension set; dispatch hits plain text fallback | AC8 |
| Empty content | Empty string passes through; pre or div shows empty (correct) | -- |
| Very large content (>1MB) | highlight.js handles synchronously; may cause brief UI freeze | -- |

The guard pattern typeof hljs !== 'undefined' ensures that a CDN failure (network
error, blocked CDN) results in graceful degradation to plain text, not a JavaScript
error. This matches the existing typeof marked !== 'undefined' pattern.

---

## 7. DOM Structure for Playwright Verification

### 7.1 Artifact Viewer DOM (per artifact)

```html
<!-- Existing DOM from feature 76 (unchanged) -->
<div class="artifact-viewer" hidden aria-live="polite">
  <pre class="artifact-viewer-pre" aria-label="Content of filename.ext">
    Loading...
  </pre>
  <div class="md-rendered" hidden></div>
</div>
```

### 7.2 After Rendering: JSON Example

```html
<div class="artifact-viewer" aria-live="polite">
  <pre class="artifact-viewer-pre" hidden>Loading...</pre>
  <div class="md-rendered">
    <pre>
      <code class="hljs language-json">
        <span class="hljs-punctuation">{</span>
        <span class="hljs-attr">"status"</span>
        <span class="hljs-punctuation">:</span>
        <span class="hljs-string">"pass"</span>
        <span class="hljs-punctuation">}</span>
      </code>
    </pre>
  </div>
</div>
```

### 7.3 Playwright Assertion Strategy

For each content type, the E2E test follows this pattern:

```
1. Navigate to /item/{slug}
2. Click the artifact expand button (or wait for auto-expand)
3. Wait for pre.artifact-viewer-pre to NOT contain "Loading"
4. Assert: pre.artifact-viewer-pre has hidden attribute
5. Assert: div.md-rendered does NOT have hidden attribute
6. Type-specific assertions:
```

**JSON assertions (AC13, AC16):**
```
- div.md-rendered > pre > code.hljs.language-json exists
- code.hljs contains at least one span.hljs-attr (keys have color)
- code.hljs contains at least one span.hljs-string (strings have color)
- code.hljs.textContent includes '\n' (pretty-printed)
```

**YAML assertions (AC17, AC18, AC19, AC20):**
```
- div.md-rendered > pre > code.hljs.language-yaml exists
- code.hljs contains at least one span.hljs-attr (keys)
- code.hljs contains at least one span.hljs-string (values)
```

**Log assertions (AC3, AC21):**
```
- div.md-rendered > pre.log-content exists
- pre.log-content contains at least one span.log-header
- If test data includes embedded JSON: span.log-embedded-json exists
  and contains newlines (pretty-printed)
```

**Code assertions (AC4, AC22):**
```
- div.md-rendered > pre > code.hljs exists
- code.hljs contains span.hljs-keyword (language keywords)
- code.hljs contains span.hljs-string (string literals)
```

**Plain text assertions (AC11):**
```
- pre.artifact-viewer-pre does NOT have hidden attribute
- div.md-rendered has hidden attribute
```

### 7.4 CSS Selector Summary for Tests

| Selector | Meaning | Used in ACs |
|---|---|---|
| pre.artifact-viewer-pre[hidden] | Raw pre is hidden (formatted content active) | AC10, AC25 |
| pre.artifact-viewer-pre:not([hidden]) | Raw pre is visible (plain text fallback) | AC11 |
| .md-rendered:not([hidden]) | Styled container is visible | AC12, AC17, AC26 |
| .md-rendered[hidden] | Styled container is hidden (plain text) | AC11 |
| .md-rendered pre > code.hljs | Highlighted code block exists | AC13 |
| .md-rendered code.hljs span.hljs-attr | JSON/YAML key token | AC14, AC18 |
| .md-rendered code.hljs span.hljs-string | String value token | AC14, AC18, AC20 |
| .md-rendered code.hljs span.hljs-number | Numeric value token | AC14 |
| .md-rendered code.hljs span.hljs-literal | Boolean/null token | AC14, AC20 |
| .md-rendered code.hljs span.hljs-comment | Comment token | AC19 |
| .md-rendered code.hljs span.hljs-keyword | Language keyword | AC4 |
| .md-rendered pre.log-content | Log content container | AC3 |
| .md-rendered span.log-header | Log section header | AC3 |
| .md-rendered span.log-embedded-json | Embedded JSON in log | AC21 |

---

## 8. Step Explorer Integration

The step explorer (loadStageArtifacts function at line ~1681) already calls
renderArtifactContent for each pre.step-artifact-content element. The same dispatch
logic applies automatically -- no changes needed to the step explorer code.

The DOM structure in the step explorer differs slightly:

```html
<pre class="step-artifact-content" data-artifact-path="path/to/file.json" hidden>
  Loading...
</pre>
<div class="md-rendered" hidden></div>
```

The pre has class step-artifact-content instead of artifact-viewer-pre, but the
renderArtifactContent function takes pre and mdDiv as parameters regardless of class
names. Both call sites pass the correct elements. No changes needed.

---

## 9. Security Considerations

### 9.1 XSS via highlight.js Output

highlight.js escapes HTML entities in the input text before wrapping tokens in span
elements. The output of hljs.highlight() is safe to assign to innerHTML. This is a
documented guarantee of the library.

However, the renderLog function builds DOM using document.createTextNode and
document.createElement, which are inherently XSS-safe (textContent assignment escapes
HTML). The only innerHTML usage in the log renderer would be for the embedded JSON
highlight path -- but this design uses textContent for embedded JSON display, avoiding
any XSS surface.

### 9.2 Content-Type Sniffing

The extension is extracted from the file path provided by the server. There is no user
input in the extension extraction. A malicious artifact path could only come from the
filesystem (which requires server-side write access). This is not a meaningful attack
vector for an internal tool.

---

## 10. Implementation Order

The recommended implementation sequence:

1. **CDN additions** (5 min): Add highlight.js core, language modules, and dark theme
   CSS to the extra_head block, after the existing marked.js script tag. Add the
   hljs.configure call.

2. **CSS additions** (5 min): Add .hljs override styles, log-header, log-embedded-json,
   and log-content classes to the existing style block.

3. **Refactor renderArtifactContent** (15 min): Extract renderMarkdown, renderPlainText,
   renderHighlighted, renderJson, renderLog functions. Replace the existing function body
   with the dispatch logic.

4. **Test manually** (10 min): Load an item page with JSON, YAML, log, and code
   artifacts. Verify each renders correctly.

5. **Write Playwright tests** (20 min): One test per content type following the
   assertion strategy in section 7.3.

---

## Design -> AC Traceability Grid

| AC | Design Section | How Satisfied |
|---|---|---|
| AC1 | 4.2 | JSON.parse + JSON.stringify(_, null, 2) produces indented output |
| AC2 | 4.3 | highlight.js YAML module colors .hljs-attr vs .hljs-string distinctly |
| AC3 | 4.4 | LOG_HEADER_PATTERN regex detects headers; .log-header CSS styles them |
| AC4 | 4.3 | highlight.js language modules produce .hljs-keyword/.hljs-string/.hljs-comment |
| AC5 | 2.2 | Extension dispatch replaces single .md check |
| AC6 | 2.3 | extractExtension() splits on '.' and lowercases |
| AC7 | 2.2 | Dispatch map routes to 5 distinct renderer functions |
| AC8 | 2.2, 4.5 | Default branch and CDN-fail guards use renderPlainText |
| AC9 | 4.1-4.4 | All formatters output to the .md-rendered div |
| AC10 | 4.1-4.4 | All formatters set pre.hidden=true, mdDiv.hidden=false |
| AC11 | 4.5 | renderPlainText sets pre.hidden=false, mdDiv.hidden=true |
| AC12 | 4.2 | JSON renderer uses .md-rendered div |
| AC13 | 4.3 | renderHighlighted creates pre > code.hljs with span children |
| AC14 | 3.2, 5.1 | github-dark theme assigns distinct colors per .hljs-* class |
| AC15 | 4.2 | try/catch around JSON.parse; catch calls renderPlainText |
| AC16 | 4.2, 4.3 | Pretty-printed JSON has newlines; hljs produces styled spans |
| AC17 | 4.3 | YAML uses renderHighlighted which populates .md-rendered div |
| AC18 | 3.2, 5.1 | highlight.js YAML theme colors .hljs-attr vs .hljs-string |
| AC19 | 3.2 | highlight.js YAML recognizes comments as .hljs-comment |
| AC20 | 3.2 | highlight.js YAML highlights .hljs-string and .hljs-literal |
| AC21 | 4.4 | renderLog detects { in lines, attempts JSON.parse, pretty-prints |
| AC22 | 5.1 | github-dark.min.css harmonizes with .md-rendered background |
| AC23 | 3.3 | highlight.js loaded via CDN with SRI, matching marked.js pattern |
| AC24 | 7.3 | DOM structure is navigable by Playwright selectors |
| AC25 | 7.4 | pre[hidden] selector verifiable |
| AC26 | 7.4 | .md-rendered:not([hidden]) with .hljs-* children verifiable |
| AC27 | 7.4 | Span classes (.hljs-attr, .log-header) distinguish formatted from plain |
| AC28 | 2.1 | All changes in item.html (CDN, CSS, JS) |
| AC29 | 4.1 | Extends feature-76 renderArtifactContent and .md-rendered pattern |
