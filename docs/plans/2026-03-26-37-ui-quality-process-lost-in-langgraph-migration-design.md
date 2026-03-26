---
title: "Defect 37: UI Quality Process Lost in LangGraph Migration"
date: 2026-03-26
type: design
---

# UI Quality Process — Design Document

## Problem

The old pipeline included a UI design competition process (Phase 0) where multiple
designs were generated in parallel and judged before implementation. This was not
migrated when the LangGraph pipeline replaced the old system. As a result, web UI
pages were built without design review, producing inconsistent and amateurish
styling across dashboard, cost analysis, traces, completions, queue, and item
detail pages.

## Scope

Three acceptance criteria drive this work item:

1. A documented UI design review process exists in the planner or coder agent prompts.
2. The planner agent mandates the frontend-design skill for UI work items.
3. A style guide or reference page exists to enforce consistency.

Additionally, specific UI regressions must be addressed across all pages.

## Architecture

### Phase 1 — Process Documentation

**Files to modify:**
- `.claude/agents/planner.md` — Add a UI work item detection section that
  instructs the planner to invoke the `frontend-design` skill before creating
  implementation tasks for any work item that touches web UI templates or CSS.
- `.claude/agents/frontend-coder.md` — Add reference to the style guide and
  require it to be read before making any UI change.

**Files to create:**
- `docs/ui-style-guide.md` — Canonical style guide covering typography, spacing,
  color palette, pagination component, empty states, table conventions, and
  card layouts. Serves as the "reference page" acceptance criterion.

### Phase 2 — UI Fixes

Apply the style guide to the existing pages, fixing the specific issues listed
in the work item:

- **Pagination**: left padding, consistent button sizing, readable text, active
  page highlight. Patch `langgraph_pipeline/web/static/style.css` and all
  templates that render pagination controls.
- **Empty states**: standardize to a single component pattern (icon + heading +
  sub-text) across queue, completions, traces, and dashboard.
- **Table styling**: consistent `th`/`td` padding, left-align text columns,
  right-align numeric columns.
- **Cost display tildes**: scan all templates for `~$` and replace with `$`.
- **Navigation active state**: apply a stronger visual treatment to the active
  nav link in `base.html`.

### Phase 3 — Release

Bump `plugin.json` version (patch) and add RELEASE-NOTES.md entry.

## Design Decisions

- Style guide lives in `docs/` as a Markdown file so it is readable by agents
  and humans without running the app.
- Agent prompt updates use clear trigger language ("if the work item touches
  any file under `langgraph_pipeline/web/`") to avoid ambiguity.
- UI fixes in Phase 2 are grouped by concern (pagination, empty states, tables,
  misc) to allow targeted validation.

## Key Files

| File | Action |
|------|--------|
| `.claude/agents/planner.md` | Add UI design review section |
| `.claude/agents/frontend-coder.md` | Reference style guide |
| `docs/ui-style-guide.md` | Create style guide |
| `langgraph_pipeline/web/static/style.css` | Fix shared CSS |
| `langgraph_pipeline/web/templates/base.html` | Nav active state |
| `langgraph_pipeline/web/templates/dashboard.html` | Empty state, table |
| `langgraph_pipeline/web/templates/queue.html` | Pagination, empty state |
| `langgraph_pipeline/web/templates/completions.html` | Pagination, empty state, table |
| `langgraph_pipeline/web/templates/analysis.html` | Cost tilde, table |
| `langgraph_pipeline/web/templates/proxy_list.html` | Pagination, table |
| `langgraph_pipeline/web/templates/item.html` | Timeline, table |
| `plugin.json` / `RELEASE-NOTES.md` | Version bump |
