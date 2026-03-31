# Design: 74 Item Page Step Explorer

Source: tmp/plans/.claimed/74-item-page-step-explorer.md
Requirements: docs/plans/2026-03-31-74-item-page-step-explorer-requirements.md

## Architecture Overview

The item detail page is structured as a stage-based step explorer. A server-side
data model groups all work item artifacts under six ordered pipeline stages
(Intake, Requirements, Planning, Execution, Verification, Archive). Each stage
carries its own status and completion timestamp, and each artifact carries a
created/modified timestamp.

The Jinja2 template renders a vertical accordion of collapsible stage sections.
Artifact content is not embedded at page load; instead, stage expansion triggers
AJAX fetches to the existing artifact-content endpoint, keeping the initial
page load lightweight.

The existing /item/{slug}/dynamic polling endpoint returns stage-level status
so the accordion updates live while a worker is active.

### Technology stack

- Backend: Python/FastAPI (existing)
- Templates: Jinja2 (existing)
- Frontend: vanilla JS (existing, no framework)
- Styling: embedded CSS in item.html (existing pattern)

### Key files to create or modify

| File | Action |
|---|---|
| langgraph_pipeline/web/routes/item.py | Modify: stage data model, build_stages(), status matrix, /dynamic extension |
| langgraph_pipeline/web/templates/item.html | Modify: step explorer accordion with collapsible stages |

---

## Design Decisions

### D1: Stage-based artifact grouping data model

Addresses: P1, FR1
Satisfies: AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC20, AC21, AC22

Approach: Define StageInfo and ArtifactInfo TypedDicts in item.py. A build_stages()
function maps existing artifact discovery results into six ordered StageInfo dicts.
The Verification stage is omitted when item_type is "feature" (AC5 specifies
verification for defects only).

ArtifactInfo fields: name (display label), path (for lazy fetch), timestamp
(file mtime epoch), timestamp_display (pre-formatted string).

StageInfo fields: id (lowercase key), name (display label), status (three-state),
artifacts (list of ArtifactInfo), completion_ts (formatted), completion_epoch (raw).

The six stages and their artifact mappings:

1. Intake: User Request (raw backlog file), Clause Register, 5 Whys Analysis (AC1)
2. Requirements: Structured Requirements document (AC2)
3. Planning: Design Document, YAML Plan (AC3)
4. Execution: per-task log files, validation JSON files (AC4)
5. Verification: final verification report, defects only (AC5)
6. Archive: completion record from completed backlog dirs (AC6)

STAGE_ORDER constant enforces chronological pipeline ordering. The page displays
exactly six stages in order (AC7) with artifacts in chronological order (AC8).
Artifacts are grouped under their originating pipeline stage (AC20), providing
visual hierarchy (AC21) and enabling identification of artifact origin without
scrolling (AC22).

Files: langgraph_pipeline/web/routes/item.py

### D2: Stage status computation and completion timestamps

Addresses: FR2
Satisfies: AC9, AC10

Approach: Each stage's status is one of: "not_started", "in_progress", "done"
(AC9). A _compute_stage_statuses() function uses the item's pipeline_stage
and a lookup matrix mapping 9 pipeline states to expected status per stage index.

Each completed stage displays a completion timestamp derived from the latest
artifact mtime (AC10). A "done*" adjustment: stages marked done that have no
artifacts are downgraded to in_progress.

Files: langgraph_pipeline/web/routes/item.py

### D3: Per-artifact timestamps

Addresses: P2, FR3
Satisfies: AC11, AC12, AC23, AC24

Approach: Each artifact's timestamp is its file modification time (st_mtime),
formatted as "YYYY-MM-DD HH:MM" (local time) server-side. Artifacts are nested
under their parent stage with their own timestamps (AC11). Each artifact document
displays its created/modified timestamp (AC12), distinct from the parent stage
completion timestamp. Timestamps are displayed on both stages and artifacts (AC23),
enabling users to reconstruct the temporal sequence of work (AC24).

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D4: On-demand artifact loading

Addresses: P4, FR4
Satisfies: AC13, AC14, AC15, AC26

Approach: At page load, the template renders only stage headers and artifact
metadata (name, timestamp) but not artifact content. The initial page load
fetches only stage metadata without artifact content (AC14). When a user expands
a stage, JavaScript fetches each artifact's content via the existing
/item/{slug}/artifact-content?path={path} endpoint (AC15). Artifact contents
are loaded on demand (AC13), and the page avoids loading all content
simultaneously (AC26).

Fetched content is cached via a data-loaded DOM attribute; re-expanding does
not re-fetch. The /dynamic endpoint includes a stages array with artifact_count
so live polling can detect new artifacts and clear the cache.

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D5: Collapsible stage accordion with persistence

Addresses: P3, UC1
Satisfies: AC16, AC17, AC25

Approach: Each stage renders as a section with a clickable button header that
toggles body visibility. CSS class "collapsed" hides the body. JavaScript
persists open/closed state in localStorage keyed by slug + stage id.

Each stage section can be independently expanded and collapsed (AC16). A chevron
icon indicates collapse/expand state (AC17). Users can collapse sections they
are not interested in (AC25). The most recent active stage defaults to expanded
on first visit; all others default to collapsed.

Stage headers use button elements with aria-expanded and aria-controls for
accessibility.

Files: langgraph_pipeline/web/templates/item.html

### D6: Rename Raw Input to User Request

Addresses: FR5
Satisfies: AC18, AC19

Approach: The artifact display name for the original backlog file is "User
Request" in build_stages() (AC18). The label appears within the Intake stage
section (AC19). The underlying file path and data key remain unchanged.

Files: langgraph_pipeline/web/routes/item.py

---

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | Intake stage contains: User Request, clause register, 5 whys analysis |
| AC2 | D1 | Requirements stage contains: structured requirements document |
| AC3 | D1 | Planning stage contains: design document, YAML plan |
| AC4 | D1 | Execution stage contains: per-task results, validation reports |
| AC5 | D1 | Verification stage contains: final verification report (defects only) |
| AC6 | D1 | Archive stage contains: completion status, outcome |
| AC7 | D1 | Page displays exactly six stages in order: Intake through Archive |
| AC8 | D1 | Stages displayed in chronological pipeline order via STAGE_ORDER |
| AC9 | D2 | Three-state status indicator (not_started / in_progress / done) per stage |
| AC10 | D2 | Completed stage displays completion timestamp from latest artifact mtime |
| AC11 | D3 | Artifacts nested under parent stage, each with own timestamp |
| AC12 | D3 | Each artifact displays file mtime as creation/modification timestamp |
| AC13 | D4 | Artifact content loaded on demand, not at page load |
| AC14 | D4 | Initial page load fetches only stage metadata, no artifact content |
| AC15 | D4 | Content fetched only when user expands stage or clicks artifact |
| AC16 | D5 | Independent collapse/expand per stage via CSS class toggle |
| AC17 | D5 | Chevron icon rotates to indicate collapse/expand state |
| AC18 | D6 | "Raw Input" label replaced with "User Request" |
| AC19 | D6 | "User Request" label appears within Intake stage section |
| AC20 | D1 | Artifacts grouped under originating pipeline stage, not flat list |
| AC21 | D1 | Visual hierarchy: stage headers (bold) vs nested artifacts (indented) |
| AC22 | D1 | Artifact origin identifiable from stage grouping without full scroll |
| AC23 | D3 | Timestamps displayed on both stages and artifacts |
| AC24 | D3 | Chronological order plus per-artifact timestamps show temporal sequence |
| AC25 | D5 | Users can collapse sections they are not interested in |
| AC26 | D4 | Page avoids loading all content simultaneously; faster render |
