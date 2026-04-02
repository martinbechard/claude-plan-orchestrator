# Design: 74 Item Page Step Explorer

Source: tmp/plans/.claimed/74-item-page-step-explorer.md
Requirements: docs/plans/2026-04-02-74-item-page-step-explorer-requirements.md

## Architecture Overview

The item detail page is restructured as a stage-based step explorer. A server-side
data model groups all work item artifacts under six ordered pipeline stages
(Intake, Requirements, Planning, Execution, Verification, Archive). Each stage
carries a three-state status indicator and completion timestamp. Each artifact
carries its own creation/modification timestamp.

The Jinja2 template renders a vertical accordion of collapsible stage sections.
Artifact content is not embedded at page load; stage expansion triggers AJAX
fetches to the existing artifact-content endpoint, keeping initial page load
lightweight. A loading indicator is shown while content is fetched.

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
| langgraph_pipeline/web/routes/item.py | Modify: stage data model, build_stages(), status matrix, /dynamic extension |
| langgraph_pipeline/web/templates/item.html | Modify: step explorer accordion with collapsible stages, on-demand loading |

---

## Design Decisions

### D1: Stage-based artifact grouping data model

Addresses: P1, P2, FR1, UC1
Satisfies: AC1, AC2, AC3, AC9, AC10, AC15, AC16, AC17, AC18, AC19, AC20

Approach: Define StageInfo and ArtifactInfo TypedDicts in item.py. A build_stages()
function maps existing artifact discovery results into six ordered StageInfo dicts.
The Verification stage is omitted when item_type is "feature" (AC19 specifies
verification for defects only).

ArtifactInfo fields: name (display label), path (for lazy fetch), timestamp
(file mtime epoch), timestamp_display (pre-formatted string).

StageInfo fields: id (lowercase key), name (display label), status (three-state),
artifacts (list of ArtifactInfo), completion_ts (formatted), completion_epoch (raw).

The six stages and their artifact mappings:

1. Intake: User Request (raw backlog file), Clause Register, 5 Whys Analysis (AC15)
2. Requirements: Structured Requirements document (AC16)
3. Planning: Design Document, YAML Plan (AC17)
4. Execution: per-task log files, validation JSON files (AC18)
5. Verification: final verification report, defects only (AC19)
6. Archive: completion record from completed backlog dirs (AC20)

STAGE_ORDER constant enforces chronological pipeline ordering. The page displays
exactly six stages in order (AC9, AC10) with artifacts nested under each stage
(AC1, AC3). Artifacts are grouped under their originating pipeline stage (AC1),
replacing the flat layout with a structured navigable layout (AC2).

Files: langgraph_pipeline/web/routes/item.py

### D2: Stage status computation

Addresses: FR2
Satisfies: AC21, AC22

Approach: Each stage's status is one of: "not_started", "in_progress", "done"
(AC21). A _compute_stage_statuses() function uses the item's pipeline_stage
and a lookup matrix mapping pipeline states to expected status per stage index.

A "done*" adjustment: stages marked done that have no artifacts are downgraded
to in_progress. This ensures the status accurately reflects the actual state
of each stage (AC22).

Files: langgraph_pipeline/web/routes/item.py

### D3: Stage completion timestamps

Addresses: FR3, P2
Satisfies: AC4, AC6, AC23, AC24

Approach: Each completed stage displays a completion timestamp derived from the
latest artifact mtime within that stage (AC23). Stages that have not completed
display no timestamp (AC24). Timestamps on stages provide temporal context (AC4)
and the chronological ordering of stages plus their timestamps makes the temporal
sequence of work visually apparent (AC6).

Timestamps are formatted as "YYYY-MM-DD HH:MM" in local time, computed server-side.

Files: langgraph_pipeline/web/routes/item.py

### D4: Per-artifact timestamps

Addresses: FR4, P2
Satisfies: AC25, AC26

Approach: Each artifact's timestamp is its file modification time (st_mtime),
formatted as "YYYY-MM-DD HH:MM" (local time) server-side. Each artifact nested
under a stage displays its own timestamp (AC25). The timestamp reflects when the
artifact file was created or last modified (AC26).

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D5: On-demand artifact loading with loading indicator

Addresses: P3, FR5
Satisfies: AC7, AC8, AC27, AC28

Approach: At page load, the template renders only stage headers and artifact
metadata (name, timestamp) but not artifact content. The initial page load
fetches only stage metadata without artifact content (AC7, AC8). When a user
expands a stage, JavaScript fetches each artifact's content via the existing
/item/{slug}/artifact-content?path={path} endpoint (AC27).

A spinner/loading indicator is shown in the artifact content area while the
fetch is in progress (AC28). Fetched content is cached via a data-loaded DOM
attribute; re-expanding does not re-fetch. The /dynamic endpoint includes a
stages array with artifact_count so live polling can detect new artifacts and
clear the cache.

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D6: Collapsible stage accordion with persistence

Addresses: UC2, P1, P2
Satisfies: AC5, AC11, AC12, AC13, AC14

Approach: Each stage renders as a section with a clickable button header that
toggles body visibility. CSS class "collapsed" hides the body. JavaScript
persists open/closed state in localStorage keyed by slug + stage id.

Users can collapse sections they are not interested in (AC5). Users can navigate
to a specific stage quickly without scrolling through all content (AC11).
Each stage can be independently collapsed (AC12) and expanded (AC13) without
affecting other stages (AC14).

A chevron icon indicates collapse/expand state. The most recent active stage
defaults to expanded on first visit; all others default to collapsed.

Stage headers use button elements with aria-expanded and aria-controls for
accessibility.

Files: langgraph_pipeline/web/templates/item.html

### D7: Rename Raw Input to User Request

Addresses: FR6
Satisfies: AC29, AC30

Approach: The artifact display name for the original backlog file is "User
Request" in build_stages() (AC29). No reference to "Raw Input" appears as a
label anywhere on the item page (AC30). The underlying file path and data key
remain unchanged.

Files: langgraph_pipeline/web/routes/item.py

---

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | Artifacts grouped under parent pipeline stage instead of flat list |
| AC2 | D1 | Single long page replaced by structured, navigable layout with section boundaries |
| AC3 | D1 | Each artifact visually indicates pipeline stage via nesting under stage header |
| AC4 | D3 | Timestamps displayed for each pipeline stage (completion time) |
| AC5 | D6 | Users can collapse sections they are not interested in |
| AC6 | D3 | Temporal sequence apparent through stage ordering and timestamps |
| AC7 | D5 | Artifacts loaded on demand rather than all at page load |
| AC8 | D5 | Initial page load faster because artifact content is deferred |
| AC9 | D1 | Step explorer shows stages in chronological pipeline order with artifacts nested |
| AC10 | D1 | Stages displayed in order: Intake, Requirements, Planning, Execution, Verification, Archive |
| AC11 | D6 | User navigates to specific stage quickly via expand, others stay collapsed |
| AC12 | D6 | User collapses a pipeline stage to hide its artifacts |
| AC13 | D6 | User expands a collapsed pipeline stage to reveal its artifacts |
| AC14 | D6 | Each stage independently collapse/expand without affecting others |
| AC15 | D1 | Intake stage contains: User Request, clause register, 5 whys analysis |
| AC16 | D1 | Requirements stage contains: structured requirements document |
| AC17 | D1 | Planning stage contains: design document, YAML plan |
| AC18 | D1 | Execution stage contains: per-task results, validation reports |
| AC19 | D1 | Verification stage appears only for defects, contains final verification report |
| AC20 | D1 | Archive stage contains: completion status, outcome |
| AC21 | D2 | Each stage displays status: not started, in progress, or done |
| AC22 | D2 | Status accurately reflects actual pipeline stage state via lookup matrix |
| AC23 | D3 | Completed stage displays completion timestamp from latest artifact mtime |
| AC24 | D3 | Timestamp absent/hidden for stages that have not completed |
| AC25 | D4 | Each artifact displays its own timestamp |
| AC26 | D4 | Artifact timestamp reflects file creation or last modification time |
| AC27 | D5 | Artifact contents loaded only when user expands or requests (not at page load) |
| AC28 | D5 | Loading indicator shown while artifact content is being fetched |
| AC29 | D7 | Label "Raw Input" replaced with "User Request" in Intake stage |
| AC30 | D7 | "Raw Input" no longer appears as a label anywhere on the item page |
