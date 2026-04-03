# Structured Requirements: 87 Item Page Content Type Aware Rendering

Source: tmp/plans/.claimed/87-item-page-content-type-aware-rendering.md
Generated: 2026-04-02T23:43:36.442105+00:00

## Requirements

### P1: Structured artifact content displayed as raw unformatted text
Type: UI
Priority: high
Source clauses: [C1, C2, C59, C67, C68]
Description: The item detail page displays all non-markdown artifact content (JSON, YAML, logs, code) as raw unformatted text in dark pre blocks. This makes structured data like JSON validation results and YAML plans very hard to read, forcing users to parse raw unformatted text instead of reading formatted content. Users cannot efficiently read and understand artifact content across multiple file formats because only markdown is rendered; all other types fall through to raw text display.
Acceptance Criteria:
- Do all supported structured file types (.json, .yaml/.yml, .log, .py, .ts, .html, .css) render with formatting rather than raw unformatted text? YES = pass, NO = fail
- Is structured data (JSON, YAML) visually distinguishable from plain text? YES = pass, NO = fail

### P2: JSON files displayed as unreadable single-line raw strings
Type: UI
Priority: high
Source clauses: [C10]
Description: .json files (validation results, config) are displayed as single-line raw JSON strings that are nearly impossible to parse visually. There is no indentation, no line breaks, and no color distinction between keys, values, and structural tokens.
Acceptance Criteria:
- Are .json files displayed with indentation and line breaks rather than as a single-line string? YES = pass, NO = fail

### P3: YAML files have no visual distinction between keys and values
Type: UI
Priority: high
Source clauses: [C11]
Description: .yaml/.yml files (pipeline plans) are displayed as raw text with no visual distinction between keys and values. Users cannot quickly scan YAML structure because all text appears in the same style.
Acceptance Criteria:
- Do .yaml/.yml files display with visually distinct treatment for keys versus values? YES = pass, NO = fail

### P4: Log files have no structure and headers blend with body
Type: UI
Priority: high
Source clauses: [C12]
Description: .log files (task execution logs, validation step logs) are displayed as raw text with no structure. Section headers and body content blend together, making it difficult to navigate log output or find specific sections.
Acceptance Criteria:
- Are section header lines in .log files visually distinct from body content? YES = pass, NO = fail

### P5: Code files have no syntax highlighting
Type: UI
Priority: medium
Source clauses: [C13]
Description: .py, .ts, .html, .css files (code artifacts) are displayed as raw text with no syntax highlighting. Keywords, strings, comments, and other language constructs are all rendered identically.
Acceptance Criteria:
- Do code files (.py, .ts, .html, .css) display with syntax-appropriate coloring? YES = pass, NO = fail

### P6: renderArtifactContent has no content-type dispatch mechanism
Type: functional
Priority: high
Source clauses: [C4, C14, C15, C60, C65]
Description: The renderArtifactContent() function in item.html only checks for .md extension. Everything else gets `pre.textContent = text` with no processing. The function has no dispatch mechanism to route different file types to appropriate renderers. Feature 76 added markdown rendering via marked.js but was scoped narrowly to only .md files without a general dispatch mechanism for other file types.
Acceptance Criteria:
- Does renderArtifactContent() dispatch on file extension rather than only checking .md? YES = pass, NO = fail
- Do non-.md file types route to type-specific rendering logic rather than falling through to raw pre.textContent? YES = pass, NO = fail

---

### FR1: JSON pretty-printing and syntax highlighting
Type: UI
Priority: high
Source clauses: [C6, C18, C19, C20, C21, C22, C23, C24, C25]
Description: JSON content (.json files) must be pretty-printed with indentation (JSON.parse + JSON.stringify with indent) and have syntax highlighting for keys, strings, numbers, booleans, and null values. If JSON.parse fails, the system must fall back to raw text display. On the item page, when a user expands any artifact section that shows a .json file, the content must show indented JSON with visually distinct colors for keys vs string values vs numbers. The .md-rendered (or equivalent styled container) div must be visible, not the raw pre. The container must contain a `pre > code` structure with colored spans for syntax tokens. JSON keys, string values, numeric values, and boolean/null must each have distinct colors visible in the dark theme.
Acceptance Criteria:
- Is JSON content pretty-printed with indentation (multi-line, not single-line)? YES = pass, NO = fail
- Do JSON keys have a distinct color from string values? YES = pass, NO = fail
- Do numeric values have a distinct color from string values? YES = pass, NO = fail
- Do boolean and null values have a distinct color? YES = pass, NO = fail
- Is the styled container div visible and the raw pre element hidden when displaying JSON? YES = pass, NO = fail
- Does the container contain a `pre > code` structure with colored spans for syntax tokens? YES = pass, NO = fail
- When JSON.parse fails on malformed JSON, does the system fall back to raw text display? YES = pass, NO = fail
- Are the colors visible and distinguishable in the dark theme? YES = pass, NO = fail

### FR2: YAML syntax highlighting
Type: UI
Priority: high
Source clauses: [C7, C26, C27, C28, C29, C30, C31]
Description: YAML content (.yaml, .yml files) must have syntax highlighting that visually distinguishes keys from values, and highlights comments, strings, and booleans. On the item page, when a user expands any artifact section that shows a .yaml file, the content must show YAML with visually distinct colors for keys vs values. The styled container div must be visible, not the raw pre. YAML keys and values must have distinct visual treatment (different colors).
Acceptance Criteria:
- Do YAML keys have a visually distinct color from YAML values? YES = pass, NO = fail
- Are YAML comments highlighted distinctly? YES = pass, NO = fail
- Are YAML strings and booleans highlighted? YES = pass, NO = fail
- Is the styled container div visible and the raw pre element hidden when displaying YAML? YES = pass, NO = fail

### FR3: Log file section formatting with embedded JSON detection
Type: UI
Priority: high
Source clauses: [C8, C32, C33, C34, C35, C36, C37]
Description: Log file content (.log files) should have basic visual structure. Lines that look like section headers (e.g., "=== STDOUT ===" or "=== validation-step-3 ...===") should be visually distinct from body content with bold, different color, or background styling. JSON embedded in log lines should be detected and pretty-printed where possible. On the item page, when a user expands any artifact section that shows a .log file, section header lines (matching patterns like "=== ... ===") must have distinct visual styling from body lines. If a log line contains a valid JSON object, that JSON is pretty-printed with indentation rather than displayed as a single-line string.
Acceptance Criteria:
- Do section header lines matching "=== ... ===" patterns have distinct visual styling (bold, different color, or background) from body lines? YES = pass, NO = fail
- When a log line contains a valid JSON object, is that JSON pretty-printed with indentation? YES = pass, NO = fail
- Is the styled container div visible and the raw pre element hidden when displaying log files? YES = pass, NO = fail

### FR4: Code file syntax highlighting
Type: UI
Priority: medium
Source clauses: [C38, C39, C40, C41, C42]
Description: Code files (.py, .ts, .html, .css) should have basic syntax highlighting. This can use a lightweight client-side highlighter (e.g., highlight.js or Prism.js via CDN, matching the marked.js CDN pattern already in use). On the item page, when a user expands any artifact section that shows a code file, the code must display with syntax-appropriate coloring (keywords, strings, comments in distinct colors). The styling must be consistent with the dark theme used by .md-rendered.
Acceptance Criteria:
- Do code files display with syntax-appropriate coloring for keywords, strings, and comments? YES = pass, NO = fail
- Are at least .py, .ts, .html, and .css file types supported? YES = pass, NO = fail
- Is the syntax highlighting styling consistent with the dark theme used by .md-rendered? YES = pass, NO = fail
- Is the highlighter loaded via CDN, matching the existing marked.js CDN pattern? YES = pass, NO = fail

### FR5: Extension-based content-type dispatch in renderArtifactContent
Type: functional
Priority: high
Source clauses: [C5, C43, C44, C45, C46, C47, C64, C66]
Description: The existing renderArtifactContent(pre, mdDiv, text, path) function must be extended to dispatch on file extension instead of only checking .md. The function should: extract extension from path; route to the appropriate renderer (markdown, JSON, YAML, log, code, or plain text); use a single styled container (the existing .md-rendered div or equivalent) for all formatted output, keeping the pre as fallback for truly plain content; maintain the existing behavior where pre is hidden and styled div is visible for formatted content, and pre is visible and styled div is hidden for plain fallback. The dispatch must be extensible so that each file type is displayed in the most readable format for its content, enabling users to efficiently interpret artifacts in all formats they encounter.
Acceptance Criteria:
- Does the function extract the file extension from the path parameter? YES = pass, NO = fail
- Does the function route .md to the existing markdown renderer? YES = pass, NO = fail
- Does the function route .json to the JSON renderer? YES = pass, NO = fail
- Does the function route .yaml/.yml to the YAML renderer? YES = pass, NO = fail
- Does the function route .log to the log renderer? YES = pass, NO = fail
- Does the function route .py, .ts, .html, .css to the code renderer? YES = pass, NO = fail
- Does the function fall back to plain text for unrecognized extensions? YES = pass, NO = fail
- For formatted content, is the pre element hidden and the styled container visible? YES = pass, NO = fail
- For plain fallback content, is the pre element visible and the styled container hidden? YES = pass, NO = fail

### FR6: Verification via Playwright with DOM-level assertions
Type: non-functional
Priority: high
Source clauses: [C48, C49, C50, C51, C52, C53, C54, C55]
Description: For each content type, validation must use Playwright (not curl) because rendering is JavaScript-driven. The validation approach must: navigate to an item page that has artifacts of the target type; click to expand a stage or artifact that contains the target file type; wait for the AJAX fetch to complete (the "Loading..." text disappears); assert that the raw pre element is hidden (has hidden attribute); assert that the styled container div is visible and contains structured/colored content (not just plain text). For JSON specifically, assert the content contains newlines (pretty-printed) and the container has child elements with distinct styling (spans with color classes). Each criterion specifies what DOM state to assert so the validator can write meaningful Playwright tests rather than falling back to curl. This addresses the key gap from feature 76 where acceptance criteria only checked "does markdown render?" without specifying DOM-level observable evidence.
Acceptance Criteria:
- Are all content-type verifications performed via Playwright (not curl)? YES = pass, NO = fail
- Does each test click to expand the artifact section before asserting? YES = pass, NO = fail
- Does each test wait for AJAX completion (Loading... text disappears) before asserting? YES = pass, NO = fail
- Does each test assert the raw pre element has the hidden attribute? YES = pass, NO = fail
- Does each test assert the styled container is visible with structured content? YES = pass, NO = fail
- For JSON tests, does the assertion check for newlines and child spans with color classes? YES = pass, NO = fail

---

### FR7: Client-side formatting constraint
Type: non-functional
Priority: high
Source clauses: [C16, C17]
Description: The artifact-content endpoint (item.py lines 333-365) returns raw PlainTextResponse for all file types. All formatting must happen client-side. No server-side changes to the endpoint are required or expected; the rendering logic is entirely in the browser JavaScript.
Acceptance Criteria:
- Is all content formatting performed client-side in JavaScript? YES = pass, NO = fail
- Does the artifact-content endpoint remain unchanged (still returning PlainTextResponse)? YES = pass, NO = fail

### FR8: Dependency on feature 76 markdown rendering
Type: non-functional
Priority: high
Source clauses: [C3, C57, C58, C61]
Description: This feature depends on feature 76 (markdown rendering) being complete. It extends the same renderArtifactContent() function and .md-rendered container pattern that feature 76 introduced via marked.js. Feature 76 added markdown rendering but was scoped narrowly to only .md files; this feature extends that foundation to all content types.
Acceptance Criteria:
- Is feature 76 (markdown rendering via marked.js) complete and functional before this feature is implemented? YES = pass, NO = fail
- Does this feature build on the existing renderArtifactContent() function and .md-rendered container pattern? YES = pass, NO = fail

---

## Coverage Matrix

| Raw Input Section | Requirement(s) |
|---|---|
| Summary: non-markdown content displayed as raw text | P1, P6 |
| Summary: JSON pretty-printed with highlighting | FR1 |
| Summary: YAML should have highlighting | FR2 |
| Summary: log files should have basic structure | FR3 |
| Problem: step explorer shows multiple file types | P1 |
| Problem: .json files single-line raw strings | P2 |
| Problem: .yaml files no visual distinction | P3 |
| Problem: .log files no structure | P4 |
| Problem: .py/.ts/.html/.css no highlighting | P5 |
| Problem: renderArtifactContent only checks .md | P6 |
| Problem: artifact-content endpoint returns PlainTextResponse | FR7 |
| S1: JSON pretty-printing and syntax highlighting | FR1 |
| S1 verification: DOM assertions for JSON | FR1, FR6 |
| S2: YAML syntax highlighting | FR2 |
| S2 verification: DOM assertions for YAML | FR2, FR6 |
| S3: Log file section formatting | FR3 |
| S3 verification: DOM assertions for logs | FR3, FR6 |
| S4: Code file syntax highlighting (stretch) | FR4 |
| S4 verification: DOM assertions for code | FR4, FR6 |
| S5: Extend renderArtifactContent with type dispatch | FR5 |
| Verification: general approach with Playwright | FR6 |
| Files Likely Affected: item.html | FR5 |
| Dependencies: feature 76 | FR8 |
| 5 Whys: root need for extensible rendering | P1, P6, FR5 |
| 5 Whys: summary of overall problem | P1 |

## Clause Coverage Grid

| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [FACT] | FACT | P1 | Mapped |
| C2 [PROB] | PROB | P1 | Mapped |
| C3 [FACT] | FACT | FR8 | Mapped |
| C4 [FACT] | FACT | P6 | Mapped |
| C5 [GOAL] | GOAL | FR5 | Mapped |
| C6 [GOAL] | GOAL | FR1 | Mapped |
| C7 [GOAL] | GOAL | FR2 | Mapped |
| C8 [GOAL] | GOAL | FR3 | Mapped |
| C9 [CTX] | CTX | P1 | Mapped: provides context for the overall rendering problem |
| C10 [PROB] | PROB | P2 | Mapped |
| C11 [PROB] | PROB | P3 | Mapped |
| C12 [PROB] | PROB | P4 | Mapped |
| C13 [PROB] | PROB | P5 | Mapped |
| C14 [FACT] | FACT | P6 | Mapped |
| C15 [FACT] | FACT | P6 | Mapped |
| C16 [FACT] | FACT | FR7 | Mapped |
| C17 [CONS] | CONS | FR7 | Mapped |
| C18 [GOAL] | GOAL | FR1 | Mapped |
| C19 [GOAL] | GOAL | FR1 | Mapped |
| C20 [CONS] | CONS | FR1 | Mapped |
| C21 [AC] | AC | FR1 | Mapped |
| C22 [AC] | AC | FR1 | Mapped |
| C23 [AC] | AC | FR1 | Mapped |
| C24 [AC] | AC | FR1 | Mapped |
| C25 [AC] | AC | FR1 | Mapped |
| C26 [GOAL] | GOAL | FR2 | Mapped |
| C27 [GOAL] | GOAL | FR2 | Mapped |
| C28 [AC] | AC | FR2 | Mapped |
| C29 [AC] | AC | FR2 | Mapped |
| C30 [AC] | AC | FR2 | Mapped |
| C31 [AC] | AC | FR2 | Mapped |
| C32 [GOAL] | GOAL | FR3 | Mapped |
| C33 [GOAL] | GOAL | FR3 | Mapped |
| C34 [GOAL] | GOAL | FR3 | Mapped |
| C35 [AC] | AC | FR3 | Mapped |
| C36 [AC] | AC | FR3 | Mapped |
| C37 [AC] | AC | FR3 | Mapped |
| C38 [GOAL] | GOAL | FR4 | Mapped |
| C39 [CONS] | CONS | FR4 | Mapped |
| C40 [AC] | AC | FR4 | Mapped |
| C41 [AC] | AC | FR4 | Mapped |
| C42 [AC] | AC | FR4 | Mapped |
| C43 [GOAL] | GOAL | FR5 | Mapped |
| C44 [GOAL] | GOAL | FR5 | Mapped |
| C45 [GOAL] | GOAL | FR5 | Mapped |
| C46 [CONS] | CONS | FR5 | Mapped |
| C47 [CONS] | CONS | FR5 | Mapped |
| C48 [AC] | AC | FR6 | Mapped |
| C49 [AC] | AC | FR6 | Mapped |
| C50 [AC] | AC | FR6 | Mapped |
| C51 [AC] | AC | FR6 | Mapped |
| C52 [AC] | AC | FR6 | Mapped |
| C53 [AC] | AC | FR6 | Mapped |
| C54 [CTX] | CTX | FR6 | Mapped: motivates DOM-level assertion approach |
| C55 [CTX] | CTX | FR6 | Mapped: motivates DOM-level assertion approach |
| C56 [CTX] | CTX | FR5 | Mapped: identifies file to modify for dispatch |
| C57 [CONS] | CONS | FR8 | Mapped |
| C58 [CTX] | CTX | FR8 | Mapped: explains relationship to feature 76 |
| C59 [PROB] | PROB | P1 | Mapped |
| C60 [PROB] | PROB | P6 | Mapped |
| C61 [FACT] | FACT | FR8 | Mapped |
| C62 [CTX] | CTX | P1 | Mapped: explains why formatted display matters |
| C63 [CTX] | CTX | P1 | Mapped: explains user need for readable artifacts |
| C64 [GOAL] | GOAL | FR5 | Mapped |
| C65 [PROB] | PROB | P6 | Mapped |
| C66 [GOAL] | GOAL | FR5 | Mapped |
| C67 [PROB] | PROB | P1 | Mapped |
| C68 [PROB] | PROB | P1 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

**AC1**: On the item page, do all supported structured file types (.json, .yaml/.yml, .log, .py, .ts, .html, .css) render with formatting rather than raw unformatted text? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse) + C5 [GOAL] (operationalized)
  Belongs to: P1
  Source clauses: [C1, C2, C5, C59, C67, C68]

**AC2**: Is structured data (JSON, YAML) visually distinguishable from plain text through indentation, coloring, or other formatting? YES = pass, NO = fail
  Origin: Derived from C59 [PROB] (inverse)
  Belongs to: P1
  Source clauses: [C9, C59, C62, C63]

**AC3**: Are .json files displayed with indentation and line breaks rather than as a single-line string? YES = pass, NO = fail
  Origin: Derived from C10 [PROB] (inverse)
  Belongs to: P2
  Source clauses: [C10]

**AC4**: Do .yaml/.yml files display with visually distinct treatment for keys versus values? YES = pass, NO = fail
  Origin: Derived from C11 [PROB] (inverse)
  Belongs to: P3
  Source clauses: [C11]

**AC5**: Are section header lines in .log files visually distinct from body content? YES = pass, NO = fail
  Origin: Derived from C12 [PROB] (inverse)
  Belongs to: P4
  Source clauses: [C12]

**AC6**: Do code files (.py, .ts, .html, .css) display with syntax-appropriate coloring for keywords, strings, and comments? YES = pass, NO = fail
  Origin: Derived from C13 [PROB] (inverse)
  Belongs to: P5
  Source clauses: [C13]

**AC7**: Does renderArtifactContent() dispatch on file extension rather than only checking .md? YES = pass, NO = fail
  Origin: Derived from C60 [PROB] (inverse) + C65 [PROB] (inverse)
  Belongs to: P6
  Source clauses: [C4, C14, C15, C60, C65]

**AC8**: Do non-.md file types route to type-specific rendering logic rather than falling through to raw pre.textContent? YES = pass, NO = fail
  Origin: Derived from C60 [PROB] (inverse)
  Belongs to: P6
  Source clauses: [C4, C15, C60]

**AC9**: On the item page, when expanding any artifact section that shows a .json file, is the JSON content pretty-printed with indentation (multi-line, not single-line)? YES = pass, NO = fail
  Origin: Explicit from C21 [AC] + Derived from C18 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C6, C18, C21]

**AC10**: Does the JSON display show visually distinct colors for keys vs string values vs numbers? YES = pass, NO = fail
  Origin: Explicit from C22 [AC]
  Belongs to: FR1
  Source clauses: [C19, C22]

**AC11**: When displaying JSON, is the .md-rendered (or equivalent styled container) div visible, not the raw pre? YES = pass, NO = fail
  Origin: Explicit from C23 [AC]
  Belongs to: FR1
  Source clauses: [C23]

**AC12**: Does the JSON container contain a pre > code structure with colored spans for syntax tokens? YES = pass, NO = fail
  Origin: Explicit from C24 [AC]
  Belongs to: FR1
  Source clauses: [C24]

**AC13**: Do JSON keys, string values, numeric values, and boolean/null each have distinct colors visible in the dark theme? YES = pass, NO = fail
  Origin: Explicit from C25 [AC]
  Belongs to: FR1
  Source clauses: [C19, C25]

**AC14**: When JSON.parse fails on malformed JSON, does the system fall back to raw text display? YES = pass, NO = fail
  Origin: Derived from C20 [CONS] (operationalized as testable constraint)
  Belongs to: FR1
  Source clauses: [C20]

**AC15**: On the item page, when expanding any artifact section that shows a .yaml file, does the content show YAML with visually distinct colors for keys vs values? YES = pass, NO = fail
  Origin: Explicit from C28 [AC] + C29 [AC]
  Belongs to: FR2
  Source clauses: [C7, C26, C27, C28, C29]

**AC16**: When displaying YAML, is the styled container div visible, not the raw pre? YES = pass, NO = fail
  Origin: Explicit from C30 [AC]
  Belongs to: FR2
  Source clauses: [C30]

**AC17**: Do YAML keys and values have distinct visual treatment (different colors)? YES = pass, NO = fail
  Origin: Explicit from C31 [AC]
  Belongs to: FR2
  Source clauses: [C27, C31]

**AC18**: On the item page, when expanding any artifact section that shows a .log file, do section header lines (matching patterns like "=== ... ===") have distinct visual styling (bold, different color, or background) from body lines? YES = pass, NO = fail
  Origin: Explicit from C35 [AC] + C36 [AC]
  Belongs to: FR3
  Source clauses: [C8, C32, C33, C35, C36]

**AC19**: If a log line contains a valid JSON object, is that JSON pretty-printed with indentation rather than displayed as a single-line string? YES = pass, NO = fail
  Origin: Explicit from C37 [AC]
  Belongs to: FR3
  Source clauses: [C34, C37]

**AC20**: On the item page, when expanding any artifact section that shows a code file (.py, .ts, .html, .css), does the code display with syntax-appropriate coloring (keywords, strings, comments in distinct colors)? YES = pass, NO = fail
  Origin: Explicit from C40 [AC] + C41 [AC]
  Belongs to: FR4
  Source clauses: [C38, C40, C41]

**AC21**: Is the syntax highlighting styling for code files consistent with the dark theme used by .md-rendered? YES = pass, NO = fail
  Origin: Explicit from C42 [AC]
  Belongs to: FR4
  Source clauses: [C42]

**AC22**: Is the syntax highlighting library loaded via CDN, matching the existing marked.js CDN pattern? YES = pass, NO = fail
  Origin: Derived from C39 [CONS] (operationalized)
  Belongs to: FR4
  Source clauses: [C39]

**AC23**: Does renderArtifactContent() extract the file extension from the path parameter? YES = pass, NO = fail
  Origin: Derived from C44 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C43, C44]

**AC24**: Does the function route .md to the existing markdown renderer? YES = pass, NO = fail
  Origin: Derived from C45 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C45]

**AC25**: Does the function route .json to the JSON renderer? YES = pass, NO = fail
  Origin: Derived from C45 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C45]

**AC26**: Does the function route .yaml/.yml to the YAML renderer? YES = pass, NO = fail
  Origin: Derived from C45 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C45]

**AC27**: Does the function route .log to the log renderer? YES = pass, NO = fail
  Origin: Derived from C45 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C45]

**AC28**: Does the function route .py, .ts, .html, .css to the code renderer? YES = pass, NO = fail
  Origin: Derived from C45 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C45]

**AC29**: Does the function fall back to plain text for unrecognized extensions? YES = pass, NO = fail
  Origin: Derived from C45 [GOAL] (operationalized) + C47 [CONS]
  Belongs to: FR5
  Source clauses: [C45, C47]

**AC30**: For formatted content, is the pre element hidden and the styled container visible? YES = pass, NO = fail
  Origin: Derived from C47 [CONS] (operationalized)
  Belongs to: FR5
  Source clauses: [C46, C47]

**AC31**: For plain fallback content, is the pre element visible and the styled container hidden? YES = pass, NO = fail
  Origin: Derived from C47 [CONS] (operationalized)
  Belongs to: FR5
  Source clauses: [C47]

**AC32**: Is the dispatch mechanism extensible (new file types can be added without restructuring)? YES = pass, NO = fail
  Origin: Derived from C64 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C5, C64, C66]

**AC33**: For EACH content type, are verifications performed via Playwright (not curl), since rendering is JavaScript-driven? YES = pass, NO = fail
  Origin: Explicit from C48 [AC]
  Belongs to: FR6
  Source clauses: [C48, C54, C55]

**AC34**: Does each content-type test click to expand a stage or artifact that contains the target file type? YES = pass, NO = fail
  Origin: Explicit from C49 [AC]
  Belongs to: FR6
  Source clauses: [C49]

**AC35**: Does each test wait for the AJAX fetch to complete (the "Loading..." text disappears) before asserting? YES = pass, NO = fail
  Origin: Explicit from C50 [AC]
  Belongs to: FR6
  Source clauses: [C50]

**AC36**: Does each test assert that the raw pre element is hidden (has hidden attribute)? YES = pass, NO = fail
  Origin: Explicit from C51 [AC]
  Belongs to: FR6
  Source clauses: [C51]

**AC37**: Does each test assert that the styled container div is visible and contains structured/colored content (not just plain text)? YES = pass, NO = fail
  Origin: Explicit from C52 [AC]
  Belongs to: FR6
  Source clauses: [C52]

**AC38**: For JSON specifically, does the test assert the content contains newlines (pretty-printed) and the container has child elements with distinct styling (spans with color classes)? YES = pass, NO = fail
  Origin: Explicit from C53 [AC]
  Belongs to: FR6
  Source clauses: [C53]

**AC39**: Is all content formatting performed client-side in JavaScript (no server-side rendering changes)? YES = pass, NO = fail
  Origin: Derived from C17 [CONS] (operationalized)
  Belongs to: FR7
  Source clauses: [C16, C17]

**AC40**: Does the artifact-content endpoint remain unchanged (still returning PlainTextResponse)? YES = pass, NO = fail
  Origin: Derived from C16 [FACT] (preserved as constraint)
  Belongs to: FR7
  Source clauses: [C16]

**AC41**: Is feature 76 (markdown rendering via marked.js) complete and functional before this feature is implemented? YES = pass, NO = fail
  Origin: Derived from C57 [CONS] (operationalized)
  Belongs to: FR8
  Source clauses: [C3, C57, C61]

**AC42**: Does this feature build on the existing renderArtifactContent() function and .md-rendered container pattern from feature 76? YES = pass, NO = fail
  Origin: Derived from C58 [CTX] (operationalized)
  Belongs to: FR8
  Source clauses: [C43, C58]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2 | 2 |
| P2 | AC3 | 1 |
| P3 | AC4 | 1 |
| P4 | AC5 | 1 |
| P5 | AC6 | 1 |
| P6 | AC7, AC8 | 2 |
| FR1 | AC9, AC10, AC11, AC12, AC13, AC14 | 6 |
| FR2 | AC15, AC16, AC17 | 3 |
| FR3 | AC18, AC19 | 2 |
| FR4 | AC20, AC21, AC22 | 3 |
| FR5 | AC23, AC24, AC25, AC26, AC27, AC28, AC29, AC30, AC31, AC32 | 10 |
| FR6 | AC33, AC34, AC35, AC36, AC37, AC38 | 6 |
| FR7 | AC39, AC40 | 2 |
| FR8 | AC41, AC42 | 2 |

---

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | FACT | AC1 | Context for P1 (establishes current state being tested) |
| C2 | PROB | AC1 | Inverse |
| C3 | FACT | AC41 | Establishes dependency prerequisite |
| C4 | FACT | AC7, AC8 | Context for dispatch gap (establishes what P6 tests) |
| C5 | GOAL | AC1, AC32 | Made testable |
| C6 | GOAL | AC9 | Made testable |
| C7 | GOAL | AC15 | Made testable |
| C8 | GOAL | AC18 | Made testable |
| C9 | CTX | -- | Context only: describes where artifacts appear; not independently testable |
| C10 | PROB | AC3 | Inverse |
| C11 | PROB | AC4 | Inverse |
| C12 | PROB | AC5 | Inverse |
| C13 | PROB | AC6 | Inverse |
| C14 | FACT | AC7 | Context for P6 (establishes current .md-only check) |
| C15 | FACT | AC7, AC8 | Context for P6 (establishes fallthrough behavior) |
| C16 | FACT | AC39, AC40 | Establishes server-side constraint being verified |
| C17 | CONS | AC39 | Operationalized as testable constraint |
| C18 | GOAL | AC9 | Made testable |
| C19 | GOAL | AC10, AC13 | Made testable |
| C20 | CONS | AC14 | Operationalized as testable fallback |
| C21 | AC | AC9 | Explicit (verbatim) |
| C22 | AC | AC10 | Explicit (verbatim) |
| C23 | AC | AC11 | Explicit (verbatim) |
| C24 | AC | AC12 | Explicit (verbatim) |
| C25 | AC | AC13 | Explicit (verbatim) |
| C26 | GOAL | AC15 | Made testable |
| C27 | GOAL | AC15, AC17 | Made testable |
| C28 | AC | AC15 | Explicit (verbatim) |
| C29 | AC | AC15 | Explicit (merged with C28 -- same DOM assertion) |
| C30 | AC | AC16 | Explicit (verbatim) |
| C31 | AC | AC17 | Explicit (verbatim) |
| C32 | GOAL | AC18 | Made testable |
| C33 | GOAL | AC18 | Made testable (header pattern specified) |
| C34 | GOAL | AC19 | Made testable |
| C35 | AC | AC18 | Explicit (verbatim) |
| C36 | AC | AC18 | Explicit (merged with C35 -- same assertion) |
| C37 | AC | AC19 | Explicit (verbatim) |
| C38 | GOAL | AC20 | Made testable |
| C39 | CONS | AC22 | Operationalized as testable constraint |
| C40 | AC | AC20 | Explicit (verbatim) |
| C41 | AC | AC20 | Explicit (merged with C40 -- same assertion) |
| C42 | AC | AC21 | Explicit (verbatim) |
| C43 | GOAL | AC23, AC42 | Made testable |
| C44 | GOAL | AC23 | Made testable |
| C45 | GOAL | AC24, AC25, AC26, AC27, AC28, AC29 | Made testable (one AC per route) |
| C46 | CONS | AC30 | Operationalized as testable container pattern |
| C47 | CONS | AC30, AC31 | Operationalized as testable visibility rules |
| C48 | AC | AC33 | Explicit (verbatim) |
| C49 | AC | AC34 | Explicit (verbatim) |
| C50 | AC | AC35 | Explicit (verbatim) |
| C51 | AC | AC36 | Explicit (verbatim) |
| C52 | AC | AC37 | Explicit (verbatim) |
| C53 | AC | AC38 | Explicit (verbatim) |
| C54 | CTX | -- | Context only: motivates DOM-level assertion approach; not independently testable |
| C55 | CTX | -- | Context only: motivates DOM-level assertion approach; not independently testable |
| C56 | CTX | -- | Context only: identifies file to modify; not independently testable |
| C57 | CONS | AC41 | Operationalized as dependency check |
| C58 | CTX | AC42 | Operationalized: verifies architectural continuity with feature 76 |
| C59 | PROB | AC1, AC2 | Inverse |
| C60 | PROB | AC7, AC8 | Inverse |
| C61 | FACT | AC41 | Establishes feature 76 scope (context for dependency) |
| C62 | CTX | -- | Context only: explains why formatted display matters; not independently testable |
| C63 | CTX | -- | Context only: explains user need; not independently testable |
| C64 | GOAL | AC32 | Made testable |
| C65 | PROB | AC7 | Inverse |
| C66 | GOAL | AC25, AC26, AC27 | Made testable (routing to renderers) |
| C67 | PROB | AC1 | Inverse |
| C68 | PROB | AC1, AC2 | Inverse |

---

### Justification for clauses without ACs

| Clause | Type | Justification |
|---|---|---|
| C9 | CTX | Describes where artifacts appear (step explorer, output sections). Provides spatial context for the problem but is not an independently testable behavior. Covered implicitly by AC34 (clicking to expand artifacts). |
| C54 | CTX | Explains *why* DOM-level assertions are needed (gap from feature 76). Motivational context for the FR6 approach, not a testable behavior itself. |
| C55 | CTX | Explains *what* DOM state assertions enable (meaningful Playwright tests). Design rationale, not a testable behavior. |
| C56 | CTX | Identifies the file to modify (item.html). Implementation guidance, not a testable behavior. |
| C62 | CTX | Explains why formatted display is better than raw text (structural properties of formats). Rationale, not testable. |
| C63 | CTX | Explains user workflow need (interpret artifacts to troubleshoot). User motivation, not testable. |
