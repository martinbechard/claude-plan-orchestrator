# Systems Design: Execution History Tree Rendering

Design competition entry for task 0.1 (systems-designer).
Parent design: docs/plans/2026-04-02-83-trace-links-empty-or-missing-design.md
Covers: D4 (client-side execution tree rendering), UC1, AC2, AC3, AC4, AC5.

## 1. Architecture Overview

The execution history page follows a two-phase rendering pattern:

```
Phase 1 (server):  Jinja2 template embeds run metadata as data attributes
Phase 2 (client):  execution-history.js fetches tree JSON, builds DOM
```

```
+---------------------------+      +----------------------------+
| execution_history.py      |      | /api/execution-tree/{id}   |
| (FastAPI route)           |      | (JSON API - already exists)|
+---------------------------+      +----------------------------+
| 1. get_run(run_id)        |      | Returns:                   |
| 2. Pass run dict + run_id |      | { run_id, tree: TreeNode[] }|
|    to template context    |      |                            |
+---------------------------+      +----------------------------+
            |                                   ^
            v                                   |
+---------------------------+                   |
| execution_history.html    |                   |
| (Jinja2 template)         |     fetch()       |
| - data-run-id             | ----------------->|
| - data-run-name           |
| - data-run-status         |
| - data-run-duration       |
+---------------------------+
            |
            v
+---------------------------+
| execution-history.js      |
| (new, vanilla JS)         |
| - fetchTree()             |
| - renderTree()            |
| - renderEmptyState()      |
| - toggleNode()            |
+---------------------------+
```

## 2. Data Flow

### 2.1 Server-Side Bootstrap

The execution_history.py route already fetches the root run via get_run(run_id).
To support the empty-tree fallback (when the API returns a tree with zero descendants),
the route must pass additional context to the template:

```python
# Fields to embed as data-* attributes on the #execution-tree div:
# - run_id        (already passed)
# - run.name      (display name for root, from trace row)
# - run.status    (derived: "success" if end_time, "error" if error, else "unknown")
# - run.duration  (end_time - start_time in seconds, or 0)
# - run.cost      (from metadata_json total_cost_usd, or 0)
# - run.model     (from trace row model column, or "")
```

The template embeds these as data attributes so the JS can render a meaningful
fallback without a second API call:

```html
<div id="execution-tree"
     data-run-id="{{ run_id }}"
     data-run-name="{{ run.name or run_id[:8] }}"
     data-run-status="{{ run_status }}"
     data-run-duration="{{ run_duration }}"
     data-run-cost="{{ run_cost }}"
     data-run-model="{{ run.get('model', '') }}">
  <p class="empty-state">Loading execution tree...</p>
</div>
```

### 2.2 Client-Side Fetch

On DOMContentLoaded, execution-history.js:

1. Reads run_id from `#execution-tree[data-run-id]`.
2. Calls `fetch("/api/execution-tree/" + runId)`.
3. On success: if `tree` array is non-empty, calls `renderTree(tree)`.
   If `tree` is empty (root-only trace, no descendants), calls `renderEmptyState()`.
4. On fetch error (network, 4xx, 5xx): calls `renderErrorState(message)`.

### 2.3 API Response Shape (existing, no changes needed)

```typescript
// Documented for the JS consumer; the API is Python/JSON.
interface TreeApiResponse {
  run_id: string;
  tree: TreeNodeJson[];
}

interface TreeNodeJson {
  run_id: string;
  name: string;
  display_name: string;
  node_type: "graph_node" | "subgraph" | "agent" | "tool_call";
  status: "success" | "error" | "running" | "unknown";
  duration: number;      // seconds
  cost: number;          // USD
  model: string;
  token_count: number;
  inputs_json: string | null;
  outputs_json: string | null;
  metadata_json: string | null;
  children: TreeNodeJson[];
}
```

## 3. Component Structure (DOM Builder)

The JS uses a recursive DOM builder pattern (no virtual DOM, no framework).
Each tree node is rendered as a `<div class="tree-node">` containing:

```
<div class="tree-node" data-node-type="{node_type}" data-status="{status}">
  <div class="tree-node-header" role="button" tabindex="0"
       aria-expanded="true" aria-controls="children-{run_id}">
    <span class="tree-node-toggle">▼</span>
    <span class="tree-node-icon">{icon}</span>
    <span class="tree-node-name">{display_name}</span>
    <span class="badge badge-{status}">{status}</span>
    <span class="tree-node-meta">
      {duration} · {cost} · {token_count} tokens
    </span>
  </div>
  <div class="tree-node-children" id="children-{run_id}">
    <!-- recursive child nodes -->
  </div>
</div>
```

### 3.1 Node Type Icons

Map node_type to a text glyph (no icon library needed):

| node_type   | Icon | Rationale                |
|-------------|------|--------------------------|
| graph_node  | [G]  | Pipeline graph step      |
| subgraph    | [S]  | Nested subgraph          |
| agent       | [A]  | LLM/agent invocation     |
| tool_call   | [T]  | Tool call (Read, Bash..) |

Icons are rendered as `<span class="tree-node-icon tree-node-icon--{type}">`.
CSS gives each a distinct background color to visually differentiate.

### 3.2 Recursive Builder Function

```
function buildNodeElement(node):
    div = createElement("div", "tree-node")
    header = buildHeader(node)
    div.append(header)

    if node.children.length > 0:
        childrenContainer = createElement("div", "tree-node-children")
        childrenContainer.id = "children-" + node.run_id
        for child in node.children:
            childrenContainer.append(buildNodeElement(child))
        div.append(childrenContainer)

    return div
```

## 4. Collapse/Expand State Management

### 4.1 Toggle Mechanism

Each node header is clickable. Clicking toggles visibility of its
`.tree-node-children` div via a CSS class `.collapsed`:

```css
.tree-node-children.collapsed { display: none; }
```

The header's `aria-expanded` attribute is toggled between "true" and "false".
The toggle glyph changes between "▼" (expanded) and "▶" (collapsed).

### 4.2 State Storage

Collapse state is ephemeral (not persisted to localStorage). Rationale:
- Tree data changes between visits (new trace rows)
- The page is a drill-down from the completions table, not a persistent view
- Simplicity: no serialization/deserialization of expanded node sets

### 4.3 Default State

All top-level nodes start **expanded**. Children at depth >= 2 start **collapsed**.
This provides an overview of the main execution steps without overwhelming
the user with deeply nested tool calls.

### 4.4 Keyboard Accessibility

The header div has `role="button"` and `tabindex="0"`. Event listeners on both
`click` and `keydown` (Enter/Space) trigger the toggle. The `aria-expanded`
attribute ensures screen readers announce the expand/collapse state.

## 5. Empty-Tree Fallback

When the API returns `tree: []` (only a root trace exists, no descendant spans),
the JS renders a card using the data attributes from the template context:

```
<div class="detail-header">
  <div class="run-name">{data-run-name}</div>
  <div class="detail-meta">
    Status <span><badge>{data-run-status}</span>
  </div>
  <div class="detail-meta">
    Duration <span>{formatted data-run-duration}</span>
  </div>
  <div class="detail-meta">
    Cost <span>{formatted data-run-cost}</span>
  </div>
</div>
<p class="empty-state">
  No detailed trace data available for this run.
  Only the root execution record exists.
</p>
```

This reuses the existing `.detail-header` and `.detail-meta` CSS classes from
style.css, maintaining visual consistency with the rest of the UI.

## 6. CSS Class Conventions

All new CSS classes follow the existing codebase patterns:

| Class                         | Purpose                                           |
|-------------------------------|---------------------------------------------------|
| `.tree-node`                  | Container for a single tree node                  |
| `.tree-node-header`           | Clickable header row with name, badge, meta       |
| `.tree-node-toggle`           | Expand/collapse arrow glyph                       |
| `.tree-node-icon`             | Node type icon (styled per type via modifier)      |
| `.tree-node-icon--graph_node` | Green background for graph nodes                  |
| `.tree-node-icon--tool_call`  | Purple background for tool calls                  |
| `.tree-node-icon--agent`      | Blue background for agent/LLM calls               |
| `.tree-node-icon--subgraph`   | Orange background for subgraphs                   |
| `.tree-node-name`             | Display name text                                 |
| `.tree-node-meta`             | Duration/cost/tokens secondary info               |
| `.tree-node-children`         | Container for child nodes (indented)              |
| `.tree-node-children.collapsed` | Hidden state                                    |

Indentation is handled by nesting: each `.tree-node-children` adds a left
padding (e.g. 1.25rem), creating visual hierarchy through DOM structure
rather than computed indent levels.

Existing classes reused: `.badge`, `.badge-success`, `.badge-error`,
`.badge-unknown`, `.detail-header`, `.detail-meta`, `.empty-state`.

## 7. Loading and Error States

### 7.1 Loading

The template renders `<p class="empty-state">Loading execution tree...</p>`
inside the `#execution-tree` div. The JS replaces this entire div's innerHTML
with the rendered tree on success.

### 7.2 Error

On fetch failure, the JS replaces the loading message with:

```html
<p class="empty-state">
  Failed to load execution tree. {error detail}
</p>
```

No retry button (the user can refresh the page). Error messages include
the HTTP status code when available.

## 8. File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| execution_history.py | Modify | Compute and pass run_status, run_duration, run_cost to template |
| execution_history.html | Modify | Add data-* attributes, include JS via extra_head block |
| execution-history.js | Create | Fetch tree API, recursive DOM builder, collapse/expand, empty fallback |
| style.css | Modify | Add .tree-node-* CSS rules for tree rendering |

## 9. Design -> AC Traceability

| AC | How This Design Satisfies It |
|----|------------------------------|
| AC2 | JS fetches tree from API and renders it as DOM content; page shows real data not empty shell |
| AC3 | The existing trace link in completions.html navigates to /execution-history/{run_id}; this design renders the content on that page |
| AC4 | Recursive DOM builder creates nested collapsible tree showing full parent/child hierarchy |
| AC5 | JS renders trace data (name, status, duration, cost, tokens) fetched from the LangSmith-sourced API |
