# Design: 74 Item Page Step Explorer

Source: tmp/plans/.claimed/74-item-page-step-explorer.md
Requirements: docs/plans/2026-03-31-74-item-page-step-explorer-requirements.md

## Architecture Overview

The item detail page is restructured from a flat layout into a stage-based step
explorer. A server-side data model groups all work item artifacts under six
ordered pipeline stages (Intake, Requirements, Planning, Execution, Verification,
Archive). Each stage carries its own status and completion timestamp, and each
artifact carries a created/modified timestamp.

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
| langgraph_pipeline/web/templates/item.html | Modify: replace layout with step explorer accordion |

---

## Design Decisions

### D1: Stage-based artifact grouping data model

Addresses: P1, P2, FR1
Satisfies: AC1, AC2, AC5, AC6, AC7, AC8, AC9, AC10, AC11, AC12, AC17

Approach: Define a StageInfo TypedDict and an ArtifactInfo TypedDict in item.py.
A build_stages() function maps existing artifact discovery results into six
ordered StageInfo dicts. The Verification stage is omitted when the item type
is "feature" (AC11 specifies verification shown for defects only).

ArtifactInfo fields: name (display label), path (for lazy fetch), timestamp
(file mtime epoch), timestamp_display (pre-formatted string).

StageInfo fields: id (lowercase key), name (display label), status (three-state),
artifacts (list of ArtifactInfo), completion_ts (formatted), completion_epoch (raw).

The six stages and their artifact mappings:

1. Intake: User Request (raw backlog file), Clause Register, 5 Whys Analysis (AC7)
2. Requirements: Structured Requirements document (AC8)
3. Planning: Design Document, YAML Plan (AC9)
4. Execution: per-task log files, validation JSON files (AC10)
5. Verification: final verification report, defects only (AC11)
6. Archive: completion record from completed backlog dirs (AC12)

STAGE_ORDER constant enforces chronological pipeline ordering (AC6) and
is the single source of truth for stage identity and display names.
Artifacts are nested under their parent stage with timestamps (AC17).
The page shows artifacts grouped under stage headings (AC5), displayed
as a visual hierarchy showing pipeline stage origin (AC2), instead of
a flat page (AC1).

Files: langgraph_pipeline/web/routes/item.py

### D2: Stage status computation

Addresses: UC1
Satisfies: AC15

Approach: Each stage's status is one of: "not_started", "in_progress", "done"
(AC15). A _compute_stage_statuses() function uses the item's pipeline_stage
(from _derive_pipeline_stage()) and a lookup matrix mapping 9 pipeline states
(queued, unknown, claimed, designing, planning, executing, validating,
completed, stuck) to expected status per stage index.

A "done*" adjustment: stages marked done that have no artifacts are downgraded
to in_progress. The "stuck" state uses artifact-based fallback to show
progress up to the point of failure.

Files: langgraph_pipeline/web/routes/item.py

### D3: Timestamps on stages and artifacts

Addresses: P3, UC1, FR3
Satisfies: AC3, AC16, AC17, AC20, AC21

Approach: Each artifact's timestamp is its file modification time (st_mtime),
formatted as "YYYY-MM-DD HH:MM" (local time) server-side. Each stage's
completion timestamp is the latest mtime among its artifacts, shown only when
status is "done" (AC16). Server-side formatting avoids client-side date logic.

Each artifact document displays its created/modified timestamp (AC20), visible
without additional interaction beyond expanding the parent stage (AC21).
Artifacts are nested under their parent stage with their own timestamps (AC17).
Timestamps are shown on both stages and artifacts (AC3).

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D4: Collapsible stage accordion with persistence

Addresses: P4, UC1
Satisfies: AC4, AC13, AC14

Approach: Each stage renders as a section with a clickable button header that
toggles body visibility. CSS class "collapsed" hides the body. JavaScript
manages toggle and persists open/closed state in localStorage keyed by
slug + stage id.

Users can collapse (AC13) and expand (AC14) each stage section independently
(AC4). The most recent active stage defaults to expanded on first visit; all
others default to collapsed. Subsequent visits restore persisted state.

Stage headers use button elements with aria-expanded and aria-controls for
accessibility. Keyboard navigation supported natively via button semantics.

Files: langgraph_pipeline/web/templates/item.html

### D5: On-demand artifact loading

Addresses: FR2
Satisfies: AC18, AC19

Approach: At page load, the template renders only stage headers and artifact
metadata (name, timestamp) but not artifact content. When a user expands a
stage, JavaScript fetches each artifact's content via the existing
/item/{slug}/artifact-content?path={path} endpoint. Fetched content is cached
via a data-loaded DOM attribute; re-expanding does not re-fetch.

Artifact contents are deferred until the user expands the parent stage (AC18).
The initial page load avoids fetching all artifact content upfront (AC19).

The /dynamic endpoint is extended to include a stages array with status,
timestamps, and artifact_count so live polling can detect new artifacts and
clear the cache. Polling does NOT fetch content -- only stage metadata.

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D6: Rename Raw Input to User Request

Addresses: FR4
Satisfies: AC22, AC23

Approach: The artifact display name for the original backlog file is "User
Request" in build_stages() (AC22). The label "Raw Input" is removed from all
template text and heading references (AC23). The underlying file path and data
key remain unchanged.

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

---

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | Artifacts organized into distinct navigable stage sections instead of flat page |
| AC2 | D1 | Visual hierarchy: stage headers group artifacts, showing pipeline stage origin |
| AC3 | D3 | Timestamps on both stage headers (completion_ts) and artifacts (timestamp_display) |
| AC4 | D4 | Collapsible stage sections with CSS collapsed class and JS toggle |
| AC5 | D1 | Step explorer with artifacts grouped under pipeline stage headings |
| AC6 | D1 | STAGE_ORDER constant defines six stages in chronological pipeline order |
| AC7 | D1 | Intake stage discovers: User Request, Clause Register, 5 Whys Analysis |
| AC8 | D1 | Requirements stage discovers: Structured Requirements document |
| AC9 | D1 | Planning stage discovers: Design Document, YAML Plan |
| AC10 | D1 | Execution stage discovers: per-task log files, validation JSON files |
| AC11 | D1 | Verification stage discovers: verification report; omitted for feature items |
| AC12 | D1 | Archive stage discovers: completion record from COMPLETED_DIRS |
| AC13 | D4 | Click stage header to collapse and hide artifacts independently |
| AC14 | D4 | Click collapsed stage header to expand and reveal artifacts |
| AC15 | D2 | Three-state status indicator (not_started / in_progress / done) per stage |
| AC16 | D3 | Stage completion timestamp from latest artifact mtime when status is done |
| AC17 | D1, D3 | Artifacts nested under parent stage, each with its own timestamp |
| AC18 | D5 | AJAX fetch triggered only when parent stage expanded; content deferred |
| AC19 | D5 | Initial page load renders headers and metadata only; no artifact content upfront |
| AC20 | D3 | Each artifact document displays file mtime as created/modified timestamp |
| AC21 | D3 | Timestamp visible within expanded stage without additional user interaction |
| AC22 | D6 | Former "Raw Input" now labeled "User Request" in build_stages() |
| AC23 | D6 | All "Raw Input" label references removed from template and backend |
