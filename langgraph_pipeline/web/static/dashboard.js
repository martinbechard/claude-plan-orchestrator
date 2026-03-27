// langgraph_pipeline/web/static/dashboard.js
// Dashboard SSE consumer — no external dependencies, no build step.
// Design: docs/plans/2026-03-25-15-pipeline-activity-dashboard-design.md

"use strict";

// ── Constants ──────────────────────────────────────────────────────────────────

const SSE_ENDPOINT = "/api/stream";
const RECONNECT_DELAY_MS = 3000;
const LS_VIEW_KEY = "dashboard.workers.view";
const LS_WINDOW_MS_KEY = "dashboard.timeline.windowMs";
const LS_COLOR_MODE_KEY = "dashboard.timeline.colorMode";
const VIEW_TABLE = "table";
const VIEW_TIMELINE = "timeline";
const COLOR_MODE_TYPE = "type";
const COLOR_MODE_VELOCITY = "velocity";
const DEFAULT_WINDOW_MS = 10 * 60 * 1000;
const MIN_WINDOW_MS = 60 * 1000;
const AXIS_TICK_COUNT = 5;
const MS_PER_MINUTE = 60 * 1000;
const MS_PER_HOUR = 60 * MS_PER_MINUTE;
const HALF_WINDOW_DIVISOR = 2;
const ZOOM_FACTOR = 2;
const FLASH_DURATION_MS = 1500;
const VEL_LOW_THRESHOLD = 500;
const VEL_MED_THRESHOLD = 2000;
const VEL_HIGH_THRESHOLD = 5000;
const VEL_COLOR_NONE   = [144, 144, 176]; // grey #9090b0
const VEL_COLOR_LOW    = [ 37,  99, 235]; // blue #2563eb
const VEL_COLOR_MED    = [ 22, 163,  74]; // green #16a34a
const VEL_COLOR_HIGH   = [234, 179,   8]; // yellow #eab308
const VEL_COLOR_MAX    = [220,  38,  38]; // red #dc2626

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

/** Parses finished_at which may be an ISO string or a Unix timestamp (seconds). */
function finishedAtToMs(finishedAt) {
  if (typeof finishedAt === "number") return finishedAt * 1000;
  return new Date(finishedAt).getTime();
}

function fmtFinished(finishedAt) {
  const d = new Date(finishedAtToMs(finishedAt));
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** Formats an epoch-ms timestamp as HH:MM (24-hour local time). */
function fmtTimeHHMM(epochMs) {
  const d = new Date(epochMs);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return hh + ":" + mm;
}

/** Formats a window duration in ms as a human-readable string like "10m" or "2h". */
function fmtWindowDuration(ms) {
  if (ms < MS_PER_HOUR) return Math.round(ms / MS_PER_MINUTE) + "m";
  const h = Math.floor(ms / MS_PER_HOUR);
  const rem = Math.round((ms % MS_PER_HOUR) / MS_PER_MINUTE);
  return rem > 0 ? h + "h " + rem + "m" : h + "h";
}

function fmtVelocity(tpm) {
  if (!tpm || tpm === 0) return "\u2014";
  if (tpm >= 1000) return (tpm / 1000).toFixed(1) + "k tok/min";
  return Math.round(tpm) + " tok/min";
}

function fmtVelocityCompact(tpm) {
  if (!tpm || tpm === 0) return "\u2014";
  if (tpm >= 1000) return (tpm / 1000).toFixed(1) + "k/m";
  return Math.round(tpm) + "/m";
}

function lerpColor(c1, c2, t) {
  return [
    Math.round(c1[0] + (c2[0] - c1[0]) * t),
    Math.round(c1[1] + (c2[1] - c1[1]) * t),
    Math.round(c1[2] + (c2[2] - c1[2]) * t)
  ];
}

function velocityColor(tpm) {
  if (!tpm || tpm <= 0) {
    return "rgb(" + VEL_COLOR_NONE.join(",") + ")";
  }
  var rgb;
  if (tpm < VEL_LOW_THRESHOLD) {
    var t = tpm / VEL_LOW_THRESHOLD;
    rgb = lerpColor(VEL_COLOR_NONE, VEL_COLOR_LOW, t);
  } else if (tpm < VEL_MED_THRESHOLD) {
    var t = (tpm - VEL_LOW_THRESHOLD) / (VEL_MED_THRESHOLD - VEL_LOW_THRESHOLD);
    rgb = lerpColor(VEL_COLOR_LOW, VEL_COLOR_MED, t);
  } else if (tpm < VEL_HIGH_THRESHOLD) {
    var t = (tpm - VEL_MED_THRESHOLD) / (VEL_HIGH_THRESHOLD - VEL_MED_THRESHOLD);
    rgb = lerpColor(VEL_COLOR_MED, VEL_COLOR_HIGH, t);
  } else {
    var t = Math.min(1, (tpm - VEL_HIGH_THRESHOLD) / VEL_HIGH_THRESHOLD);
    rgb = lerpColor(VEL_COLOR_HIGH, VEL_COLOR_MAX, t);
  }
  return "rgb(" + rgb.join(",") + ")";
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
var latestWorkers = [];
var latestCompletions = [];
var colorMode = COLOR_MODE_TYPE;
var prevActiveSlugSet = new Set();

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

function getStoredColorMode() {
  try {
    var v = localStorage.getItem(LS_COLOR_MODE_KEY);
    return v === COLOR_MODE_VELOCITY ? COLOR_MODE_VELOCITY : COLOR_MODE_TYPE;
  } catch (_) {
    return COLOR_MODE_TYPE;
  }
}

function setStoredColorMode(mode) {
  try { localStorage.setItem(LS_COLOR_MODE_KEY, mode); } catch (_) { /* noop */ }
}

// ── Timeline window state ─────────────────────────────────────────────────────

var timelineWindowMs = DEFAULT_WINDOW_MS;
var timelineWindowStart = 0;
var timelineWindowEnd = 0;
var timelineLiveMode = true;

function getStoredWindowMs() {
  try {
    var raw = localStorage.getItem(LS_WINDOW_MS_KEY);
    if (raw) {
      var parsed = parseInt(raw, 10);
      if (!isNaN(parsed) && parsed >= MIN_WINDOW_MS) return parsed;
    }
  } catch (_) { /* noop */ }
  return DEFAULT_WINDOW_MS;
}

function setStoredWindowMs(ms) {
  try { localStorage.setItem(LS_WINDOW_MS_KEY, String(ms)); } catch (_) { /* noop */ }
}

function snapWindowToLive() {
  timelineWindowEnd = Date.now();
  timelineWindowStart = timelineWindowEnd - timelineWindowMs;
  timelineLiveMode = true;
  updateLiveButtonState();
}

function updateLiveButtonState() {
  var btn = document.getElementById("tl-btn-live");
  if (!btn) return;
  if (timelineLiveMode) {
    btn.classList.add("timeline-nav-btn--live-active");
    btn.setAttribute("aria-pressed", "true");
  } else {
    btn.classList.remove("timeline-nav-btn--live-active");
    btn.setAttribute("aria-pressed", "false");
  }
}

function updateWindowLabel() {
  var label = document.getElementById("timeline-window-label");
  if (!label) return;
  var startStr = fmtTimeHHMM(timelineWindowStart);
  var endStr = fmtTimeHHMM(timelineWindowEnd);
  var durStr = fmtWindowDuration(timelineWindowMs);
  label.textContent = startStr + " \u2014 " + endStr + " (" + durStr + ")";
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

function outcomeBarBorderClass(outcome) {
  switch (outcome) {
    case "success": return "timeline-bar-border--success";
    case "warn": return "timeline-bar-border--warn";
    case "fail": return "timeline-bar-border--fail";
    default: return "timeline-bar-border--success";
  }
}


function updateColorModeButton() {
  var btn = document.getElementById("tl-btn-color-mode");
  if (!btn) return;
  if (colorMode === COLOR_MODE_VELOCITY) {
    btn.textContent = "Type";
    btn.setAttribute("aria-pressed", "true");
    btn.setAttribute("title", "Switch to type colour mode");
  } else {
    btn.textContent = "Velocity";
    btn.setAttribute("aria-pressed", "false");
    btn.setAttribute("title", "Switch to velocity colour mode");
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

// ── Timeline axis ─────────────────────────────────────────────────────────────

function renderTimelineAxis() {
  var axis = document.getElementById("timeline-axis");
  axis.innerHTML = "";

  for (var i = 0; i <= AXIS_TICK_COUNT; i++) {
    var pct = (i / AXIS_TICK_COUNT) * 100;
    var epochMs = timelineWindowStart + (pct / 100) * timelineWindowMs;

    var tick = document.createElement("span");
    tick.className = "timeline-axis-tick";
    tick.style.left = pct + "%";
    tick.textContent = fmtTimeHHMM(epochMs);
    axis.appendChild(tick);
  }
}

// ── Timeline bar positioning ─────────────────────────────────────────────────

/**
 * Computes left% and width% for a bar given its start/end in epoch ms.
 * Clamps both edges to the visible window.
 * Returns null if the bar is completely outside the window.
 */
function computeBarPosition(barStartMs, barEndMs) {
  if (barEndMs <= timelineWindowStart || barStartMs >= timelineWindowEnd) return null;

  var clampedStart = Math.max(barStartMs, timelineWindowStart);
  var clampedEnd = Math.min(barEndMs, timelineWindowEnd);

  var leftPct = ((clampedStart - timelineWindowStart) / timelineWindowMs) * 100;
  var widthPct = ((clampedEnd - clampedStart) / timelineWindowMs) * 100;

  return { leftPct: Math.max(0, leftPct), widthPct: Math.max(0, widthPct) };
}

/**
 * Creates and appends a single timeline row for a bar entry.
 * barEntry: { slug, itemType, barStartMs, barEndMs, isCompletion, outcome, tokensPerMinute }
 */
function buildTimelineRow(barEntry) {
  var pos = computeBarPosition(barEntry.barStartMs, barEntry.barEndMs);
  if (!pos) return null;

  var clone = stampTemplate("tpl-timeline-row");
  var row = clone.querySelector(".timeline-row");
  row.setAttribute("data-slug", barEntry.slug);
  if (barEntry.isCompletion) row.classList.add("timeline-row--completion");

  var label = clone.querySelector(".timeline-label");
  var labelLink = document.createElement("a");
  labelLink.href = "/item/" + encodeURIComponent(barEntry.slug);
  labelLink.textContent = barEntry.slug;
  label.appendChild(labelLink);

  var track = clone.querySelector(".timeline-bar-track");
  addGridlines(track);

  var bar = clone.querySelector(".timeline-bar");
  bar.style.left = pos.leftPct + "%";
  bar.style.width = pos.widthPct + "%";

  if (colorMode === COLOR_MODE_VELOCITY) {
    bar.style.backgroundColor = velocityColor(barEntry.tokensPerMinute || 0);
  } else {
    bar.classList.add(timelineBarClass(barEntry.itemType));
  }

  if (barEntry.isCompletion) {
    bar.classList.add("timeline-bar--completion");
    bar.classList.add(outcomeBarBorderClass(barEntry.outcome));
  }

  var elapsedS = Math.round((barEntry.barEndMs - barEntry.barStartMs) / 1000);
  var velStr = fmtVelocity(barEntry.tokensPerMinute || 0);
  var velCompact = fmtVelocityCompact(barEntry.tokensPerMinute || 0);
  var barLabelText = colorMode === COLOR_MODE_VELOCITY ? velCompact : fmtElapsed(elapsedS);
  var barLabel = document.createElement("span");
  barLabel.className = "timeline-bar-label";
  barLabel.textContent = barLabelText;
  bar.appendChild(barLabel);

  // Full-detail tooltip always shows slug, elapsed, type, and velocity
  var tooltipParts = [barEntry.slug, fmtElapsed(elapsedS), barEntry.itemType];
  if (velStr !== "\u2014") tooltipParts.push(velStr);
  bar.title = tooltipParts.join(" \u2022 ");

  // Live elapsed clock on the right (active workers only)
  var elapsedClock = clone.querySelector(".timeline-elapsed-clock");
  if (elapsedClock) {
    if (!barEntry.isCompletion) {
      elapsedClock.textContent = fmtElapsed(elapsedS);
    }
  }

  return clone;
}

/** Adds faint vertical gridlines to the bar track at each axis tick position. */
function addGridlines(track) {
  for (var i = 1; i < AXIS_TICK_COUNT; i++) {
    var pct = (i / AXIS_TICK_COUNT) * 100;
    var line = document.createElement("div");
    line.className = "timeline-gridline";
    line.style.left = pct + "%";
    track.appendChild(line);
  }
}

// ── Completion flash ──────────────────────────────────────────────────────────

/**
 * Compares current active workers against the previous set to detect newly-completed
 * workers, then triggers a flash animation row for each one.
 */
function detectAndFlashCompletions(workers, completions) {
  var newActiveSet = new Set((workers || []).map(function(w) { return w.slug; }));

  prevActiveSlugSet.forEach(function(slug) {
    if (!newActiveSet.has(slug)) {
      var completion = (completions || []).find(function(c) { return c.slug === slug; });
      if (completion) {
        addFlashRow(slug, completion);
      }
    }
  });

  prevActiveSlugSet = newActiveSet;
}

/** Adds a transient flash row to the flash container for a just-completed worker. */
function addFlashRow(slug, completion) {
  var flashContainer = document.getElementById("timeline-flash-container");
  if (!flashContainer) return;

  // Remove existing flash row for same slug to avoid duplicates
  flashContainer.querySelectorAll(".timeline-row").forEach(function(el) {
    if (el.getAttribute("data-slug") === slug) el.remove();
  });

  var barEndMs = finishedAtToMs(completion.finished_at);
  var barStartMs = barEndMs - ((completion.duration_s || 0) * 1000);

  var pos = computeBarPosition(barStartMs, barEndMs);
  if (!pos) {
    // Worker finished outside current window — show a minimal bar at the right edge
    var durPct = Math.min(15, ((completion.duration_s || 30) / (timelineWindowMs / 1000)) * 100);
    pos = { leftPct: Math.max(0, 100 - durPct), widthPct: Math.max(1, durPct) };
  }

  var clone = stampTemplate("tpl-timeline-row");
  var row = clone.querySelector(".timeline-row");
  row.setAttribute("data-slug", slug);

  clone.querySelector(".timeline-label").textContent = slug;

  var bar = clone.querySelector(".timeline-bar");
  bar.style.left = pos.leftPct + "%";
  bar.style.width = pos.widthPct + "%";

  var flashClass;
  if (completion.outcome === "success") flashClass = "timeline-bar--flash-success";
  else if (completion.outcome === "warn") flashClass = "timeline-bar--flash-warn";
  else flashClass = "timeline-bar--flash-fail";
  bar.classList.add(flashClass);

  var elapsedClock = clone.querySelector(".timeline-elapsed-clock");
  if (elapsedClock) elapsedClock.style.visibility = "hidden";

  flashContainer.appendChild(clone);

  setTimeout(function() {
    flashContainer.querySelectorAll(".timeline-row").forEach(function(el) {
      if (el.getAttribute("data-slug") === slug) el.remove();
    });
  }, FLASH_DURATION_MS + 200);
}

// ── Timeline view ─────────────────────────────────────────────────────────────

function renderTimeline(workers, completions) {
  var rowsEl = document.getElementById("timeline-rows");
  rowsEl.innerHTML = "";

  renderTimelineAxis();
  updateWindowLabel();

  var now = Date.now();

  // Build active worker entries sorted by elapsed_s descending
  var activeEntries = (workers || []).map(function(w) {
    var barEndMs = now;
    var barStartMs = now - ((w.elapsed_s || 0) * 1000);
    return {
      slug: w.slug,
      itemType: w.item_type,
      barStartMs: barStartMs,
      barEndMs: barEndMs,
      isCompletion: false,
      outcome: null,
      tokensPerMinute: w.tokens_per_minute || 0,
      sortKey: w.elapsed_s || 0
    };
  }).sort(function(a, b) { return b.sortKey - a.sortKey; });

  // Build completion entries sorted by finished_at descending, excluding those before window
  var completionEntries = (completions || []).filter(function(c) {
    var endMs = finishedAtToMs(c.finished_at);
    return endMs >= timelineWindowStart;
  }).map(function(c) {
    var barEndMs = finishedAtToMs(c.finished_at);
    var barStartMs = barEndMs - ((c.duration_s || 0) * 1000);
    return {
      slug: c.slug,
      itemType: c.item_type,
      barStartMs: barStartMs,
      barEndMs: barEndMs,
      isCompletion: true,
      outcome: c.outcome,
      tokensPerMinute: c.tokens_per_minute || 0,
      sortKey: barEndMs
    };
  }).sort(function(a, b) { return b.sortKey - a.sortKey; });

  var allEntries = activeEntries.concat(completionEntries);

  var fragment = document.createDocumentFragment();
  allEntries.forEach(function(entry) {
    var rowClone = buildTimelineRow(entry);
    if (rowClone) fragment.appendChild(rowClone);
  });

  rowsEl.appendChild(fragment);
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
  var completions = data.recent_completions || [];

  // Detect newly-completed workers before overwriting latestWorkers
  detectAndFlashCompletions(workers, completions);

  latestWorkers = workers;
  latestCompletions = completions;

  // Update timeline window if in live mode
  if (timelineLiveMode) {
    timelineWindowEnd = Date.now();
    timelineWindowStart = timelineWindowEnd - timelineWindowMs;
  }

  renderSessionSummary(data);
  renderWorkers(workers);
  renderTimeline(workers, latestCompletions);
  applyView(currentView);
  renderCompletions(latestCompletions);
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

// ── Timeline toolbar wiring ────────────────────────────────────────────────────

function wireTimelineToolbar() {
  document.getElementById("tl-btn-prev").addEventListener("click", function() {
    var shift = timelineWindowMs / HALF_WINDOW_DIVISOR;
    timelineWindowStart -= shift;
    timelineWindowEnd -= shift;
    timelineLiveMode = false;
    updateLiveButtonState();
    renderTimeline(latestWorkers, latestCompletions);
    updateWindowLabel();
  });

  document.getElementById("tl-btn-next").addEventListener("click", function() {
    var shift = timelineWindowMs / HALF_WINDOW_DIVISOR;
    timelineWindowStart += shift;
    timelineWindowEnd += shift;
    // Re-enable live mode if the right edge is now at or past now
    if (timelineWindowEnd >= Date.now()) {
      snapWindowToLive();
    }
    renderTimeline(latestWorkers, latestCompletions);
    updateWindowLabel();
  });

  document.getElementById("tl-btn-zoom-out").addEventListener("click", function() {
    var center = (timelineWindowStart + timelineWindowEnd) / 2;
    timelineWindowMs = Math.min(timelineWindowMs * ZOOM_FACTOR, 24 * MS_PER_HOUR);
    setStoredWindowMs(timelineWindowMs);
    timelineWindowStart = center - timelineWindowMs / 2;
    timelineWindowEnd = center + timelineWindowMs / 2;
    renderTimeline(latestWorkers, latestCompletions);
    updateWindowLabel();
  });

  document.getElementById("tl-btn-zoom-in").addEventListener("click", function() {
    var center = (timelineWindowStart + timelineWindowEnd) / 2;
    timelineWindowMs = Math.max(timelineWindowMs / ZOOM_FACTOR, MIN_WINDOW_MS);
    setStoredWindowMs(timelineWindowMs);
    timelineWindowStart = center - timelineWindowMs / 2;
    timelineWindowEnd = center + timelineWindowMs / 2;
    renderTimeline(latestWorkers, latestCompletions);
    updateWindowLabel();
  });

  document.getElementById("tl-btn-live").addEventListener("click", function() {
    snapWindowToLive();
    renderTimeline(latestWorkers, latestCompletions);
    updateWindowLabel();
  });

  document.getElementById("tl-btn-color-mode").addEventListener("click", function() {
    colorMode = colorMode === COLOR_MODE_VELOCITY ? COLOR_MODE_TYPE : COLOR_MODE_VELOCITY;
    setStoredColorMode(colorMode);
    updateColorModeButton();
    renderTimeline(latestWorkers, latestCompletions);
  });
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function() {
  setConnectionStatus(false);

  currentView = getStoredView();
  colorMode = getStoredColorMode();
  timelineWindowMs = getStoredWindowMs();
  snapWindowToLive();
  applyView(currentView);
  updateColorModeButton();

  var toggleBtn = document.getElementById("workers-view-toggle");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", function() {
      var next = currentView === VIEW_TABLE ? VIEW_TIMELINE : VIEW_TABLE;
      applyView(next);
    });
  }

  wireTimelineToolbar();
  connect();
});
