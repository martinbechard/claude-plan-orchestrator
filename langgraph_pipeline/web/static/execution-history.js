// langgraph_pipeline/web/static/execution-history.js
// Client-side tree fetch and render for /execution-history/{run_id}.
// Design: docs/plans/2026-04-02-83-trace-links-empty-or-missing-design.md (D4)

"use strict";

// ── Constants ──────────────────────────────────────────────────────────────────

var API_PREFIX = "/api/execution-tree/";
var INDENT_PX_PER_LEVEL = 20;
var CHEVRON_RIGHT = "\u25B6";
var CHEVRON_DOWN = "\u25BC";
var DEFAULT_COLLAPSE_DEPTH = 2;
var SECONDS_PER_MINUTE = 60;
var SECONDS_PER_HOUR = 3600;
var COST_DECIMAL_PLACES = 4;
var TOKENS_K_THRESHOLD = 1000;
var SKELETON_LINE_COUNT = 6;

var NODE_TYPE_LABELS = {
    graph_node: "Graph",
    subgraph: "Subgraph",
    agent: "Agent",
    tool_call: "Tool"
};

// ── Formatting Helpers ─────────────────────────────────────────────────────────

function fmtDuration(seconds) {
    var s = Math.round(seconds);
    if (s < SECONDS_PER_MINUTE) return s + "s";
    var m = Math.floor(s / SECONDS_PER_MINUTE);
    var rem = s % SECONDS_PER_MINUTE;
    if (m < SECONDS_PER_MINUTE) return m + "m " + rem + "s";
    var h = Math.floor(m / SECONDS_PER_MINUTE);
    return h + "h " + (m % SECONDS_PER_MINUTE) + "m";
}

function fmtCost(usd) {
    if (usd == null || usd === 0) return "";
    return "$" + usd.toFixed(COST_DECIMAL_PLACES);
}

function fmtTokens(count) {
    if (!count) return "";
    if (count >= TOKENS_K_THRESHOLD) return (count / TOKENS_K_THRESHOLD).toFixed(1) + "k tok";
    return count + " tok";
}

function makeMetric(className, text) {
    var span = document.createElement("span");
    span.className = className;
    span.textContent = text;
    return span;
}

// ── Toggle Handler ─────────────────────────────────────────────────────────────

function makeToggleHandler(toggleBtn, nodeId) {
    return function () {
        var childrenEl = document.getElementById(nodeId + "-children");
        if (!childrenEl) return;

        var isExpanded = toggleBtn.getAttribute("aria-expanded") === "true";
        toggleBtn.setAttribute("aria-expanded", String(!isExpanded));
        toggleBtn.textContent = isExpanded ? CHEVRON_RIGHT : CHEVRON_DOWN;
        childrenEl.hidden = isExpanded;
    };
}

// ── Recursive DOM Builder ──────────────────────────────────────────────────────

function buildNodeEl(node, depth) {
    var li = document.createElement("li");
    li.className = "exec-node";
    li.setAttribute("role", "treeitem");
    li.style.paddingLeft = (depth * INDENT_PX_PER_LEVEL) + "px";

    var hasChildren = node.children && node.children.length > 0;
    var nodeId = "exec-node-" + node.run_id;

    // -- Header row --
    var header = document.createElement("div");
    header.className = "exec-node-header";

    if (hasChildren) {
        var startExpanded = depth < DEFAULT_COLLAPSE_DEPTH;
        var toggle = document.createElement("button");
        toggle.className = "exec-toggle";
        toggle.type = "button";
        toggle.setAttribute("aria-expanded", String(startExpanded));
        toggle.setAttribute("aria-controls", nodeId + "-children");
        toggle.setAttribute("aria-label", "Toggle " + node.display_name);
        toggle.textContent = startExpanded ? CHEVRON_DOWN : CHEVRON_RIGHT;
        toggle.addEventListener("click", makeToggleHandler(toggle, nodeId));
        header.appendChild(toggle);
    } else {
        var spacer = document.createElement("span");
        spacer.className = "exec-toggle-spacer";
        header.appendChild(spacer);
    }

    // Node type badge
    var typeBadge = document.createElement("span");
    typeBadge.className = "exec-type exec-type-" + node.node_type;
    typeBadge.textContent = NODE_TYPE_LABELS[node.node_type] || node.node_type;
    header.appendChild(typeBadge);

    // Display name
    var name = document.createElement("span");
    name.className = "exec-name";
    name.textContent = node.display_name;
    header.appendChild(name);

    // Status badge
    var statusBadge = document.createElement("span");
    statusBadge.className = "badge badge-" + node.status;
    statusBadge.textContent = node.status;
    header.appendChild(statusBadge);

    // Metrics (only if nonzero)
    if (node.duration > 0) {
        header.appendChild(makeMetric("exec-duration", fmtDuration(node.duration)));
    }
    if (node.cost > 0) {
        header.appendChild(makeMetric("exec-cost", fmtCost(node.cost)));
    }
    if (node.token_count > 0) {
        header.appendChild(makeMetric("exec-tokens", fmtTokens(node.token_count)));
    }
    if (node.model) {
        header.appendChild(makeMetric("exec-model", node.model));
    }

    li.appendChild(header);

    // -- Children container --
    if (hasChildren) {
        var startExpanded2 = depth < DEFAULT_COLLAPSE_DEPTH;
        var childrenUl = document.createElement("ul");
        childrenUl.id = nodeId + "-children";
        childrenUl.className = "exec-children";
        childrenUl.setAttribute("role", "group");
        childrenUl.hidden = !startExpanded2;
        for (var j = 0; j < node.children.length; j++) {
            childrenUl.appendChild(buildNodeEl(node.children[j], depth + 1));
        }
        li.appendChild(childrenUl);
    }

    return li;
}

// ── Tree Renderer ──────────────────────────────────────────────────────────────

function renderTree(container, nodes) {
    var list = document.createElement("ul");
    list.className = "exec-tree";
    list.setAttribute("role", "tree");
    for (var i = 0; i < nodes.length; i++) {
        list.appendChild(buildNodeEl(nodes[i], 0));
    }
    container.appendChild(list);
}

// ── Toolbar: Expand All / Collapse All ─────────────────────────────────────────

function createToolbar(container) {
    var toolbar = document.createElement("div");
    toolbar.className = "exec-toolbar";
    toolbar.setAttribute("role", "toolbar");
    toolbar.setAttribute("aria-label", "Tree controls");

    var expandBtn = document.createElement("button");
    expandBtn.className = "exec-toolbar-btn";
    expandBtn.type = "button";
    expandBtn.textContent = "Expand All";
    expandBtn.addEventListener("click", function () {
        setAllExpanded(container, true);
    });

    var collapseBtn = document.createElement("button");
    collapseBtn.className = "exec-toolbar-btn";
    collapseBtn.type = "button";
    collapseBtn.textContent = "Collapse All";
    collapseBtn.addEventListener("click", function () {
        setAllExpanded(container, false);
    });

    toolbar.appendChild(expandBtn);
    toolbar.appendChild(collapseBtn);
    return toolbar;
}

function setAllExpanded(container, expand) {
    var toggles = container.querySelectorAll(".exec-toggle");
    for (var i = 0; i < toggles.length; i++) {
        var btn = toggles[i];
        var childId = btn.getAttribute("aria-controls");
        var childEl = childId ? document.getElementById(childId) : null;
        if (!childEl) continue;

        btn.setAttribute("aria-expanded", String(expand));
        btn.textContent = expand ? CHEVRON_DOWN : CHEVRON_RIGHT;
        childEl.hidden = !expand;
    }
}

// ── Empty-Tree Fallback ────────────────────────────────────────────────────────

function renderEmptyTree(container) {
    var runName = container.dataset.runName || "Unknown";
    var runStatus = container.dataset.runStatus || "unknown";
    var startTime = container.dataset.runStart || "";
    var endTime = container.dataset.runEnd || "";

    var wrapper = document.createElement("div");
    wrapper.className = "exec-empty";

    var icon = document.createElement("div");
    icon.className = "icon";
    icon.textContent = "\uD83D\uDD0D";
    wrapper.appendChild(icon);

    var heading = document.createElement("div");
    heading.innerHTML = "<strong>Run: " + escapeHtml(runName) + "</strong>";
    wrapper.appendChild(heading);

    var statusEl = document.createElement("p");
    var badge = document.createElement("span");
    badge.className = "badge badge-" + runStatus;
    badge.textContent = runStatus;
    statusEl.appendChild(document.createTextNode("Status: "));
    statusEl.appendChild(badge);
    wrapper.appendChild(statusEl);

    if (startTime) {
        var timeEl = document.createElement("p");
        timeEl.className = "exec-empty-meta";
        var duration = "";
        if (endTime && startTime) {
            var secs = (new Date(endTime) - new Date(startTime)) / 1000;
            if (secs > 0) duration = " (" + fmtDuration(secs) + ")";
        }
        timeEl.textContent = "Started: " + new Date(startTime).toLocaleString() + duration;
        wrapper.appendChild(timeEl);
    }

    var note = document.createElement("div");
    note.textContent = "No detailed trace data available for this run. " +
        "This may be a synthetic trace created for a completion that ran " +
        "without LangSmith tracing enabled.";
    wrapper.appendChild(note);

    container.appendChild(wrapper);
}

function escapeHtml(str) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

// ── Error Handler ──────────────────────────────────────────────────────────────

function renderError(container, message) {
    container.innerHTML = "";
    var errDiv = document.createElement("div");
    errDiv.className = "exec-error";
    errDiv.setAttribute("role", "alert");

    var iconEl = document.createElement("span");
    iconEl.className = "exec-error-icon";
    iconEl.textContent = "!";
    iconEl.setAttribute("aria-hidden", "true");
    errDiv.appendChild(iconEl);

    var text = document.createElement("span");
    text.textContent = "Failed to load execution tree: " + message;
    errDiv.appendChild(text);

    container.appendChild(errDiv);
}

// ── Skeleton Loading ───────────────────────────────────────────────────────────

function renderSkeleton(container) {
    var wrapper = document.createElement("div");
    wrapper.className = "exec-skeleton";
    wrapper.setAttribute("role", "status");
    wrapper.setAttribute("aria-live", "polite");
    wrapper.setAttribute("aria-label", "Loading execution tree");

    for (var i = 0; i < SKELETON_LINE_COUNT; i++) {
        var line = document.createElement("div");
        line.className = "exec-skeleton-line";
        line.style.width = (70 + Math.random() * 30) + "%";
        line.style.marginLeft = (i % 3) * INDENT_PX_PER_LEVEL + "px";
        wrapper.appendChild(line);
    }

    container.innerHTML = "";
    container.appendChild(wrapper);
}

// ── Fetch and Render ───────────────────────────────────────────────────────────

function fetchAndRender(container, runId) {
    renderSkeleton(container);

    fetch(API_PREFIX + encodeURIComponent(runId))
        .then(function (response) {
            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }
            return response.json();
        })
        .then(function (data) {
            container.innerHTML = "";
            if (!data.tree || data.tree.length === 0) {
                renderEmptyTree(container);
            } else {
                container.appendChild(createToolbar(container));
                renderTree(container, data.tree);
            }
        })
        .catch(function (err) {
            renderError(container, err.message);
        });
}

// ── Entry Point ────────────────────────────────────────────────────────────────

(function () {
    var container = document.getElementById("execution-tree");
    if (!container) return;

    var runId = container.dataset.runId;
    if (!runId) return;

    fetchAndRender(container, runId);
}());
