// langgraph_pipeline/web/static/dashboard.js
// Dashboard SSE consumer — no external dependencies, no build step.
// Design: docs/plans/2026-03-25-15-pipeline-activity-dashboard-design.md

"use strict";

// ── Constants ──────────────────────────────────────────────────────────────────

const SSE_ENDPOINT = "/api/stream";
const RECONNECT_DELAY_MS = 3000;
const LS_VIEW_KEY = "dashboard.workers.view";
const VIEW_TABLE = "table";
const VIEW_TIMELINE = "timeline";
const AXIS_TICK_PERCENTS = [0, 25, 50, 75, 100];
const FLASH_DURATION_MS = 1200;

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

// ── View state ────────────────────────────────────────────────────────────────

var currentView = VIEW_TABLE;
var previousWorkerSlugs = new Set();
var latestCompletions = [];

function getStoredView() {
  try {
    var v = localStorage.getItem(LS_VIEW_KEY);
    return v === VIEW_TIMELINE ? VIEW_TIMELINE : VIEW_TABLE;
  } catch (_) {
    return VIEW_TABLE;
  }
}

function setStoredView(view) {
  try { localStorage.setItem(LS_VIEW_KEY, view); } catch (_) { /* noop */ }
}

// ── Timeline bar colour ──────────────────────────────────────────────────────

function timelineBarClass(itemType) {
  switch (itemType) {
    case "defect": return "timeline-bar--defect";
    case "feature": return "timeline-bar--feature";
    case "analysis": return "timeline-bar--analysis";
    default: return "";
  }
}

function flashClass(outcome) {
  switch (outcome) {
    case "success": return "timeline-bar--flash-success";
    case "warn": return "timeline-bar--flash-warn";
    case "fail": return "timeline-bar--flash-fail";
    default: return "timeline-bar--flash-success";
  }
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
    const slugLink = document.createElement("a");
    slugLink.href = "/item/" + encodeURIComponent(w.slug);
    slugLink.textContent = w.slug;
    slugEl.appendChild(slugLink);

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

    const completionSlugEl = clone.querySelector(".completion-slug");
    const completionSlugLink = document.createElement("a");
    completionSlugLink.href = "/item/" + encodeURIComponent(c.slug);
    completionSlugLink.textContent = c.slug;
    completionSlugEl.appendChild(completionSlugLink);

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

// ── Timeline view ─────────────────────────────────────────────────────────────

function renderTimelineAxis(maxElapsed) {
  var axis = document.getElementById("timeline-axis");
  axis.innerHTML = "";
  AXIS_TICK_PERCENTS.forEach(function(pct) {
    var span = document.createElement("span");
    span.className = "timeline-axis-tick";
    span.style.left = pct + "%";
    var secs = Math.round((pct / 100) * maxElapsed);
    span.textContent = fmtElapsed(secs);
    axis.appendChild(span);
  });
}

function renderTimeline(workers) {
  var container = document.getElementById("timeline-container");
  var rowsEl = document.getElementById("timeline-rows");

  if (!workers || workers.length === 0) {
    rowsEl.innerHTML = "";
    document.getElementById("timeline-axis").innerHTML = "";
    return;
  }

  var maxElapsed = 0;
  workers.forEach(function(w) {
    if ((w.elapsed_s || 0) > maxElapsed) maxElapsed = w.elapsed_s;
  });
  if (maxElapsed === 0) maxElapsed = 1;

  renderTimelineAxis(maxElapsed);

  var fragment = document.createDocumentFragment();
  workers.forEach(function(w) {
    var clone = stampTemplate("tpl-timeline-row");
    var row = clone.querySelector(".timeline-row");
    row.setAttribute("data-slug", w.slug);

    var label = clone.querySelector(".timeline-label");
    var labelLink = document.createElement("a");
    labelLink.href = "/item/" + encodeURIComponent(w.slug);
    labelLink.textContent = w.slug;
    label.appendChild(labelLink);

    var bar = clone.querySelector(".timeline-bar");
    var pct = Math.min(100, ((w.elapsed_s || 0) / maxElapsed) * 100);
    bar.style.width = pct + "%";
    bar.classList.add(timelineBarClass(w.item_type));

    clone.querySelector(".timeline-elapsed").textContent = fmtElapsed(w.elapsed_s || 0);

    fragment.appendChild(clone);
  });

  rowsEl.innerHTML = "";
  rowsEl.appendChild(fragment);
}

// ── Completion flash ──────────────────────────────────────────────────────────

function findCompletionOutcome(slug, completions) {
  if (!completions) return null;
  for (var i = 0; i < completions.length; i++) {
    if (completions[i].slug === slug) return completions[i].outcome;
  }
  return null;
}

function showCompletionFlash(departedSlugs, completions) {
  departedSlugs.forEach(function(slug) {
    var outcome = findCompletionOutcome(slug, completions);
    var cls = flashClass(outcome);

    if (currentView === VIEW_TIMELINE) {
      var rowsEl = document.getElementById("timeline-rows");
      var clone = stampTemplate("tpl-timeline-row");
      var row = clone.querySelector(".timeline-row");
      row.setAttribute("data-slug", slug);
      clone.querySelector(".timeline-label").textContent = slug;
      var bar = clone.querySelector(".timeline-bar");
      bar.className = "timeline-bar " + cls;
      bar.style.width = "100%";
      clone.querySelector(".timeline-elapsed").textContent = "done";
      rowsEl.appendChild(clone);
    } else {
      var container = document.getElementById("workers-container");
      var cards = container.querySelectorAll(".worker-card");
      cards.forEach(function(card) {
        if (card.getAttribute("aria-label") === "Worker: " + slug) {
          card.style.transition = "opacity 1.2s ease";
          card.style.opacity = "0";
        }
      });
    }

    setTimeout(function() {
      if (currentView === VIEW_TIMELINE) {
        var rowsEl = document.getElementById("timeline-rows");
        rowsEl.querySelectorAll(".timeline-row").forEach(function(row) {
          if (row.getAttribute("data-slug") === slug) row.remove();
        });
      } else {
        var container = document.getElementById("workers-container");
        container.querySelectorAll(".worker-card").forEach(function(card) {
          if (card.getAttribute("aria-label") === "Worker: " + slug) card.remove();
        });
      }
    }, FLASH_DURATION_MS);
  });
}

// ── Toggle logic ──────────────────────────────────────────────────────────────

function applyView(view) {
  currentView = view;
  setStoredView(view);

  var workersContainer = document.getElementById("workers-container");
  var timelineContainer = document.getElementById("timeline-container");
  var btn = document.getElementById("workers-view-toggle");

  if (view === VIEW_TIMELINE) {
    workersContainer.style.display = "none";
    timelineContainer.hidden = false;
    btn.textContent = "Table";
    btn.setAttribute("aria-pressed", "true");
    btn.setAttribute("title", "Switch to table view");
  } else {
    workersContainer.style.display = "";
    timelineContainer.hidden = true;
    btn.textContent = "Timeline";
    btn.setAttribute("aria-pressed", "false");
    btn.setAttribute("title", "Switch to timeline view");
  }
}

// ── Main render ────────────────────────────────────────────────────────────────

function renderAll(data) {
  var workers = data.active_workers || [];
  latestCompletions = data.recent_completions || [];

  var currentSlugs = new Set();
  workers.forEach(function(w) { currentSlugs.add(w.slug); });

  var departed = [];
  previousWorkerSlugs.forEach(function(slug) {
    if (!currentSlugs.has(slug)) departed.push(slug);
  });

  renderSessionSummary(data);
  renderWorkers(workers);
  renderTimeline(workers);
  applyView(currentView);
  renderCompletions(latestCompletions);
  renderErrors(data.recent_errors);

  if (departed.length > 0) {
    showCompletionFlash(departed, latestCompletions);
  }

  previousWorkerSlugs = currentSlugs;
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

  currentView = getStoredView();
  applyView(currentView);

  var toggleBtn = document.getElementById("workers-view-toggle");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", function() {
      var next = currentView === VIEW_TABLE ? VIEW_TIMELINE : VIEW_TABLE;
      applyView(next);
    });
  }

  connect();
});
