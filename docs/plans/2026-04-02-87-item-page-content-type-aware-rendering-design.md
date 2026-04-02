# Design: 87 Item Page Content-Type-Aware Rendering

Source: tmp/plans/.claimed/87-item-page-content-type-aware-rendering.md
Requirements: docs/plans/2026-04-02-87-item-page-content-type-aware-rendering-requirements.md

## Architecture Overview

This feature extends the existing renderArtifactContent() function in item.html
to dispatch on file extension, routing each content type to an appropriate
client-side renderer. The current function only handles .md via marked.js and
falls back to raw pre.textContent for everything else.

The approach adds highlight.js via CDN (matching the existing marked.js CDN
pattern) for syntax highlighting of JSON, YAML, and code files. Log files get a
custom lightweight formatter. All formatted output uses the existing .md-rendered
styled container div, keeping the pre element as fallback for unrecognized types.

All changes are client-side only -- the server's artifact-content endpoint
returns raw PlainTextResponse and is not modified (FR7, AC39, AC40).

### Key file

| File | Change |
|---|---|
| langgraph_pipeline/web/templates/item.html | Extend renderArtifactContent() with extension-based dispatch, add highlight.js CDN script/CSS, add CSS for log formatting and JSON token colors, add individual renderer functions |

### CDN Library Choice

highlight.js is chosen over Prism.js because:
- Simpler API (single hljs.highlight() call vs requiring DOM manipulation)
- Built-in language detection as fallback
- Dark themes that match the existing .md-rendered styling
- CDN bundle can include just the needed languages (json, yaml, python, typescript, xml/html, css)

## Design Decisions

### D1: Extension-based dispatch table in renderArtifactContent()
Addresses: P1, P6, FR5, FR8
Satisfies: AC1, AC7, AC8, AC23, AC24, AC25, AC26, AC27, AC28, AC29, AC30, AC31, AC32, AC42
Approach: Replace the single .md check with an extension extraction step and a
dispatch map. The function extracts the lowercase extension from the path via
path.split('.').pop().toLowerCase(), then looks it up in a map of extension ->
renderer function. Each renderer receives (pre, mdDiv, text) and is responsible
for populating mdDiv with formatted content and hiding pre, or falling back to
plain text. The existing .md-rendered container is reused for all formatted types.
Unrecognized extensions fall through to the existing pre.textContent behavior.
All rendering is client-side JavaScript; no server changes required. This builds
on the existing renderArtifactContent() function and .md-rendered container pattern
from feature 76.
Files: langgraph_pipeline/web/templates/item.html

### D2: JSON renderer with pretty-printing and syntax highlighting
Addresses: P2, FR1
Satisfies: AC2, AC3, AC9, AC10, AC11, AC12, AC13, AC14
Approach: A renderJSON(pre, mdDiv, text) function that: (1) tries JSON.parse(text),
(2) on success, pretty-prints via JSON.stringify(parsed, null, 2), (3) creates a
pre > code.hljs structure inside mdDiv, (4) applies highlight.js JSON highlighting
for colored tokens (keys via hljs-attr, strings via hljs-string, numbers via
hljs-number, booleans/null via hljs-literal), (5) hides the raw pre and shows
mdDiv. On parse failure, falls back to raw pre.textContent display. The pre > code
structure with hljs classes produces colored spans with distinct styling per token
type in the dark theme.
Files: langgraph_pipeline/web/templates/item.html

### D3: YAML renderer with syntax highlighting
Addresses: P3, FR2
Satisfies: AC4, AC15, AC16, AC17
Approach: A renderYAML(pre, mdDiv, text) function that creates a pre > code.hljs
structure inside mdDiv and applies highlight.js YAML highlighting. This produces
colored spans distinguishing keys from values (hljs-attr vs hljs-string), and
highlighting comments (hljs-comment), strings, and booleans (hljs-literal). The
styled container is shown and raw pre is hidden.
Files: langgraph_pipeline/web/templates/item.html

### D4: Log renderer with section headers and embedded JSON
Addresses: P4, FR3
Satisfies: AC5, AC18, AC19
Approach: A renderLog(pre, mdDiv, text) function that processes log text line by
line: (1) lines matching /^={3,}\s.*={3,}$/ are wrapped in a styled header element
(bold, distinct background color), (2) lines that look like JSON (start with { or
[) are attempted to parse; on success, the JSON is pretty-printed and highlighted
inline, (3) all other lines are rendered as plain text within a pre inside mdDiv.
This is a lightweight custom formatter, not highlight.js, since log files have no
standard grammar.
Files: langgraph_pipeline/web/templates/item.html

### D5: Code renderer with highlight.js syntax highlighting
Addresses: P5, FR4
Satisfies: AC6, AC20, AC21, AC22
Approach: A renderCode(pre, mdDiv, text, ext) function that creates a pre > code
structure inside mdDiv and applies highlight.js with the language mapped from the
file extension (.py -> python, .ts -> typescript, .html -> xml, .css -> css). Uses
a dark theme CSS from highlight.js CDN (e.g. github-dark or atom-one-dark) that is
consistent with the .md-rendered dark theme. The highlight.js library and language
modules are loaded via CDN script tags matching the existing marked.js pattern.
Files: langgraph_pipeline/web/templates/item.html

### D6: Playwright-verifiable DOM structure
Addresses: FR6
Satisfies: AC33, AC34, AC35, AC36, AC37, AC38
Approach: All renderers (D2-D5) produce content inside the existing .md-rendered
div and hide the raw pre element. highlight.js automatically generates span
elements with class names (hljs-attr, hljs-string, hljs-number, etc.) that serve
as assertable DOM markers. The log renderer (D4) uses CSS classes for header lines.
The existing "Loading..." text pattern is preserved as the AJAX wait condition.
Verification must use Playwright (not curl) since rendering is JavaScript-driven.
No additional work is needed beyond the renderer implementations since the DOM
structure is an inherent outcome of using highlight.js and styled containers.
Files: langgraph_pipeline/web/templates/item.html

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | Dispatch table routes all supported types to formatters instead of raw pre |
| AC2 | D2 | JSON.parse + JSON.stringify + highlight.js makes structured data visually distinct |
| AC3 | D2 | JSON.stringify(parsed, null, 2) produces indented multi-line output |
| AC4 | D3 | highlight.js YAML grammar distinguishes keys (hljs-attr) from values |
| AC5 | D4 | Regex-matched header lines wrapped in styled element with bold + background |
| AC6 | D5 | highlight.js with language-specific grammar produces keyword/string/comment coloring |
| AC7 | D1 | Extension extraction + dispatch map replaces single .md check |
| AC8 | D1 | Each file type routes to its renderer instead of falling through to pre.textContent |
| AC9 | D2 | JSON.parse + JSON.stringify with indent = 2 produces pretty-printed output |
| AC10 | D2 | highlight.js JSON grammar produces hljs-attr (keys), hljs-string, hljs-number spans |
| AC11 | D2 | Renderer shows mdDiv (styled container) and hides pre |
| AC12 | D2 | Creates pre > code.hljs structure with colored spans inside mdDiv |
| AC13 | D2 | highlight.js JSON grammar colors keys, strings, numbers, booleans, null distinctly in dark theme |
| AC14 | D2 | try/catch around JSON.parse; on failure, falls back to pre.textContent |
| AC15 | D3 | highlight.js YAML grammar applied; keys and values get distinct colors |
| AC16 | D3 | Renderer shows mdDiv and hides pre for YAML |
| AC17 | D3 | YAML keys (hljs-attr) and values (hljs-string) have distinct visual treatment |
| AC18 | D4 | Lines matching /^={3,}\s.*={3,}$/ styled with bold, distinct background |
| AC19 | D4 | Lines starting with { or [ are JSON.parse attempted; on success, pretty-printed inline |
| AC20 | D5 | highlight.js with language mapping (.py->python, .ts->typescript, etc.) |
| AC21 | D5 | highlight.js dark theme CSS (github-dark) consistent with .md-rendered |
| AC22 | D5 | highlight.js loaded via CDN script tags matching marked.js pattern |
| AC23 | D1 | Extension extracted via path.split('.').pop().toLowerCase() |
| AC24 | D1 | Dispatch map routes .md to existing marked.js renderer |
| AC25 | D1 | Dispatch map routes .json to JSON renderer (D2) |
| AC26 | D1 | Dispatch map routes .yaml/.yml to YAML renderer (D3) |
| AC27 | D1 | Dispatch map routes .log to log renderer (D4) |
| AC28 | D1 | Dispatch map routes .py/.ts/.html/.css to code renderer (D5) |
| AC29 | D1 | Unrecognized extensions fall through to pre.textContent (plain text) |
| AC30 | D1 | Formatted: pre hidden + mdDiv visible |
| AC31 | D1 | Plain fallback: pre visible + mdDiv hidden |
| AC32 | D1 | Dispatch map is a simple object literal; new types added by adding key-value pairs |
| AC33 | D6 | All verification uses Playwright for JavaScript-driven rendering |
| AC34 | D6 | Tests click to expand artifact sections before asserting |
| AC35 | D6 | Tests wait for "Loading..." text to disappear before asserting |
| AC36 | D6 | Tests assert raw pre element has hidden attribute |
| AC37 | D6 | Tests assert styled container is visible with structured content |
| AC38 | D6 | JSON tests assert newlines and child spans with hljs-* color classes |
| AC39 | D1 | All rendering is client-side JavaScript; no server changes |
| AC40 | -- | Constraint: artifact-content endpoint not modified (no design action needed) |
| AC41 | -- | Prerequisite: feature 76 must be complete before implementation begins |
| AC42 | D1 | Dispatch table extends existing renderArtifactContent() and .md-rendered pattern |
