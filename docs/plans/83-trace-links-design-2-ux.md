# UX Design: Execution History Tree Rendering

Design competition entry for task 0.2 (UX perspective).
Parent design: docs/plans/2026-04-02-83-trace-links-empty-or-missing-design.md
Work item: tmp/plans/.claimed/83-trace-links-empty-or-missing.md

---

## 1. Design Philosophy

The execution history tree is the primary debugging surface for pipeline runs.
Users arrive here from a trace link in the completions table to understand what
happened during execution. The design must:

- Render immediately with visible progress, not a permanent "Loading..." state
- Show the execution hierarchy at a glance without requiring interaction
- Use familiar expand/collapse patterns already established in style.css
- Differentiate node types and statuses visually without relying on color alone
- Work entirely within the existing vanilla HTML/CSS/JS stack (no framework)

---

## 2. Page States

The page has four mutually exclusive states. Each must be handled explicitly.

### 2.1 Loading State

**Trigger:** Page load, before API response arrives.

**Visual:** A skeleton pulse animation inside the #execution-tree container.
Show 3-4 placeholder bars of varying widths to suggest tree structure, using
a CSS shimmer animation on a light gray background. This replaces the current
static "Loading execution tree..." text.

```
 +------------------------------------------------------+
 | [====  skeleton bar  ====                           ] |  <- 80% width
 |   [====  skeleton bar  ====                     ]     |  <- 60% width, indented
 |   [====  skeleton bar  ====                   ]       |  <- 55% width, indented
 | [====  skeleton bar  ====                       ]     |  <- 65% width
 +------------------------------------------------------+
```

CSS class: `.tree-skeleton` with `@keyframes shimmer` animation.
Skeleton bars use `.tree-skeleton-bar` with varying widths via inline style.

### 2.2 Error State

**Trigger:** API fetch fails (network error, 500, timeout).

**Visual:** An error card using the existing `.empty-state` pattern with a red
accent. Shows an error icon, a human-readable message, and a "Retry" button.

```
 +------------------------------------------------------+
 |                                                      |
 |               [!] Failed to load                     |
 |          execution tree for this run.                |
 |                                                      |
 |              [ Retry ]    (link style)               |
 |                                                      |
 +------------------------------------------------------+
```

CSS class: `.tree-error` extends `.empty-state` with `color: #991b1b` and
a left border accent `border-left: 3px solid #ef4444` (matching error-row pattern).
The retry button triggers a fresh fetch.

### 2.3 Empty Tree State

**Trigger:** API returns successfully but the tree has no children (only a root
node with zero descendants). This happens for synthetic trace rows that were
backfilled without LangSmith data.

**Visual:** A summary card showing the root run metadata (name, status, duration,
cost) followed by an informational message explaining no detailed trace data
exists. Uses the existing `.detail-header` card pattern.

```
 +------------------------------------------------------+
 | Run: 83-trace-links-empty-or-missing                 |
 | Status: [SUCCESS]  Duration: 2m 34s  Cost: $0.45     |
 +------------------------------------------------------+
 |                                                      |
 |   No detailed execution steps available for this     |
 |   run. The trace was created without LangSmith       |
 |   instrumentation.                                   |
 |                                                      |
 +------------------------------------------------------+
```

The root run metadata comes from the template context (run dict passed by the
route), not the API response, so this fallback renders even if the API returns
an empty tree array. The run data is embedded in a `data-run-json` attribute
on the #execution-tree element.

### 2.4 Tree Rendered State

**Trigger:** API returns a tree with at least one child node.

**Visual:** Full interactive tree described in sections 3-7 below.

---

## 3. Tree Visual Hierarchy

### 3.1 Indentation and Nesting

Each tree level indents by 24px using `padding-left: calc(depth * 24px)` where
depth is computed during DOM construction. The indentation creates a clear
parent-child visual relationship without connecting lines (which add visual
noise in text-heavy trees).

Maximum visible depth: 6 levels. Deeper nodes are accessible but the
indentation caps at 6 * 24px = 144px to prevent excessive horizontal scrolling
on narrow viewports.

### 3.2 Node Layout

Each tree node is a single horizontal row containing these elements left to
right:

```
[toggle] [icon] [display_name]  [status badge]  [duration]  [cost]  [tokens]
```

**Layout spec:**

| Element | Width | Alignment |
|---------|-------|-----------|
| Toggle arrow | 16px fixed | center |
| Node type icon | 16px fixed | center |
| Display name | flex: 1 (fills remaining) | left |
| Status badge | auto (content-sized) | center |
| Duration | 70px fixed | right |
| Cost | 70px fixed | right |
| Tokens | 70px fixed | right |

The metrics columns (duration, cost, tokens) use tabular alignment so values
line up vertically across rows for easy scanning.

### 3.3 Node Spacing

- Each node row: `padding: 6px 12px` with `min-height: 32px`
- Alternating row backgrounds: odd rows `#ffffff`, even rows `#f8fafc`
- Hover: `background: #f0f5ff` (light blue tint matching existing table hover)
- Focused (keyboard): `outline: 2px solid #3b6fcf; outline-offset: -2px`

---

## 4. Node Type Differentiation

Each node type gets a distinct text icon prefix and a subtle background tint on
the icon area. No emoji -- we use monospace ASCII symbols for consistent
rendering across platforms.

| node_type | Icon | Label | Color accent |
|-----------|------|-------|-------------|
| graph_node | G | Graph | #3b6fcf (blue) |
| subgraph | S | Subgraph | #6d28d9 (purple) |
| agent | A | Agent | #0891b2 (teal) |
| tool_call | T | Tool | #d97706 (amber) |

**Icon rendering:** Each icon is a 20px x 20px circle with the letter centered
in white, background filled with the accent color. CSS class:
`.node-icon.node-icon--{type}`.

```css
.node-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    font-size: 11px;
    font-weight: 700;
    color: #fff;
    flex-shrink: 0;
}
.node-icon--graph_node { background: #3b6fcf; }
.node-icon--subgraph   { background: #6d28d9; }
.node-icon--agent      { background: #0891b2; }
.node-icon--tool_call  { background: #d97706; }
```

This approach:
- Works without emoji font support
- Provides color + shape + letter triple-encoding for accessibility
- Stays compact in the tree row

---

## 5. Status Indicators

Status badges reuse the existing `.badge` pattern from style.css with additions
for the "running" state.

| status | Badge class | Background | Text | Extra |
|--------|------------|------------|------|-------|
| success | `.badge-success` | #d1fae5 | #065f46 | (existing) |
| error | `.badge-error` | #fee2e2 | #991b1b | (existing) |
| running | `.badge-running` | #dbeafe | #1e40af | pulse animation |
| unknown | `.badge-unknown` | #f3f4f6 | #6b7280 | (existing) |

**New: running badge** gets a subtle pulse animation to indicate active work:

```css
.badge-running {
    background: #dbeafe;
    color: #1e40af;
    animation: badge-pulse 2s ease-in-out infinite;
}
@keyframes badge-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
}
```

The badge text is the status value in uppercase (e.g., "SUCCESS", "ERROR").
This provides text redundancy so the status is not conveyed by color alone
(WCAG 1.4.1 compliance).

---

## 6. Duration and Cost Display Format

### 6.1 Duration

Format rules:
- Under 1 second: `0.XXs` (e.g., `0.12s`)
- 1-59 seconds: `X.Xs` (e.g., `3.4s`)
- 60+ seconds: `Xm Ys` (e.g., `2m 34s`)
- Null/zero: `--` (em dash)

### 6.2 Cost

Format rules:
- Non-zero: `$X.XXXX` with 4 decimal places (e.g., `$0.0123`)
- Zero: `--`
- Null: `--`

No tilde prefix per project convention.

### 6.3 Token Count

Format rules:
- Non-zero: comma-separated thousands (e.g., `1,234`)
- Zero or null: `--`

### 6.4 Column Headers

The metrics area shows a subtle header row above the tree (not a full table
header -- just right-aligned labels):

```
                                              Duration     Cost    Tokens
```

These labels use `font-size: 11px; color: #9090b0; text-transform: uppercase;
letter-spacing: 0.06em` matching the existing `.session-stat-label` pattern.

---

## 7. Collapse/Expand Affordances

### 7.1 Toggle Arrow

Nodes with children show a toggle arrow to the left of the node icon:
- Collapsed: `content: ">"` (right-pointing)
- Expanded: `content: "v"` (down-pointing)
- Leaf nodes (no children): no arrow, space reserved for alignment

The toggle uses the same `details > summary` HTML pattern already used in
`.row-details`, `.json-block`, and `.grandchild-toggle` throughout style.css.
This gives us native expand/collapse behavior with:
- Click to toggle
- Keyboard Enter/Space to toggle (built into `<details>`)
- `aria-expanded` managed automatically by the browser

### 7.2 Default Expand State

- Root node: always expanded (open attribute set)
- Depth 1 children: expanded by default
- Depth 2+: collapsed by default

Rationale: Most trees have 1-2 levels of meaningful hierarchy. Expanding the
first two levels gives immediate context without overwhelming the user with
deeply nested tool calls.

### 7.3 Expand All / Collapse All

A toolbar above the tree with two text-style buttons:

```
[Expand All]  [Collapse All]         N nodes total
```

These iterate all `<details>` elements and set/remove the `open` attribute.
The node count is informational and helps gauge tree complexity.

---

## 8. Keyboard Accessibility

### 8.1 Focus Management

- Tab moves between toggle arrows (each is a `<summary>` element, natively
  focusable)
- Enter/Space on a summary toggles expand/collapse (native `<details>` behavior)
- The tree container has `role="tree"` and each node row has `role="treeitem"`
  with `aria-level` set to its depth + 1

### 8.2 Screen Reader Annotations

- Each node row includes a visually hidden summary: e.g.,
  `"Tool call: Read, status success, duration 0.12s"`
- The toggle state is conveyed via `aria-expanded` (native with `<details>`)
- Status badges include the text label (not color-only)

---

## 9. Responsive Layout

### 9.1 Desktop (>768px)

Full layout as described in section 3.2. All metric columns visible.
Tree width follows `main { max-width: 1200px }` from existing layout.

### 9.2 Tablet/Mobile (<=768px)

- Metric columns (duration, cost, tokens) move below the node name as a
  secondary line in smaller text
- Node row becomes two-line:
  ```
  [toggle] [icon] [display_name]  [status badge]
                  0.12s  $0.001  1,234 tokens
  ```
- Indentation reduces to 16px per level (from 24px)
- Max indent depth reduces to 4 levels

CSS implementation via `@media (max-width: 768px)` media query.

---

## 10. Tree Container Structure

The overall page structure within the `{% block content %}`:

```
<h1>Execution History</h1>

+-- .detail-header (run summary card) --------+
| Run: <display_name>                          |
| ID: <run_id>  Status: [badge]  Duration  Cost|
+----------------------------------------------+

+-- .tree-toolbar -------- --------------------+
| [Expand All]  [Collapse All]     12 nodes    |
+----------------------------------------------+

+-- .tree-container (white card) --------------+
|  .tree-metrics-header (Duration/Cost/Tokens) |
|  ------------------------------------------- |
|  [v] (G) orchestrator           [SUCCESS] 2m |
|    [v] (A) supervisor           [SUCCESS] 1m |
|      [>] (T) Read: file.py     [SUCCESS] 0s |
|      [>] (T) Write: out.py     [SUCCESS] 0s |
|    [>] (A) validator            [SUCCESS] 30s|
+----------------------------------------------+
```

The `.tree-container` uses the existing card pattern:
`background: #fff; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden;`

---

## 11. Color Palette Summary

All colors reuse existing style.css values except where noted:

| Purpose | Color | Source |
|---------|-------|--------|
| Text primary | #1a1a2e | existing body color |
| Text secondary | #6b7280 | existing muted text |
| Text metric label | #9090b0 | existing stat label |
| Link blue | #3b6fcf | existing link color |
| Success green | #065f46 on #d1fae5 | existing badge-success |
| Error red | #991b1b on #fee2e2 | existing badge-error |
| Running blue | #1e40af on #dbeafe | NEW (matches item-type-feature) |
| Unknown gray | #6b7280 on #f3f4f6 | existing badge-unknown |
| Row hover | #f0f5ff | similar to existing fafbff |
| Card border | #e2e8f0 | existing card border |
| Card background | #fff | existing card bg |
| Alternating row | #f8fafc | existing thead bg |

---

## 12. Interaction Flow

### 12.1 Page Load Sequence

1. Browser renders HTML shell with skeleton loader in #execution-tree
2. JS reads `data-run-id` from #execution-tree element
3. JS reads `data-run-json` for fallback run metadata
4. JS calls `fetch("/api/execution-tree/" + runId)`
5. On success with children: render tree, remove skeleton
6. On success without children: render empty-tree state with run metadata
7. On error: render error state with retry button

### 12.2 User Interaction Patterns

| Action | Result |
|--------|--------|
| Click toggle arrow | Expand/collapse that node's children |
| Click "Expand All" | All nodes expand |
| Click "Collapse All" | All nodes collapse to root |
| Click "Retry" (error state) | Re-fetch from API |
| Tab key | Move focus between toggle arrows |
| Enter/Space on focus | Toggle expand/collapse |

---

## 13. AC Traceability

| AC | How this design addresses it |
|----|------------------------------|
| AC2 | Tree renders actual content (nodes with names, badges, metrics) instead of "Loading..." |
| AC3 | Page renders the tree view when navigated to via trace link; no 404 for valid runs |
| AC4 | Nested collapsible hierarchy shows parent-child relationships with indentation |
| AC5 | Display name, status, duration, cost, and token count are shown per node from LangSmith trace data |

---

## 14. Implementation Notes for Frontend Developer

1. Use `<details>` + `<summary>` for expand/collapse -- this is already the
   established pattern in the codebase and provides free keyboard + aria support
2. Build the tree recursively: a `renderNode(node, depth)` function that returns
   a `<details>` element containing a `<summary>` (the node row) and child nodes
3. The run summary card at the top uses the existing `.detail-header` class
4. All new CSS goes in style.css under an `/* -- Execution tree -- */` section
5. The JS file is `execution-history.js`, loaded via `{% block extra_head %}`
6. No external dependencies -- vanilla JS only
