# Design: 74 Item Page Step Explorer

Source: tmp/plans/.claimed/74-item-page-step-explorer.md
Requirements: docs/plans/2026-03-31-74-item-page-step-explorer-requirements.md

## Architecture Overview

The item detail page is restructured from a flat two-column layout into a
stage-based step explorer. A server-side data model groups all work item
artifacts under six ordered pipeline stages (Intake, Requirements, Planning,
Execution, Verification, Archive). Each stage carries its own status and
completion timestamp, and each artifact carries a created/modified timestamp.

The Jinja2 template renders a vertical accordion of collapsible stage sections.
Artifact content is not embedded at page load; instead, stage expansion triggers
AJAX fetches to the existing artifact-content endpoint, keeping the initial
page load lightweight.

The existing /item/{slug}/dynamic polling endpoint is extended to return
stage-level status so the accordion updates live while a worker is active.

### Technology stack

- Backend: Python/FastAPI (existing)
- Templates: Jinja2 (existing)
- Frontend: vanilla JS (existing, no framework)
- Styling: embedded CSS in item.html (existing pattern)

### Key files to create or modify

| File | Action |
|---|---|
| langgraph_pipeline/web/routes/item.py | Modify: add stage data model, build_stages(), status matrix, extend /dynamic |
| langgraph_pipeline/web/templates/item.html | Modify: replace two-column layout with step explorer accordion |

---

## Design Decisions

### D1: Stage-based artifact grouping data model

Addresses: P1, FR1, FR2
Satisfies: AC1, AC2, AC9, AC10, AC11, AC13, AC15, AC16, AC17, AC18, AC19, AC20, AC21

Approach: Define a StageInfo TypedDict and an ArtifactInfo TypedDict in item.py.
A build_stages() function maps existing artifact discovery results into six
ordered StageInfo dicts. The Verification stage is omitted when the item type
is "feature" (no verification for features, per AC20).

ArtifactInfo fields: name (display label), path (for lazy fetch), timestamp
(file mtime epoch), timestamp_display (pre-formatted string).

StageInfo fields: id (lowercase key), name (display label), status (three-state),
artifacts (list of ArtifactInfo), completion_ts (formatted), completion_epoch (raw).

The six stages and their artifact mappings:

1. Intake: User Request (raw backlog file), Clause Register, 5 Whys Analysis
2. Requirements: Structured Requirements document
3. Planning: Design Document, YAML Plan
4. Execution: per-task log files, validation JSON files
5. Verification: final verification report (defects only)
6. Archive: completion record from completed backlog dirs

STAGE_ORDER constant enforces chronological pipeline ordering (AC10) and
is the single source of truth for stage identity and display names.

Files: langgraph_pipeline/web/routes/item.py

### D2: Stage status computation

Addresses: FR1
Satisfies: AC11

Approach: Each stage's status is one of: "not_started", "in_progress", "done".
A _compute_stage_statuses() function uses the item's pipeline_stage (from
_derive_pipeline_stage()) and a lookup matrix mapping 9 pipeline states
(queued, unknown, claimed, designing, planning, executing, validating,
completed, stuck) to expected status per stage index.

A "done*" adjustment: stages marked done that have no artifacts are downgraded
to in_progress. The "stuck" state uses artifact-based fallback to show
progress up to the point of failure.

Files: langgraph_pipeline/web/routes/item.py

### D3: Timestamps on stages and artifacts

Addresses: P3
Satisfies: AC3, AC12, AC13, AC14

Approach: Each artifact's timestamp is its file modification time (st_mtime),
formatted as "YYYY-MM-DD HH:MM" (local time) server-side. Each stage's
completion timestamp is the latest mtime among its artifacts, shown only when
status is "done". Server-side formatting avoids client-side date logic.

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D4: Collapsible stage accordion with persistence

Addresses: P4, UC1
Satisfies: AC2, AC4, AC6, AC7, AC8

Approach: Each stage renders as a section with a clickable button header that
toggles body visibility. CSS class "collapsed" hides the body. JavaScript
manages toggle and persists open/closed state in localStorage keyed by
slug + stage id.

The most recent active stage defaults to expanded on first visit; all others
default to collapsed. Subsequent visits restore persisted state.

Stage headers use button elements with aria-expanded and aria-controls for
accessibility. Keyboard navigation supported natively via button semantics.

Files: langgraph_pipeline/web/templates/item.html

### D5: On-demand artifact loading

Addresses: P5, FR3
Satisfies: AC5, AC22, AC23, AC24

Approach: At page load, the template renders only stage headers and artifact
metadata (name, timestamp) but not artifact content. When a user expands a
stage, JavaScript fetches each artifact's content via the existing
/item/{slug}/artifact-content?path={path} endpoint. Fetched content is cached
via a data-loaded DOM attribute; re-expanding does not re-fetch.

The /dynamic endpoint is extended to include a stages array with status,
timestamps, and artifact_count so live polling can detect new artifacts and
clear the cache. Polling does NOT fetch content -- only stage metadata.

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D6: Rename Raw Input to User Request

Addresses: FR4
Satisfies: AC25, AC26

Approach: The artifact display name for the original backlog file is "User
Request" in build_stages(). The label "Raw Input" is removed from all template
text. The underlying file path and data key remain unchanged.

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

---

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | Artifacts grouped under parent pipeline stage via StageInfo.artifacts |
| AC2 | D1, D4 | Visual hierarchy via stage headers + indented artifacts + accordion |
| AC3 | D3 | Timestamps on stage headers (completion_ts) and artifacts (timestamp_display) |
| AC4 | D4 | Collapsible accordion sections with CSS "collapsed" class |
| AC5 | D5 | On-demand loading; no artifact content at page load |
| AC6 | D4 | Click button header toggles collapsed class off |
| AC7 | D4 | Click expanded header toggles collapsed class on |
| AC8 | D4 | Collapsed state hides stage body containing all nested artifacts |
| AC9 | D1 | STAGE_ORDER constant defines the six stages; build_stages() returns ordered list |
| AC10 | D1 | STAGE_ORDER is in chronological pipeline order |
| AC11 | D1, D2 | Stage header renders name from StageInfo.name and status badge from StageInfo.status |
| AC12 | D3 | Stage header shows completion_ts when status is done |
| AC13 | D1, D3 | Artifacts nested under stages; each ArtifactInfo has timestamp_display |
| AC14 | D3 | ArtifactInfo.timestamp_display from file st_mtime |
| AC15 | D1 | Intake stage discovers: User Request, Clause Register, 5 Whys Analysis |
| AC16 | D1 | Requirements stage discovers: Structured Requirements document |
| AC17 | D1 | Planning stage discovers: Design Document, YAML Plan |
| AC18 | D1 | Execution stage discovers: log files, validation JSON files |
| AC19 | D1 | Verification stage discovers: verification-report.md |
| AC20 | D1 | Verification stage omitted entirely when item_type == "feature" |
| AC21 | D1 | Archive stage discovers: completion record from COMPLETED_DIRS |
| AC22 | D5 | AJAX fetch triggered only when stage expanded; content not preloaded |
| AC23 | D5 | Expanding previously-unloaded stage triggers fetch for each artifact |
| AC24 | D5 | Initial page renders only headers + metadata; faster than eager loading |
| AC25 | D6 | "User Request" label in build_stages() replaces "Raw Input" |
| AC26 | D6 | Intake stage artifact name is "User Request" |
