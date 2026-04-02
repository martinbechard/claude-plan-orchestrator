# Item Page Content-Type-Aware Rendering

## Status: Open

## Priority: High

## Summary

The item detail page displays all non-markdown artifact content (JSON, YAML, logs)
as raw unformatted text in dark pre blocks. This makes structured data like JSON
validation results and YAML plans very hard to read. Feature 76 added markdown
rendering via marked.js but only for .md files -- every other content type falls
through to pre.textContent with no formatting at all.

The page needs content-type-aware rendering so that each file type is displayed in
the most readable format for its content: JSON should be pretty-printed with syntax
highlighting, YAML should have highlighting, and log files should have basic
structure.

## Problem

When users view an item page, the step explorer and output artifact sections show
content from multiple file types:

- .json files (validation results, config) -- displayed as single-line raw JSON
  strings that are nearly impossible to parse visually
- .yaml/.yml files (pipeline plans) -- displayed as raw text with no visual
  distinction between keys and values
- .log files (task execution logs, validation step logs) -- displayed as raw text
  with no structure, headers or sections blend together
- .py, .ts, .html, .css files (code artifacts) -- displayed as raw text with no
  syntax highlighting

The renderArtifactContent() function in item.html only checks for .md extension.
Everything else gets pre.textContent = text with no processing.

The artifact-content endpoint (item.py lines 333-365) returns raw PlainTextResponse
for all file types -- all formatting must happen client-side.

## Scope

### S1: JSON pretty-printing and syntax highlighting

JSON content (.json files) must be pretty-printed with indentation (JSON.parse +
JSON.stringify with indent) and have syntax highlighting for keys, strings, numbers,
booleans, and null values. If JSON.parse fails, fall back to raw text display.

Verification: On the item page, expand any artifact section that shows a .json file.
The content must show indented JSON with visually distinct colors for keys vs string
values vs numbers. Specifically:
- The .md-rendered (or equivalent styled container) div must be visible, not the raw pre
- The container must contain a pre > code structure with colored spans for syntax tokens
- JSON keys, string values, numeric values, and boolean/null must each have distinct
  colors visible in the dark theme

### S2: YAML syntax highlighting

YAML content (.yaml, .yml files) must have syntax highlighting that visually
distinguishes keys from values, and highlights comments, strings, and booleans.

Verification: On the item page, expand any artifact section that shows a .yaml file.
The content must show YAML with visually distinct colors for keys vs values.
Specifically:
- The styled container div must be visible, not the raw pre
- YAML keys and values must have distinct visual treatment (different colors)

### S3: Log file section formatting

Log file content (.log files) should have basic visual structure. Lines that look
like section headers (e.g. "=== STDOUT ===" or "=== validation-step-3 ...===")
should be visually distinct from body content. JSON embedded in log lines should be
detected and pretty-printed where possible.

Verification: On the item page, expand any artifact section that shows a .log file.
- Section header lines (matching patterns like "=== ... ===") must have distinct
  visual styling (bold, different color, or background) from body lines
- If a log line contains a valid JSON object, that JSON is pretty-printed with
  indentation rather than displayed as a single-line string

### S4: Code file syntax highlighting (stretch)

Code files (.py, .ts, .html, .css) should have basic syntax highlighting. This can
use a lightweight client-side highlighter (e.g. highlight.js or Prism.js via CDN,
matching the marked.js CDN pattern already in use).

Verification: On the item page, expand any artifact section that shows a code file.
- The code must display with syntax-appropriate coloring (keywords, strings, comments
  in distinct colors)
- The styling must be consistent with the dark theme used by .md-rendered

### S5: Extend renderArtifactContent() with type dispatch

The existing renderArtifactContent(pre, mdDiv, text, path) function must be extended
to dispatch on file extension instead of only checking .md. The function should:
- Extract extension from path
- Route to the appropriate renderer (markdown, JSON, YAML, log, code, or plain text)
- Use a single styled container (the existing .md-rendered div or equivalent) for all
  formatted output, keeping the pre as fallback for truly plain content
- Maintain the existing behavior: pre hidden + styled div visible for formatted
  content; pre visible + styled div hidden for plain fallback

## Verification

General verification approach -- for EACH content type, the validator must:

1. Navigate to an item page that has artifacts of that type (use Playwright, not curl,
   because rendering is JavaScript-driven)
2. Click to expand a stage or artifact that contains the target file type
3. Wait for the AJAX fetch to complete (the "Loading..." text disappears)
4. Assert that the raw pre element is hidden (has hidden attribute)
5. Assert that the styled container div is visible and contains structured/colored
   content (not just plain text)
6. For JSON specifically: assert the content contains newlines (pretty-printed) and
   the container has child elements with distinct styling (spans with color classes)

The key gap from feature 76 was that acceptance criteria only checked "does markdown
render?" without specifying DOM-level observable evidence. Each criterion here
specifies what DOM state to assert so the validator can write meaningful Playwright
tests rather than falling back to curl.

## Files Likely Affected

| File | Change |
|---|---|
| langgraph_pipeline/web/templates/item.html | Extend renderArtifactContent(), add syntax highlighting library (CDN), add CSS for highlighted tokens |

## Dependencies

- Depends on feature 76 (markdown rendering) being complete -- this extends the same
  renderArtifactContent() function and .md-rendered container pattern

## LangSmith Trace: df8f1c88-184e-4170-b132-2ede30067349


## 5 Whys Analysis

Title: Item Page Artifact Content Readability Gap

Clarity: 4/5

**5 Whys:**

W1: Why can't users easily read structured artifact content on the item page?
    Because: Structured data like JSON, YAML, and logs are displayed as raw unformatted single-line text in dark pre blocks without indentation or syntax highlighting [C3, C4, C11, C12, C13]

W2: Why does the page display raw text for most file types?
    Because: The renderArtifactContent() function only checks for .md extensions and routes everything else to pre.textContent with no processing [C5, C15, C16]

W3: Why doesn't the function handle all content types?
    Because: Feature 76 added markdown rendering via marked.js but was scoped narrowly to only .md files without a general dispatch mechanism for other file types [C5] [ASSUMPTION: scope was intentional/resource-constrained]

W4: Why should each file type have its own rendering strategy?
    Because: Different content types (JSON, YAML, logs, code) have structural properties and visual conventions that formatted display makes legible, whereas raw text defeats the value of structured formats [C6, C7, C8, C9, C14] [ASSUMPTION: structured formats exist to improve readability when rendered correctly]

W5: Why does content readability matter on the item page specifically?
    Because: Users need to quickly interpret and verify output artifacts across multiple file types (validation results, pipeline plans, execution logs, code) to troubleshoot steps and make decisions [C10, C4] [ASSUMPTION: users cannot effectively use the platform without readable artifacts]

**Root Need:** Enable extensible content-type-aware rendering on the item page so users can efficiently interpret artifacts in all formats they encounter. The core deficiency is that renderArtifactContent() has no dispatch mechanism [C15, C16, C41] to route JSON, YAML, logs, and code to appropriate renderers [C43], forcing users to parse raw unformatted text [C11, C12, C13, C14] instead of reading formatted content [C6, C7, C8, C9].

**Summary:** Users cannot efficiently read and understand artifact content across multiple file formats because only markdown is rendered; all other types fall through to raw text display.
