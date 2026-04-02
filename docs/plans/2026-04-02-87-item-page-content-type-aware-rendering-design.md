# Design: 87 Item Page Content-Type-Aware Rendering

Source: tmp/plans/.claimed/87-item-page-content-type-aware-rendering.md
Requirements: docs/plans/2026-04-02-87-item-page-content-type-aware-rendering-requirements.md

## Architecture Overview

All changes are confined to a single file: langgraph_pipeline/web/templates/item.html.
The existing renderArtifactContent(pre, mdDiv, text, path) function currently checks
only .md extensions and falls through to raw pre.textContent for everything else.

This design extends the function into a content-type dispatcher that routes each file
extension to an appropriate renderer. A syntax highlighting library (highlight.js) is
loaded via CDN -- matching the existing marked.js CDN pattern -- to handle JSON, YAML,
and code files. Log files get a custom lightweight renderer that detects section headers
and embedded JSON.

All formatted output uses the existing .md-rendered div (or equivalent styled container),
maintaining the pre-hidden/div-visible pattern already established by feature 76.

## Key Files

| File | Change |
|---|---|
| langgraph_pipeline/web/templates/item.html | Extend renderArtifactContent(), add highlight.js CDN + dark theme CSS, add custom log renderer, add syntax token CSS |

## Design Decisions

### D1: Extension-based dispatch in renderArtifactContent()

Addresses: P5, FR1
Satisfies: AC5, AC6, AC7, AC8, AC9, AC10, AC11, AC28, AC29
Approach: Replace the single .md check with an extension extraction step (path.split('.').pop().toLowerCase()) followed by a switch/if-else chain dispatching to: markdown (.md), JSON (.json), YAML (.yaml/.yml), log (.log), code (.py/.ts/.html/.css), and plain text fallback. All formatted renderers use the .md-rendered div (pre hidden, div visible). Unrecognized extensions use pre.textContent (pre visible, div hidden). This extends the feature-76 pattern without breaking it.
Files: langgraph_pipeline/web/templates/item.html

### D2: highlight.js via CDN for syntax highlighting

Addresses: P4, FR5, FR2, FR3
Satisfies: AC4, AC22, AC23, AC13, AC14, AC17, AC18, AC19, AC20
Approach: Add highlight.js core + JSON, YAML, Python, TypeScript, HTML, CSS language modules via CDN with SRI hashes (matching marked.js pattern). Use a dark theme CSS (e.g., github-dark or atom-one-dark) from the highlight.js CDN. Call hljs.highlight(text, {language: ext}) for code files, JSON, and YAML, then place the result into a pre > code structure inside the .md-rendered div. This gives colored spans for syntax tokens with distinct colors for keys, strings, numbers, booleans, keywords, and comments -- all from the library with no custom tokenizer needed.
Files: langgraph_pipeline/web/templates/item.html

### D3: JSON pretty-printing before highlighting

Addresses: P1, FR2
Satisfies: AC1, AC12, AC13, AC14, AC15, AC16
Approach: For .json files, first attempt JSON.parse(text) then JSON.stringify(parsed, null, 2) to produce indented output. Then pass the pretty-printed string through hljs.highlight(text, {language: 'json'}) for syntax coloring. If JSON.parse throws, fall back to raw text display (pre.textContent). The pretty-printing ensures newlines and indentation; the highlighting ensures colored spans for keys vs strings vs numbers vs booleans/null.
Files: langgraph_pipeline/web/templates/item.html

### D4: Custom log file renderer

Addresses: P3, FR4
Satisfies: AC3, AC21
Approach: For .log files, split text into lines. For each line: (1) check if it matches a section header pattern (/^={2,}\s.*={2,}$/ or similar), and if so wrap in a styled span with bold font-weight, distinct color, and optional background. (2) Check if the line contains a JSON object (starts with { or contains { after a prefix), attempt JSON.parse on the extracted portion, and if valid, replace with indented JSON.stringify output. (3) Otherwise render as plain text. Assemble into the .md-rendered div as a pre element with mixed styled content.
Files: langgraph_pipeline/web/templates/item.html

### D5: Dark theme CSS for highlighted tokens

Addresses: FR2, FR3, FR5
Satisfies: AC14, AC18, AC22
Approach: Use the highlight.js built-in dark theme CSS loaded via CDN (github-dark.min.css or similar). This provides consistent dark-theme coloring for all syntax token classes (.hljs-keyword, .hljs-string, .hljs-number, .hljs-attr, .hljs-literal, .hljs-comment) that harmonizes with the existing .md-rendered dark background (#1a1a2e). Add minor overrides if needed to match the exact background/text colors.
Files: langgraph_pipeline/web/templates/item.html

### D6: DOM-level verifiable structure

Addresses: FR6
Satisfies: AC24, AC25, AC26, AC27
Approach: All renderers produce DOM elements inside the .md-rendered div that are testable via Playwright: (1) The raw pre gets hidden attribute set for formatted types. (2) The .md-rendered div is visible with structured child elements. (3) JSON/YAML/code use pre > code.hljs with child span elements carrying .hljs-* class names that have distinct computed colors. (4) Log files use a pre with child span.log-header elements. Playwright tests can assert: pre[hidden] exists, .md-rendered:not([hidden]) exists, and .md-rendered contains spans with highlight classes.
Files: langgraph_pipeline/web/templates/item.html

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D3 | JSON.parse + JSON.stringify(_, null, 2) for pretty-printing |
| AC2 | D2 | highlight.js YAML language module provides key/value color distinction |
| AC3 | D4 | Custom log renderer with regex-based header detection and bold/color styling |
| AC4 | D2 | highlight.js language modules for .py, .ts, .html, .css |
| AC5 | D1 | Extension dispatch replaces single .md check |
| AC6 | D1 | path.split('.').pop().toLowerCase() extracts extension |
| AC7 | D1 | Switch/if-else chain dispatches to markdown, JSON, YAML, log, code renderers |
| AC8 | D1 | Default/else branch falls back to pre.textContent |
| AC9 | D1 | All formatted renderers output to the .md-rendered div |
| AC10 | D1 | Formatted renderers set pre.hidden=true, mdDiv.hidden=false |
| AC11 | D1 | Plain fallback sets pre.hidden=false, mdDiv.hidden=true |
| AC12 | D3 | JSON uses .md-rendered div (not raw pre) |
| AC13 | D2, D3 | hljs.highlight produces pre > code with colored spans |
| AC14 | D2, D3, D5 | highlight.js dark theme assigns distinct colors per token type |
| AC15 | D3 | try/catch around JSON.parse; catch branch uses pre.textContent |
| AC16 | D3, D6 | Pretty-printed JSON has newlines; hljs produces child spans with classes |
| AC17 | D2 | YAML uses .md-rendered div via same show/hide pattern |
| AC18 | D2, D5 | highlight.js YAML theme colors .hljs-attr vs .hljs-string distinctly |
| AC19 | D2, D5 | highlight.js highlights YAML comments as .hljs-comment |
| AC20 | D2, D5 | highlight.js highlights strings (.hljs-string) and booleans (.hljs-literal) |
| AC21 | D4 | Log renderer detects embedded JSON objects and pretty-prints them |
| AC22 | D5 | highlight.js dark theme CSS harmonizes with .md-rendered background |
| AC23 | D2 | highlight.js loaded via CDN, matching marked.js CDN pattern |
| AC24 | D6 | DOM structure is navigable and assertable by Playwright |
| AC25 | D6 | pre.hidden=true set for all formatted content types |
| AC26 | D6 | .md-rendered visible with child elements carrying .hljs-* classes |
| AC27 | D6 | Span classes and computed colors distinguish formatted from plain text |
| AC28 | D1, D2, D5 | All changes in item.html (CDN scripts, CSS, JS function) |
| AC29 | D1 | Extends feature-76 renderArtifactContent() and .md-rendered pattern |
