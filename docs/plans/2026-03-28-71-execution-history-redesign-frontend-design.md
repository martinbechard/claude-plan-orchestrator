# Frontend Implementation Design: Execution History UI Redesign

Design competition entry for task 0.3.
Parent design: docs/plans/2026-03-28-71-execution-history-redesign-design.md
Work item: tmp/plans/.claimed/71-execution-history-redesign.md

---

## 1. Design Philosophy

This design follows the existing codebase conventions:
- **Server-rendered Jinja2** with embedded CSS per template (no Tailwind, no CSS framework)
- **Vanilla JS** with no build step, no external dependencies
- **FastAPI routes** prepare full context dicts; templates receive ready-to-render data
- **Accessibility-first**: aria attributes, keyboard navigation, semantic HTML
- **Progressive disclosure**: tree collapsed by default, detail panel loads on click

The new execution history page replaces proxy_narrative.html and proxy_trace.html with
a single unified template that supports unlimited-depth tree navigation, a detail side
panel, and deep-dive prompt/response inspection.

---

## 2. Route and Data Flow

### 2.1 New Route: GET /execution/{run_id}

Replaces the separate /proxy/{run_id} and /proxy/{run_id}/narrative routes with a
single endpoint that serves the recursive tree view.

```
Request: GET /execution/{run_id}
Response: execution_history.html template
```

**Context dict prepared by the route:**

| Key | Type | Source |
|-----|------|--------|
| run | dict | get_run(run_id) enriched via _enrich_run() |
| tree | TreeNode | Full recursive tree from get_full_subtree() assembled into nested structure |
| display_name | str | Slug resolution chain (metadata -> child lookup -> run_id prefix) |
| worker_logs | list[str] | Log files matching item slug |

The route calls get_full_subtree(run_id) (D1) to fetch all descendants in a single
recursive CTE query. Python code assembles flat rows into a nested TreeNode dict:

```python
TreeNode = {
    "run_id": str,
    "parent_run_id": str | None,
    "name": str,
    "display_name": str,       # slug-resolved name
    "node_type": str,          # "graph" | "agent" | "tool" | "unknown"
    "status": str,             # "completed" | "running" | "error" | "stale"
    "start_time": str | None,
    "end_time": str | None,
    "duration_display": str,   # "2.34s" or "1m 23s"
    "cost_display": str,       # "$0.0123" or ""
    "model": str | None,
    "token_count": int | None,
    "depth": int,              # 0 = root, 1 = child, etc.
    "child_count": int,
    "children": list[TreeNode],
    "has_detail": bool,        # True if inputs/outputs/metadata present
}
```

### 2.2 Node Detail API: GET /execution/{run_id}/node/{node_run_id}

Returns JSON for the detail side panel. Loaded on-demand when a tree node is clicked.

```json
{
    "run_id": "abc-123",
    "name": "Read",
    "display_name": "Read: src/main.py",
    "node_type": "tool",
    "status": "completed",
    "duration_display": "0.12s",
    "cost_display": "$0.0012",
    "model": "claude-sonnet-4-6",
    "token_count": 1234,
    "metrics": {
        "latency_ms": 120,
        "tokens_in": 500,
        "tokens_out": 734,
        "cost_usd": 0.0012,
        "model": "claude-sonnet-4-6"
    },
    "content": {
        "type": "tool",
        "input": {"file_path": "src/main.py", "limit": 50},
        "output": "... file contents ..."
    },
    "observability": {
        "validator_verdict": "PASS",
        "exit_code": 0,
        "plan_state": {"task": "1.1", "status": "in_progress"}
    },
    "raw_json": {
        "inputs": { ... },
        "outputs": { ... },
        "metadata": { ... }
    }
}
```

This keeps the initial page load fast (only the tree structure) while deferring the
heavy payload (inputs/outputs JSON) to on-demand fetches.

### 2.3 Deep-Dive API: GET /execution/{run_id}/node/{node_run_id}/deep-dive

Returns JSON for the prompt/response deep-dive view. Only available for agent nodes.

```json
{
    "system_prompt": "You are a ...",
    "agent_response": "I will ...",
    "messages": [
        {"role": "system", "content": "..."},
        {"role": "assistant", "content": "..."}
    ],
    "metrics": {
        "latency_ms": 45000,
        "tokens_in": 12000,
        "tokens_out": 3400,
        "model": "claude-opus-4-6"
    }
}
```

### 2.4 Completions Page Update

The completions.html Trace column link changes from:
```html
<a href="/proxy?trace_id={{ row.run_id }}">Trace</a>
```
to:
```html
<a href="/execution/{{ row.run_id }}">Trace</a>
```

The standalone "Traces" nav link in base.html is removed.

---

## 3. Template Structure

### 3.1 execution_history.html (New Template)

Single Jinja2 template with three logical zones:

```
+-------------------------------------------------------+
| Header: item name, status badge, metrics summary      |
+---------------------------+---------------------------+
|  Tree Panel (left)        |  Detail Panel (right)     |
|  - Recursive tree nodes   |  - Node info              |
|  - Expand/collapse        |  - Metrics                |
|  - Node type icons        |  - Content (type-aware)   |
|  - Selected state         |  - Observability data     |
|                           |  - Raw JSON toggle        |
|                           |  - Deep-dive button       |
+---------------------------+---------------------------+
```

**Template block structure:**

```jinja2
{% extends "base.html" %}
{% block title %}{{ display_name }} -- Plan Orchestrator{% endblock %}
{% block extra_head %}<style>/* embedded CSS */</style>{% endblock %}
{% block content %}
  {# Header section #}
  {# Split-pane container #}
    {# Left: tree panel (server-rendered) #}
    {# Right: detail panel (JS-populated) #}
  {# Deep-dive overlay (hidden by default) #}
{% endblock %}
```

### 3.2 Tree Rendering Strategy: Server-Rendered Recursive HTML

The tree is rendered server-side using a Jinja2 recursive macro. This avoids a
separate JSON API call for initial tree load and ensures the page is usable
without JavaScript (progressive enhancement).

```jinja2
{% macro render_node(node, depth) %}
<div class="tree-node depth-{{ depth }}" data-run-id="{{ node.run_id }}"
     data-depth="{{ depth }}" role="treeitem"
     aria-expanded="false" tabindex="0">
  <div class="tree-node-row" onclick="selectNode(this)">
    {% if node.children %}
    <button class="tree-toggle" onclick="toggleNode(event, this)"
            aria-label="Expand {{ node.display_name }}">
      <span class="toggle-icon">&#9654;</span>
    </button>
    {% else %}
    <span class="tree-leaf-spacer"></span>
    {% endif %}
    <span class="node-icon node-icon-{{ node.node_type }}" aria-hidden="true">
      {{ node_icon(node.node_type) }}
    </span>
    <span class="node-name">{{ node.display_name }}</span>
    {% if node.duration_display %}
    <span class="node-metric node-duration">{{ node.duration_display }}</span>
    {% endif %}
    {% if node.cost_display %}
    <span class="node-metric node-cost">{{ node.cost_display }}</span>
    {% endif %}
    <span class="node-status badge badge-{{ node.status }}">{{ node.status }}</span>
  </div>
  {% if node.children %}
  <div class="tree-children" role="group" style="display:none;">
    {% for child in node.children %}
      {{ render_node(child, depth + 1) }}
    {% endfor %}
  </div>
  {% endif %}
</div>
{% endmacro %}
```

**Node type icons** (unicode, no icon library):

| node_type | Icon | Meaning |
|-----------|------|---------|
| graph | &#9678; (&#9678;) | Pipeline graph node |
| agent | &#9733; (&#9733;) | Agent / LLM invocation |
| tool | &#9881; (&#9881;) | Tool call (Read, Edit, Bash, etc.) |
| unknown | &#9679; (&#9679;) | Unclassified node |

**Depth indentation** via CSS:

```css
.tree-node { padding-left: calc(var(--depth) * 20px); }
```

Each .tree-node sets --depth via inline style or data attribute read by CSS:

```css
.depth-0 { --depth: 0; }
.depth-1 { --depth: 1; }
/* ... generated up to depth-10, then fallback calc for deeper */
.tree-node[data-depth] { padding-left: calc(attr(data-depth) * 20px); }
```

Since CSS attr() for numeric values is not widely supported, use a Jinja2 inline style:

```jinja2
<div class="tree-node" style="padding-left: {{ depth * 20 }}px;">
```

### 3.3 Detail Panel (Right Side)

The detail panel is a fixed-position sidebar that updates via JavaScript when a tree
node is clicked. It uses fetch() to call the node detail API and renders the response
into DOM elements.

**Panel sections:**

1. **Header**: Node name + status badge + node type label
2. **Metrics bar**: Latency, tokens, cost, model -- each shown only when data available (AC42)
3. **Content area** (varies by node_type):
   - **graph**: State inputs/outputs in collapsible JSON blocks (AC12)
   - **agent**: Prompt summary + response preview + "Deep-dive" button (AC13)
   - **tool**: Input parameters + result display (AC14)
4. **Observability section**: Structured display of (AC43-AC46):
   - Validator verdicts (keyed table)
   - Pipeline decisions
   - Subprocess exit codes
   - Plan state snapshots
5. **Raw JSON toggle**: Hidden by default (AC48), reveals full JSON on click (AC49),
   re-click hides (AC50)

**Panel rendering in JS:**

```javascript
async function loadNodeDetail(runId, nodeRunId) {
    const panel = document.getElementById("detail-panel");
    panel.classList.add("loading");

    const resp = await fetch("/execution/" + runId + "/node/" + nodeRunId);
    const data = await resp.json();

    renderDetailHeader(panel, data);
    renderMetrics(panel, data.metrics);
    renderContent(panel, data.content);
    renderObservability(panel, data.observability);
    renderRawToggle(panel, data.raw_json);

    panel.classList.remove("loading");
    panel.classList.add("visible");
}
```

Content rendering dispatches by node_type:

```javascript
function renderContent(panel, content) {
    const container = panel.querySelector(".detail-content");
    container.innerHTML = "";

    switch (content.type) {
        case "graph":
            renderGraphContent(container, content);
            break;
        case "agent":
            renderAgentContent(container, content);
            break;
        case "tool":
            renderToolContent(container, content);
            break;
    }
}
```

### 3.4 Deep-Dive Overlay

The deep-dive view is a full-screen overlay (modal) that shows system prompt and agent
response side-by-side (AC15). It is triggered by a "Deep-dive" button in the detail
panel for agent nodes.

**Layout:**

```
+-------------------------------------------------------+
| [X Close]  Agent Name          Latency | Tokens | Cost |
+---------------------------+---------------------------+
|  System Prompt (left)     |  Agent Response (right)   |
|  - Scrollable (AC16)      |  - Scrollable (AC16)      |
|  - Monospace pre block    |  - Monospace pre block     |
|  - Full text, no truncate |  - Full text, no truncate  |
+---------------------------+---------------------------+
```

**HTML structure:**

```html
<div id="deep-dive-overlay" class="deep-dive-overlay" style="display:none;"
     role="dialog" aria-modal="true" aria-label="Prompt/response inspection">
  <div class="deep-dive-header">
    <button class="deep-dive-close" onclick="closeDeepDive()"
            aria-label="Close deep-dive view">&times;</button>
    <span class="deep-dive-title"></span>
    <div class="deep-dive-metrics"></div>
  </div>
  <div class="deep-dive-body">
    <div class="deep-dive-panel deep-dive-prompt">
      <div class="deep-dive-panel-title">System Prompt</div>
      <pre class="deep-dive-content"></pre>
    </div>
    <div class="deep-dive-panel deep-dive-response">
      <div class="deep-dive-panel-title">Agent Response</div>
      <pre class="deep-dive-content"></pre>
    </div>
  </div>
</div>
```

Each panel is independently scrollable via overflow-y: auto (AC16). The overlay traps
focus for accessibility and closes on Escape key.

---

## 4. CSS Architecture

### 4.1 Embedded Style Block

Following the codebase convention (proxy_narrative.html has 250 lines of embedded CSS),
the execution_history.html template embeds all styles in an extra_head block. No
modifications to style.css are needed.

### 4.2 CSS Variables

Reuse the existing phase palette from proxy_narrative.html, plus new variables:

```css
:root {
    /* Existing phase palette */
    --phase-intake:     #6366f1;
    --phase-planning:   #0891b2;
    --phase-execution:  #d97706;
    --phase-validation: #059669;
    --phase-archival:   #64748b;
    --phase-unknown:    #9090b0;

    /* Tree colors */
    --tree-bg: #ffffff;
    --tree-hover: #f8fafc;
    --tree-selected: #eff6ff;
    --tree-guide: #e2e8f0;
    --tree-indent: 20px;

    /* Node type colors */
    --node-graph: #6366f1;
    --node-agent: #d97706;
    --node-tool: #0891b2;
    --node-unknown: #9090b0;

    /* Detail panel */
    --panel-width: 420px;
    --panel-bg: #ffffff;
    --panel-border: #e2e8f0;

    /* Deep-dive */
    --deep-dive-bg: #1a1a2e;
    --deep-dive-text: #e8e8f0;
    --deep-dive-panel-bg: #0f0f1a;
}
```

### 4.3 Split-Pane Layout

The main content area uses a CSS grid with two columns:

```css
.execution-layout {
    display: grid;
    grid-template-columns: 1fr var(--panel-width);
    gap: 0;
    min-height: calc(100vh - 120px);
    /* 120px = nav(48px) + header(~72px) */
}

/* Tree panel fills left column */
.tree-panel {
    overflow-y: auto;
    overflow-x: hidden;
    padding: 1rem;
    border-right: 1px solid var(--panel-border);
}

/* Detail panel fills right column, sticky */
.detail-panel {
    overflow-y: auto;
    padding: 1rem;
    background: var(--panel-bg);
    position: sticky;
    top: 0;
    max-height: calc(100vh - 48px);
}

/* When no node is selected, detail panel shows placeholder */
.detail-panel.empty {
    display: flex;
    align-items: center;
    justify-content: center;
    color: #9090b0;
}
```

### 4.4 Tree Node Styles

```css
.tree-node-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 4px 8px;
    border-radius: 4px;
    cursor: pointer;
    transition: background 0.1s;
}
.tree-node-row:hover { background: var(--tree-hover); }
.tree-node-row.selected { background: var(--tree-selected); }

.tree-toggle {
    background: none;
    border: none;
    cursor: pointer;
    padding: 2px;
    font-size: 10px;
    color: #6b7280;
    transition: transform 0.15s;
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
}
.tree-node[aria-expanded="true"] > .tree-node-row > .tree-toggle .toggle-icon {
    transform: rotate(90deg);
}

.tree-leaf-spacer { width: 20px; flex-shrink: 0; }

.node-icon {
    font-size: 14px;
    width: 20px;
    text-align: center;
    flex-shrink: 0;
}
.node-icon-graph { color: var(--node-graph); }
.node-icon-agent { color: var(--node-agent); }
.node-icon-tool  { color: var(--node-tool); }

.node-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 13px;
}

.node-metric {
    font-size: 11px;
    color: #6b7280;
    flex-shrink: 0;
    font-variant-numeric: tabular-nums;
}

/* Tree guide lines for visual hierarchy */
.tree-children {
    position: relative;
    margin-left: 10px;
    padding-left: 10px;
    border-left: 1px solid var(--tree-guide);
}
```

### 4.5 Deep-Dive Overlay Styles

```css
.deep-dive-overlay {
    position: fixed;
    inset: 0;
    z-index: 1000;
    background: var(--deep-dive-bg);
    color: var(--deep-dive-text);
    display: flex;
    flex-direction: column;
}

.deep-dive-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.75rem 1.5rem;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    flex-shrink: 0;
}

.deep-dive-close {
    background: none;
    border: none;
    color: var(--deep-dive-text);
    font-size: 24px;
    cursor: pointer;
    padding: 0 0.5rem;
}

.deep-dive-body {
    flex: 1;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1px;
    background: rgba(255,255,255,0.1);
    min-height: 0; /* enable flex children to shrink */
}

.deep-dive-panel {
    display: flex;
    flex-direction: column;
    background: var(--deep-dive-panel-bg);
    min-height: 0;
}

.deep-dive-panel-title {
    padding: 0.5rem 1rem;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #9090b0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    flex-shrink: 0;
}

.deep-dive-content {
    flex: 1;
    overflow-y: auto; /* AC16: independently scrollable */
    padding: 1rem;
    margin: 0;
    font-family: monospace;
    font-size: 12px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
}

.deep-dive-metrics {
    display: flex;
    gap: 1.5rem;
    margin-left: auto;
    font-size: 12px;
    color: #9090b0;
}
.deep-dive-metric-value { font-weight: 600; color: var(--deep-dive-text); }
```

---

## 5. JavaScript Architecture

### 5.1 File: execution_history.js (New)

A single vanilla JS file loaded by execution_history.html. Follows the patterns
established by dashboard.js and analysis.js:
- "use strict" at top
- Constants section with uppercase names
- Named functions (no anonymous arrow functions)
- DOMContentLoaded bootstrap at bottom
- Event delegation where possible
- aria attribute management for accessibility

### 5.2 Module Structure

```
execution_history.js
  |
  +-- Constants
  |     NODE_DETAIL_ENDPOINT, DEEP_DIVE_ENDPOINT, EXPAND_ALL_DEPTH
  |
  +-- State
  |     _selectedNodeId, _expandedNodes (Set), _detailCache (Map)
  |
  +-- Tree Navigation
  |     toggleNode(event, button)    -- expand/collapse a node
  |     selectNode(rowElement)       -- select node + load detail
  |     expandToDepth(depth)         -- bulk expand (e.g. first 2 levels)
  |     collapseAll()                -- bulk collapse
  |
  +-- Detail Panel
  |     loadNodeDetail(runId, nodeRunId) -- fetch + render detail
  |     renderDetailHeader(panel, data)
  |     renderMetrics(panel, metrics)
  |     renderContent(panel, content)
  |     renderGraphContent(container, content)
  |     renderAgentContent(container, content)
  |     renderToolContent(container, content)
  |     renderObservability(panel, observability)
  |     renderRawToggle(panel, rawJson)
  |
  +-- Deep-Dive
  |     openDeepDive(runId, nodeRunId) -- fetch + show overlay
  |     closeDeepDive()
  |     _trapFocus(overlay)
  |
  +-- Keyboard Navigation
  |     _handleTreeKeydown(event)    -- ArrowUp/Down/Left/Right/Enter/Space
  |
  +-- Bootstrap
        DOMContentLoaded -> wire event listeners, expand root level
```

### 5.3 Tree Interaction

**Expand/collapse:**

```javascript
function toggleNode(event, button) {
    event.stopPropagation();
    var node = button.closest(".tree-node");
    var children = node.querySelector(".tree-children");
    if (!children) return;

    var isExpanded = node.getAttribute("aria-expanded") === "true";
    node.setAttribute("aria-expanded", String(!isExpanded));
    children.style.display = isExpanded ? "none" : "block";
}
```

**Node selection:**

```javascript
var _selectedNodeId = null;

function selectNode(rowElement) {
    var node = rowElement.closest(".tree-node");
    var nodeRunId = node.getAttribute("data-run-id");

    // Deselect previous
    var prev = document.querySelector(".tree-node-row.selected");
    if (prev) prev.classList.remove("selected");

    // Select current
    rowElement.classList.add("selected");
    _selectedNodeId = nodeRunId;

    // Load detail
    var rootRunId = document.querySelector("[data-root-run-id]")
        .getAttribute("data-root-run-id");
    loadNodeDetail(rootRunId, nodeRunId);
}
```

**Keyboard navigation** follows WAI-ARIA TreeView pattern:
- ArrowDown: move to next visible node
- ArrowUp: move to previous visible node
- ArrowRight: expand current node (if collapsed) or move to first child
- ArrowLeft: collapse current node (if expanded) or move to parent
- Enter/Space: select current node (load detail)
- Home: move to first tree node
- End: move to last visible tree node

### 5.4 Detail Panel Loading

Uses fetch() with a simple in-memory cache to avoid redundant network requests for
previously-viewed nodes:

```javascript
var _detailCache = {};

async function loadNodeDetail(rootRunId, nodeRunId) {
    var panel = document.getElementById("detail-panel");

    // Check cache
    if (_detailCache[nodeRunId]) {
        _renderDetail(panel, _detailCache[nodeRunId]);
        return;
    }

    // Show loading spinner
    panel.innerHTML = '<div class="detail-loading">Loading...</div>';
    panel.classList.remove("empty");

    var resp = await fetch(
        NODE_DETAIL_ENDPOINT
            .replace("{run_id}", rootRunId)
            .replace("{node_run_id}", nodeRunId)
    );

    if (!resp.ok) {
        panel.innerHTML = '<div class="detail-error">Failed to load node detail.</div>';
        return;
    }

    var data = await resp.json();
    _detailCache[nodeRunId] = data;
    _renderDetail(panel, data);
}
```

### 5.5 Metrics Rendering (Conditional Display)

Metrics are only shown when data is available (AC42). Each metric is rendered
conditionally:

```javascript
function renderMetrics(panel, metrics) {
    var container = panel.querySelector(".detail-metrics");
    container.innerHTML = "";

    if (!metrics) return;

    var items = [];
    if (metrics.latency_ms != null) {
        items.push({label: "Latency", value: _formatDuration(metrics.latency_ms)});
    }
    if (metrics.tokens_in != null || metrics.tokens_out != null) {
        var tokenStr = (metrics.tokens_in || 0) + " in / " + (metrics.tokens_out || 0) + " out";
        items.push({label: "Tokens", value: tokenStr});
    }
    if (metrics.cost_usd != null) {
        items.push({label: "Cost", value: "$" + metrics.cost_usd.toFixed(4)});
    }
    if (metrics.model) {
        items.push({label: "Model", value: metrics.model});
    }

    items.forEach(function(item) {
        var el = document.createElement("div");
        el.className = "detail-metric";
        el.innerHTML = '<span class="detail-metric-label">' + item.label +
            '</span><span class="detail-metric-value">' +
            _escapeHtml(item.value) + '</span>';
        container.appendChild(el);
    });
}
```

### 5.6 Observability Metadata Rendering (AC43-AC47)

Structured display of observability data, not raw JSON:

```javascript
function renderObservability(panel, obs) {
    var container = panel.querySelector(".detail-observability");
    container.innerHTML = "";

    if (!obs || Object.keys(obs).length === 0) return;

    var title = document.createElement("div");
    title.className = "detail-section-title";
    title.textContent = "Observability";
    container.appendChild(title);

    // Validator verdict (AC43)
    if (obs.validator_verdict) {
        _appendKeyValue(container, "Validator", obs.validator_verdict);
    }
    // Pipeline decision (AC44)
    if (obs.pipeline_decision) {
        _appendKeyValue(container, "Decision", obs.pipeline_decision);
    }
    // Exit code (AC45)
    if (obs.exit_code != null) {
        _appendKeyValue(container, "Exit Code", String(obs.exit_code));
    }
    // Plan state (AC46)
    if (obs.plan_state) {
        _appendCollapsible(container, "Plan State", JSON.stringify(obs.plan_state, null, 2));
    }
}
```

### 5.7 Raw JSON Toggle (AC48-AC50)

Hidden by default, toggle reveals full raw JSON:

```javascript
function renderRawToggle(panel, rawJson) {
    var container = panel.querySelector(".detail-raw");
    container.innerHTML = "";

    if (!rawJson) return;

    var toggle = document.createElement("button");
    toggle.className = "raw-json-toggle";
    toggle.textContent = "Show raw trace data";
    toggle.setAttribute("aria-expanded", "false");

    var pre = document.createElement("pre");
    pre.className = "raw-json-content";
    pre.textContent = JSON.stringify(rawJson, null, 2);
    pre.style.display = "none";

    toggle.addEventListener("click", function() {
        var isVisible = pre.style.display !== "none";
        pre.style.display = isVisible ? "none" : "block";
        toggle.textContent = isVisible ? "Show raw trace data" : "Hide raw trace data";
        toggle.setAttribute("aria-expanded", String(!isVisible));
    });

    container.appendChild(toggle);
    container.appendChild(pre);
}
```

---

## 6. Completions Page Changes (D6)

### 6.1 completions.html Modifications

Minimal changes to the existing template:

1. **Trace link URL**: Change href from /proxy?trace_id={run_id} to /execution/{run_id}
2. **Remove target="_blank"**: Open in same tab for seamless navigation

```jinja2
{# Before #}
<a href="/proxy?trace_id={{ row.run_id | e }}" target="_blank" rel="noopener">Trace</a>

{# After #}
<a href="/execution/{{ row.run_id | e }}"
   aria-label="View execution history for {{ row.slug | e }}">Trace</a>
```

### 6.2 base.html Modifications

Remove the standalone "Traces" nav link (AC7):

```jinja2
{# Remove this block: #}
<a href="/proxy"
   {% if request.url.path.startswith('/proxy') %}class="active" aria-current="page"{% endif %}>
  Traces
</a>
```

The Completions nav link gains active state for /execution paths too:

```jinja2
<a href="/completions"
   {% if request.url.path == '/completions' or request.url.path.startswith('/execution') %}
     class="active" aria-current="page"
   {% endif %}>
  Completions
</a>
```

---

## 7. Node Type Classification

The route layer classifies each tree node by examining its run name and metadata:

| Pattern | node_type | Examples |
|---------|-----------|---------|
| Top-level children of root | graph | intake, plan_creation, execute_plan, validate |
| Has model field or metadata.model | agent | Claude CLI sessions |
| Name matches known tool names | tool | Read, Edit, Write, Bash, Grep, Glob, etc. |
| Nested under a tool call | tool | Sub-tool-calls within Skill invocations (AC22) |
| None of the above | unknown | Miscellaneous runs |

Known tool names (from _TOOL_VERB in trace_narrative.py):
Read, Edit, Write, Bash, Grep, Glob, TodoWrite, Agent, WebSearch, WebFetch,
Skill, NotebookEdit, LSP.

---

## 8. AC Traceability

| AC | Design Section | Implementation |
|----|----------------|----------------|
| AC6 | 6.1 | Completions Trace link navigates to /execution/{run_id} |
| AC7 | 6.2 | base.html removes standalone Traces nav link |
| AC8 | 6.1 | Every row with run_id displays Trace link |
| AC9 | 3.2, 5.3 | Tree nodes expandable/collapsible via toggleNode() |
| AC10 | 3.2 | Recursive macro renders full tree from pipeline to tool calls |
| AC11 | 3.2 | No depth limit -- Jinja2 macro recurses unlimited |
| AC12 | 3.3, 5.4 | Detail panel shows state inputs/outputs for graph nodes |
| AC13 | 3.3, 5.4 | Detail panel shows prompt/response for agent nodes |
| AC14 | 3.3, 5.4 | Detail panel shows input/result for tool nodes |
| AC15 | 3.4 | Deep-dive overlay with side-by-side panels |
| AC16 | 3.4, 4.5 | Each deep-dive panel has overflow-y: auto |
| AC17 | 3.4, 5.5 | Deep-dive header shows latency, tokens, cost metrics |
| AC38 | 5.5 | Latency displayed when timing data available |
| AC39 | 5.5 | Token count displayed when token data available |
| AC40 | 5.5 | Cost displayed when cost data available |
| AC41 | 5.5 | Model name displayed when model data available |
| AC42 | 5.5 | Missing metrics omitted via conditional rendering |
| AC43 | 5.6 | Validator verdicts in structured key-value format |
| AC44 | 5.6 | Pipeline decisions displayed as key-value |
| AC45 | 5.6 | Subprocess exit codes displayed as key-value |
| AC46 | 5.6 | Plan state displayed in collapsible block |
| AC47 | 5.6 | All observability data in structured form |
| AC48 | 5.7 | Raw JSON toggle button hidden by default |
| AC49 | 5.7 | Toggle reveals full JSON in pre block |
| AC50 | 5.7 | Toggle can re-hide (bidirectional) |

---

## 9. File Inventory

| Action | File | Lines (est.) | Purpose |
|--------|------|-------------|---------|
| New | langgraph_pipeline/web/templates/execution_history.html | ~200 | Recursive tree + split-pane + deep-dive overlay |
| New | langgraph_pipeline/web/static/execution_history.js | ~350 | Tree interaction, detail loading, deep-dive, keyboard nav |
| Edit | langgraph_pipeline/web/templates/completions.html | ~2 lines | Change Trace link href |
| Edit | langgraph_pipeline/web/templates/base.html | ~5 lines | Remove Traces nav, update Completions active state |
| New | langgraph_pipeline/web/routes/execution.py | ~180 | New route: tree endpoint + node detail API + deep-dive API |

No changes to style.css (all CSS embedded in template). No changes to proxy.py
(backend design decisions D1-D5 are handled by tasks 1.1-3.1). No new dependencies.

---

## 10. Performance Considerations

1. **Single query for tree**: get_full_subtree() fetches entire tree in one recursive CTE,
   avoiding N+1 queries. Tree is rendered server-side in the initial HTML response.

2. **Lazy detail loading**: Node details (inputs/outputs/metadata JSON) are fetched
   on-demand when clicked, keeping the initial page load fast even for trees with
   hundreds of nodes.

3. **Client-side cache**: _detailCache avoids redundant fetch calls when re-selecting
   previously viewed nodes.

4. **Jinja2 recursion limit**: For extremely deep trees (>100 levels), Jinja2's default
   recursion limit may need bumping. In practice, pipeline trees rarely exceed 6-8
   levels. The route should set jinja2 Environment recursion_limit to 200 as a safety
   measure.

5. **DOM efficiency**: Tree nodes are rendered as flat divs with padding-based indentation
   rather than nested ul/li, keeping the DOM structure shallow even for deep trees.
   Actually, the HTML is nested (tree-children contains tree-nodes) to enable CSS
   guide-line borders, but the visual depth is controlled by padding, not additional
   wrapper elements.
