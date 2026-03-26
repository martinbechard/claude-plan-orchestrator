// langgraph_pipeline/web/static/dashboard.js
// Dashboard SSE consumer — no external dependencies, no build step.
// Design: docs/plans/2026-03-25-15-pipeline-activity-dashboard-design.md

"use strict";

// ── Constants ──────────────────────────────────────────────────────────────────

const SSE_ENDPOINT = "/api/stream";
const RECONNECT_DELAY_MS = 3000;

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmtElapsed(seconds) {
  const s = Math.round(seconds);
  if (s < 60) return s + "s";
  const m = Math.floor(s / 60);
  const rem = s % 60;
  if (m < 60) return m + "m " + rem + "s";
  const h = Math.floor(m / 60);
  const remM = m % 60;
  return h + "h " + remM + "m";
}

function fmtCost(usd) {
  if (usd == null || usd === 0) return "$0.00";
  return "$" + usd.toFixed(4);
}

function fmtFinished(finishedAt) {
  const d = typeof finishedAt === "number" ? new Date(finishedAt * 1000) : new Date(finishedAt);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function itemTypeBadgeClass(itemType) {
  switch (itemType) {
    case "defect": return "item-type-defect";
    case "feature": return "item-type-feature";
    case "analysis": return "item-type-analysis";
    default: return "item-type-unknown";
  }
}

function outcomeBadgeClass(outcome) {
  switch (outcome) {
    case "success": return "outcome-success";
    case "warn": return "outcome-warn";
    case "fail": return "outcome-fail";
    default: return "badge-unknown";
  }
}

function stampTemplate(templateId) {
  const tpl = document.getElementById(templateId);
  return document.importNode(tpl.content, true);
}

// ── Render helpers ─────────────────────────────────────────────────────────────

function renderSessionSummary(data) {
  document.getElementById("stat-active").textContent = data.active_count ?? "—";
  document.getElementById("stat-queue").textContent = data.queue_count ?? "—";
  document.getElementById("stat-processed").textContent = data.total_processed ?? "—";
  document.getElementById("stat-cost").textContent = fmtCost(data.session_cost_usd);
  document.getElementById("stat-uptime").textContent = fmtElapsed(data.session_elapsed_s ?? 0);
}

function renderWorkers(workers) {
  const container = document.getElementById("workers-container");
  const empty = document.getElementById("workers-empty");

  if (!workers || workers.length === 0) {
    empty.style.display = "";
    // Remove all worker cards but leave the empty placeholder
    Array.from(container.querySelectorAll(".worker-card")).forEach(el => el.remove());
    return;
  }

  empty.style.display = "none";

  const fragment = document.createDocumentFragment();
  workers.forEach(function(w) {
    const clone = stampTemplate("tpl-worker-card");
    const card = clone.querySelector(".worker-card");
    card.setAttribute("aria-label", "Worker: " + w.slug);

    const slugEl = clone.querySelector(".worker-slug");
    slugEl.textContent = w.slug;

    const typeEl = clone.querySelector(".item-type-badge");
    typeEl.textContent = w.item_type;
    typeEl.classList.add(itemTypeBadgeClass(w.item_type));

    const elapsedEl = clone.querySelector(".worker-elapsed");
    elapsedEl.textContent = fmtElapsed(w.elapsed_s ?? 0);

    const pidEl = clone.querySelector(".worker-pid");
    pidEl.textContent = "PID " + w.pid;

    const traceLink = clone.querySelector(".trace-link");
    if (w.run_id) {
      traceLink.href = "/proxy?trace_id=" + encodeURIComponent(w.run_id);
      traceLink.style.display = "";
    } else {
      traceLink.style.display = "none";
    }

    fragment.appendChild(clone);
  });

  // Replace only the worker-card nodes, leave empty placeholder intact
  Array.from(container.querySelectorAll(".worker-card")).forEach(el => el.remove());
  container.appendChild(fragment);
}

function renderCompletions(completions) {
  const tbody = document.getElementById("completions-container");
  const emptyRow = document.getElementById("completions-empty");

  if (!completions || completions.length === 0) {
    emptyRow.style.display = "";
    Array.from(tbody.querySelectorAll("tr:not(#completions-empty)")).forEach(el => el.remove());
    return;
  }

  emptyRow.style.display = "none";

  const fragment = document.createDocumentFragment();
  completions.forEach(function(c) {
    const clone = stampTemplate("tpl-completion-row");

    clone.querySelector(".completion-slug").textContent = c.slug;

    const typeEl = clone.querySelector(".item-type-badge");
    typeEl.textContent = c.item_type;
    typeEl.classList.add(itemTypeBadgeClass(c.item_type));

    const outcomeEl = clone.querySelector(".outcome-badge");
    outcomeEl.textContent = c.outcome;
    outcomeEl.classList.add(outcomeBadgeClass(c.outcome));

    clone.querySelector(".completion-cost").textContent = fmtCost(c.cost_usd);
    clone.querySelector(".completion-duration").textContent = fmtElapsed(c.duration_s ?? 0);
    clone.querySelector(".completion-finished").textContent = fmtFinished(c.finished_at);

    const traceLink = clone.querySelector(".trace-link");
    if (c.run_id) {
      traceLink.href = "/proxy?trace_id=" + encodeURIComponent(c.run_id);
      traceLink.style.display = "";
    } else {
      traceLink.style.display = "none";
    }

    fragment.appendChild(clone);
  });

  Array.from(tbody.querySelectorAll("tr:not(#completions-empty)")).forEach(el => el.remove());
  tbody.appendChild(fragment);
}

function renderErrors(errors) {
  const container = document.getElementById("errors-container");
  const emptyEl = document.getElementById("errors-empty");
  const badge = document.getElementById("error-count-badge");

  if (!errors || errors.length === 0) {
    emptyEl.style.display = "";
    badge.textContent = "";
    badge.style.display = "none";
    Array.from(container.querySelectorAll(".error-row")).forEach(el => el.remove());
    return;
  }

  emptyEl.style.display = "none";
  badge.textContent = errors.length;
  badge.style.display = "";

  const fragment = document.createDocumentFragment();
  errors.forEach(function(msg) {
    const clone = stampTemplate("tpl-error-row");
    clone.querySelector(".error-row").textContent = msg;
    fragment.appendChild(clone);
  });

  Array.from(container.querySelectorAll(".error-row")).forEach(el => el.remove());
  container.appendChild(fragment);
}

// ── Main render ────────────────────────────────────────────────────────────────

function renderAll(data) {
  renderSessionSummary(data);
  renderWorkers(data.active_workers);
  renderCompletions(data.recent_completions);
  renderErrors(data.recent_errors);
}

// ── Connection status ──────────────────────────────────────────────────────────

function setConnectionStatus(connected) {
  const dot = document.getElementById("connection-dot");
  const label = document.getElementById("connection-label");
  if (connected) {
    dot.classList.add("connection-dot--live");
    dot.classList.remove("connection-dot--dead");
    dot.setAttribute("aria-label", "Connected");
    dot.setAttribute("title", "Connected — live updates active");
    if (label) label.textContent = "LIVE";
  } else {
    dot.classList.remove("connection-dot--live");
    dot.classList.add("connection-dot--dead");
    dot.setAttribute("aria-label", "Disconnected");
    dot.setAttribute("title", "Disconnected — attempting to reconnect");
    if (label) label.textContent = "OFFLINE";
    document.getElementById("stat-uptime").textContent = "N/A";
  }
}

// ── EventSource lifecycle ──────────────────────────────────────────────────────

function connect() {
  const es = new EventSource(SSE_ENDPOINT);

  es.addEventListener("state", function(evt) {
    setConnectionStatus(true);
    try {
      const data = JSON.parse(evt.data);
      renderAll(data);
    } catch (err) {
      console.error("dashboard: failed to parse SSE data", err);
    }
  });

  es.addEventListener("error", function() {
    setConnectionStatus(false);
    es.close();
    setTimeout(connect, RECONNECT_DELAY_MS);
  });
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function() {
  setConnectionStatus(false);
  connect();
});
