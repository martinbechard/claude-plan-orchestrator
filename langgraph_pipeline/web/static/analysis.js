// langgraph_pipeline/web/static/analysis.js
// Client-side expand/collapse and column sort for the cost analysis page.
// Design: docs/plans/2026-03-25-16-tool-call-timing-and-cost-analysis-ui-design.md

"use strict";

// ── Constants ──────────────────────────────────────────────────────────────────

const ITEM_COST_TABLE_ID = "item-cost-table";
const SORT_DIR_ASCENDING = "asc";
const SORT_DIR_DESCENDING = "desc";

// Track sort direction per column
const _sortState = {};

// ── Row toggle ─────────────────────────────────────────────────────────────────

/**
 * Show or hide the task-detail <tr> with the given id.
 * Also updates the expand button's aria-expanded attribute and arrow glyph.
 *
 * @param {string} rowId - The id attribute of the detail <tr> to toggle.
 */
function toggleRow(rowId) {
  const detailRow = document.getElementById(rowId);
  if (!detailRow) return;

  const isExpanded = detailRow.classList.contains("expanded");
  detailRow.classList.toggle("expanded", !isExpanded);

  const btn = document.querySelector("[aria-controls='" + rowId + "']");
  if (btn) {
    btn.setAttribute("aria-expanded", String(!isExpanded));
    btn.innerHTML = isExpanded ? "&#9654;" : "&#9660;";
  }
}

// ── Table sort ─────────────────────────────────────────────────────────────────

/**
 * Sort the per-item cost table by the given column, toggling asc/desc on
 * each call. Task-detail rows travel with their parent item rows.
 *
 * @param {string} col - The data-sortable column name (e.g. "cost_usd").
 */
function sortTable(col) {
  const table = document.getElementById(ITEM_COST_TABLE_ID);
  if (!table) return;

  const tbody = table.querySelector("tbody");
  if (!tbody) return;

  const currentDir = _sortState[col] || SORT_DIR_DESCENDING;
  const nextDir = currentDir === SORT_DIR_ASCENDING ? SORT_DIR_DESCENDING : SORT_DIR_ASCENDING;
  _sortState[col] = nextDir;

  // Collect [item-row, detail-row|null] pairs so detail rows travel together
  const allRows = Array.from(tbody.rows);
  const pairs = [];
  let i = 0;
  while (i < allRows.length) {
    const row = allRows[i];
    if (row.classList.contains("item-row")) {
      const next = allRows[i + 1];
      const detailRow = (next && next.classList.contains("task-detail-row")) ? next : null;
      pairs.push([row, detailRow]);
      i += detailRow ? 2 : 1;
    } else {
      i++;
    }
  }

  // data-sortable uses underscores; row data-* attributes use hyphens
  const dataAttr = "data-" + col.replace(/_/g, "-");

  pairs.sort(function(pairA, pairB) {
    const aVal = pairA[0].getAttribute(dataAttr) || "";
    const bVal = pairB[0].getAttribute(dataAttr) || "";

    const aNum = parseFloat(aVal);
    const bNum = parseFloat(bVal);
    const cmp = (!isNaN(aNum) && !isNaN(bNum))
      ? aNum - bNum
      : aVal.localeCompare(bVal);

    return nextDir === SORT_DIR_ASCENDING ? cmp : -cmp;
  });

  pairs.forEach(function(pair) {
    tbody.appendChild(pair[0]);
    if (pair[1]) tbody.appendChild(pair[1]);
  });

  _updateSortIndicators(table, col, nextDir);
}

// ── Internal helpers ───────────────────────────────────────────────────────────

function _updateSortIndicators(table, activeCol, dir) {
  table.querySelectorAll("th[data-sortable]").forEach(function(th) {
    const indicator = th.querySelector(".sort-indicator");
    if (!indicator) return;
    indicator.textContent = (th.getAttribute("data-sortable") === activeCol)
      ? (dir === SORT_DIR_ASCENDING ? " \u25b2" : " \u25bc")
      : " \u21c5";
  });
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function() {
  const table = document.getElementById(ITEM_COST_TABLE_ID);
  if (!table) return;

  // Expand/collapse via event delegation on the table body
  table.addEventListener("click", function(evt) {
    const btn = evt.target.closest(".expand-btn");
    if (!btn) return;
    const rowId = btn.getAttribute("aria-controls");
    if (rowId) toggleRow(rowId);
  });

  // Wire sortable column headers
  table.querySelectorAll("th[data-sortable]").forEach(function(th) {
    const indicator = document.createElement("span");
    indicator.className = "sort-indicator";
    indicator.setAttribute("aria-hidden", "true");
    indicator.textContent = " \u21c5";
    th.appendChild(indicator);

    th.style.cursor = "pointer";
    th.setAttribute("role", "button");
    th.setAttribute("tabindex", "0");
    th.setAttribute("title", "Click to sort");

    const col = th.getAttribute("data-sortable");
    th.addEventListener("click", function() { sortTable(col); });
    th.addEventListener("keydown", function(evt) {
      if (evt.key === "Enter" || evt.key === " ") {
        evt.preventDefault();
        sortTable(col);
      }
    });
  });
});
