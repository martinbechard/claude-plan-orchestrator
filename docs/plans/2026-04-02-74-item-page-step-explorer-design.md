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

Addresses: P1, P2, FR1
Satisfies: AC1, AC2, AC3, AC4, AC11, AC12, AC13, AC14, AC15, AC16, AC17, AC20

Approach: Define StageInfo and ArtifactInfo TypedDicts in item.py. A build_stages()
function maps existing artifact discovery results into six ordered StageInfo dicts.
The Verification stage is omitted when item_type is "feature" (AC15 specifies
verification for defects only).

ArtifactInfo fields: name (display label), path (for lazy fetch), timestamp
(file mtime epoch), timestamp_display (pre-formatted string).

StageInfo fields: id (lowercase key), name (display label), status (three-state),
artifacts (list of ArtifactInfo), completion_ts (formatted), completion_epoch (raw).

The six stages and their artifact mappings:

1. Intake: User Request (raw backlog file), Clause Register, 5 Whys Analysis (AC11)
2. Requirements: Structured Requirements document (AC12)
3. Planning: Design Document, YAML Plan (AC13)
4. Execution: per-task log files, validation JSON files (AC14)
5. Verification: final verification report, defects only (AC15)
6. Archive: completion record from completed backlog dirs (AC16)

STAGE_ORDER constant enforces chronological pipeline ordering (AC17). The page
displays exactly six stages in order with artifacts nested under each stage
(AC1, AC3, AC20). Artifacts are grouped under their originating pipeline stage
(AC1), replacing the flat layout with a structured navigable layout (AC2).
The temporal sequence of stages is visually apparent (AC4).

Files: langgraph_pipeline/web/routes/item.py

### D2: Stage status computation

Addresses: FR2
Satisfies: AC18

Approach: Each stage's status is one of: "not_started", "in_progress", "done"
(AC18). A _compute_stage_statuses() function uses the item's pipeline_stage
and a lookup matrix mapping pipeline states to expected status per stage index.

A "done*" adjustment: stages marked done that have no artifacts are downgraded
to in_progress. This ensures the status accurately reflects the actual state
of each stage.

Files: langgraph_pipeline/web/routes/item.py

### D3: Stage completion timestamps

Addresses: P3, FR2
Satisfies: AC5, AC19

Approach: Each completed stage displays a completion timestamp derived from the
latest artifact mtime within that stage (AC19). Stages that have not completed
display no timestamp. Timestamps on stages provide temporal context (AC5).

Timestamps are formatted as "YYYY-MM-DD HH:MM" in local time, computed server-side.

Files: langgraph_pipeline/web/routes/item.py

### D4: Per-artifact timestamps

Addresses: P3, FR2
Satisfies: AC6, AC21

Approach: Each artifact's timestamp is its file modification time (st_mtime),
formatted as "YYYY-MM-DD HH:MM" (local time) server-side. Each artifact nested
under a stage displays its own timestamp (AC21). The timestamp reflects when the
artifact file was created or last modified (AC6).

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D5: On-demand artifact loading with loading indicator

Addresses: P5, FR3
Satisfies: AC9, AC10, AC23, AC24, AC25

Approach: At page load, the template renders only stage headers and artifact
metadata (name, timestamp) but not artifact content. The initial page load
fetches only stage metadata without artifact content (AC9, AC24). The initial
page load is faster because artifact content is deferred (AC10). When a user
expands a stage, JavaScript fetches each artifact's content via the existing
/item/{slug}/artifact-content?path={path} endpoint (AC23). Expanding a stage
loads artifacts without a full page refresh (AC25).

A spinner/loading indicator is shown in the artifact content area while the
fetch is in progress. Fetched content is cached via a data-loaded DOM
attribute; re-expanding does not re-fetch. The /dynamic endpoint includes a
stages array with artifact_count so live polling can detect new artifacts and
clear the cache.

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D6: Collapsible stage accordion with persistence

Addresses: P4, FR2
Satisfies: AC7, AC8, AC22

Approach: Each stage renders as a section with a clickable button header that
toggles body visibility. CSS class "collapsed" hides the body. JavaScript
persists open/closed state in localStorage keyed by slug + stage id.

Users can collapse any stage section they are not interested in (AC7).
Collapsed sections remain collapsed until the user explicitly expands them
(AC8). Each stage section can be collapsed and expanded by the user (AC22).

A chevron icon indicates collapse/expand state. The most recent active stage
defaults to expanded on first visit; all others default to collapsed.

Stage headers use button elements with aria-expanded and aria-controls for
accessibility.

Files: langgraph_pipeline/web/templates/item.html

### D7: Rename Raw Input to User Request

Addresses: FR4
Satisfies: AC26, AC27

Approach: The artifact display name for the original backlog file is "User
Request" in build_stages() (AC26). The underlying file path and data key
remain unchanged so the same artifact content is referenced (AC27).

Files: langgraph_pipeline/web/routes/item.py

---

## Systems Architecture

### Architecture Overview

```
+--------------------+      +-----------------+      +------------------+
|   item_detail()    |----->| build_stages()  |----->| StageInfo[]      |
| GET /item/{slug}   |      |   Pass 1: Discover     | (6 stages, each  |
|                    |      |   Pass 2: Status       |  with artifacts) |
+--------------------+      |   Pass 3: Timestamps   +------------------+
         |                  +-----------------+              |
         v                          ^                       v
+--------------------+              |              +------------------+
|   item.html        |              |              | item_dynamic()   |
| Jinja2 accordion   |              |              | GET /item/{slug} |
| (stage headers +   |              |              |     /dynamic     |
|  lazy artifact     |              |              | -> stage_summaries|
|  loading via AJAX) |              |              +------------------+
+--------------------+              |
         |                          |
         v                          |
+--------------------+      +-----------------+
| artifact-content   |      | _compute_stage_ |
| GET /item/{slug}/  |      |   statuses()    |
|   artifact-content |      | _BASE_MATRIX    |
| ?path=...          |      | done* adjustment|
+--------------------+      +-----------------+
```

Data flows top-down from the page request through build_stages() which produces
StageInfo arrays consumed by both the template and the /dynamic polling endpoint.

### Data Models

#### ArtifactInfo (TypedDict)

| Field | Type | Description | Constraints |
|---|---|---|---|
| name | str | Human-readable display label (e.g. "User Request") | Always non-empty; unique within a stage |
| path | str | Relative file path for /artifact-content on-demand loading | Stringified Path; file must exist at discovery time |
| timestamp | float | Raw epoch float from file st_mtime | 0.0 sentinel when mtime is unavailable |
| timestamp_display | str | Pre-formatted "YYYY-MM-DD HH:MM" string for Jinja2 | Empty string when timestamp is 0.0 |

Each ArtifactInfo belongs to exactly one StageInfo via the artifacts list.
Created by _make_artifact() which reads file mtime at discovery time.

#### StageInfo (TypedDict)

| Field | Type | Description | Constraints |
|---|---|---|---|
| id | str | Lowercase identifier (e.g. "intake") | Must match first element of a STAGE_ORDER tuple |
| name | str | Title-case display label (e.g. "Intake") | Must match second element of a STAGE_ORDER tuple |
| status | str | One of "not_started", "in_progress", "done" | Set by _compute_stage_statuses() in Pass 2 |
| artifacts | list[ArtifactInfo] | Ordered list of discovered artifacts | May be empty; order is discovery order |
| completion_ts | Optional[str] | Formatted timestamp when status is "done" | None when status is not "done" or no artifacts |
| completion_epoch | Optional[float] | Raw epoch float for JSON serialisation | None when completion_ts is None |

STAGE_ORDER defines the canonical list of 6 stages. StageInfo instances are built
in STAGE_ORDER sequence. The Verification stage is omitted when item_type is "feature".

### build_stages() Algorithm

Signature: build_stages(slug, item_type, pipeline_stage) -> list[StageInfo]

#### Pass 1: Artifact Discovery

For each stage, the function probes specific file paths and populates a
stage_artifacts dictionary keyed by stage id.

**Intake stage:**
1. _find_original_request_file(slug) -> "User Request" (searches claimed/, backlog dirs, completed dirs)
2. workspace_path(slug)/clauses.md -> "Clause Register"
3. workspace_path(slug)/five-whys.md -> "5 Whys Analysis"

**Requirements stage:**
1. _find_structured_requirements_file(slug) -> "Structured Requirements" (workspace first, then docs/plans/ glob)

**Planning stage:**
1. _find_design_doc(slug) -> "Design Document" (workspace first, then docs/plans/ glob)
2. _find_plan_yaml(slug) -> "YAML Plan" (exact match in tmp/plans/, then prefix glob)

**Execution stage:**
1. Log files (.log): scans WORKER_OUTPUT_DIR/slug/ then workspace logs/, sorted, deduplicated by filename
2. Validation JSONs: scans workspace validation/ then WORKER_OUTPUT_DIR/slug/ for validation-*.json, deduplicated

**Verification stage:**
1. workspace verification-report.md -> "Verification Report" (workspace priority; first match wins)

**Archive stage:**
1. First match of slug.md across COMPLETED_DIRS values -> "Completion Record"

After discovery, StageInfo dicts are constructed from STAGE_ORDER, skipping
"verification" when item_type is "feature". Initial status is "not_started".

#### Pass 2: Status Computation

Delegates to _compute_stage_statuses(stages, pipeline_stage). See Status
Computation Matrix below.

#### Pass 3: Completion Timestamps

For each stage with status "done" and at least one artifact:
- completion_epoch = max(artifact.timestamp for all artifacts in stage)
- completion_ts = _format_timestamp(completion_epoch)

Stages with status "done" but no artifacts retain None for both timestamp fields.

### Status Computation Matrix

_compute_stage_statuses() uses _BASE_MATRIX mapping each pipeline_stage to
per-stage status values.

#### _BASE_MATRIX

| pipeline_stage | intake | requirements | planning | execution | verification | archive |
|---|---|---|---|---|---|---|
| queued | N | N | N | N | N | N |
| unknown | N | N | N | N | N | N |
| claimed | P | N | N | N | N | N |
| designing | D* | D* | P | N | N | N |
| planning | D* | D* | P | N | N | N |
| executing | D* | D* | D* | P | N | N |
| validating | D* | D* | D* | D* | P | N |
| completed | D | D | D | D | D | D |

Legend: N = not_started, P = in_progress, D = done, D* = done with adjustment

#### done* Adjustment Logic

Stages in {intake, requirements, planning, execution, verification} are subject
to the done* rule: when the base matrix assigns "done" AND pipeline_stage is not
"completed" AND the stage has zero artifacts, status is downgraded to "in_progress".
This prevents showing a stage as complete when no evidence of its output exists.

The "archive" stage is excluded from this adjustment because its completion is
self-evident from pipeline_stage being "completed".

When pipeline_stage is "completed", all stages are unconditionally "done"
regardless of artifact presence.

#### Fallback for Unrecognised pipeline_stage

When pipeline_stage is "stuck" or any unrecognised value (not in _BASE_MATRIX),
status is derived from artifact presence: stages with artifacts are "done", the
first without artifacts is "in_progress", all subsequent are "not_started".

### API Extension: /dynamic Endpoint

GET /item/{slug}/dynamic returns a JSON object. The stages field supports live
polling of stage status without full page reload.

#### stage_summaries Schema

```
stages: [
    {
        "id": string,              // e.g. "intake"
        "status": string,          // "not_started" | "in_progress" | "done"
        "completion_ts": string?,  // "YYYY-MM-DD HH:MM" or null
        "completion_epoch": float?, // epoch seconds or null
        "artifact_count": int      // number of discovered artifacts
    },
    ...
]
```

The array contains one entry per visible stage (5 for features, 6 for defects).
Each poll returns freshly computed stage data from build_stages(). The frontend
compares artifact_count to detect new artifacts and clear cached content.

### Artifact-to-Stage Mapping Table

| Stage | Artifact Label | File Path Pattern | Discovery Function |
|---|---|---|---|
| intake | User Request | tmp/plans/.claimed/{slug}.md OR backlog/{slug}.md OR completed/{slug}.md | _find_original_request_file() |
| intake | Clause Register | .worktrees/{slug}/clauses.md | Direct path check |
| intake | 5 Whys Analysis | .worktrees/{slug}/five-whys.md | Direct path check |
| requirements | Structured Requirements | .worktrees/{slug}/requirements.md OR docs/plans/*-{slug}-requirements.md | _find_structured_requirements_file() |
| planning | Design Document | .worktrees/{slug}/design.md OR docs/plans/*-{slug}-design.md | _find_design_doc() |
| planning | YAML Plan | tmp/plans/{slug}.yaml OR tmp/plans/{slug}*.yaml | _find_plan_yaml() |
| execution | {filename}.log | docs/reports/worker-output/{slug}/*.log OR .worktrees/{slug}/logs/*.log | Directory scan, deduplicated |
| execution | validation-*.json | .worktrees/{slug}/validation/*.json OR worker-output/{slug}/*.json | Glob scan, deduplicated |
| verification | Verification Report | .worktrees/{slug}/verification-report.md OR worker-output/{slug}/verification-report.md | First-match priority |
| archive | Completion Record | docs/completed-{type}/{slug}.md | First match across COMPLETED_DIRS |

Priority rules: Workspace paths take priority over legacy docs/plans/ paths.
Workspace verification-report.md takes priority over worker-output copy.
Worker-output logs are listed before workspace logs. Workspace validation JSONs
take priority over worker-output copies.

### Timestamp Strategy

```
File on disk
    |  stat().st_mtime (epoch float)
    v
_make_artifact()
    |
    +---> ArtifactInfo.timestamp (raw float, 0.0 on stat error)
    +---> _format_timestamp(epoch) -> ArtifactInfo.timestamp_display

Pass 3 of build_stages():
    |  max(artifact.timestamp for all artifacts in stage)
    |  (only for stages with status == "done" and len(artifacts) > 0)
    v
    +---> StageInfo.completion_epoch (raw float)
    +---> _format_timestamp(max_epoch) -> StageInfo.completion_ts
```

Key properties:
- All timestamps are local time (server timezone), not UTC
- Format is "YYYY-MM-DD HH:MM" via _TIMESTAMP_FORMAT constant
- 0.0 sentinel for unavailable mtime produces empty display strings
- Stage completion timestamp is derived (max of artifact mtimes), not stored independently
- /dynamic exposes both raw epoch and formatted string for display and comparison

### Component Hierarchy

```
item_detail (FastAPI endpoint)
    +-- build_stages(slug, item_type, pipeline_stage)
    |       +-- _find_original_request_file(slug)
    |       +-- _find_structured_requirements_file(slug)
    |       +-- _find_design_doc(slug)
    |       +-- _find_plan_yaml(slug)
    |       +-- _make_artifact(name, path)  [per discovered file]
    |       +-- _compute_stage_statuses(stages, pipeline_stage)
    |       +-- _format_timestamp(epoch)  [Pass 3]
    |       v
    |   list[StageInfo] --> template as "stages"
    +-- item.html template
            +-- Stage accordion (iterates stages)
            |       +-- Stage header (name, status badge, completion_ts)
            |       +-- Stage body (iterates artifacts)
            |               +-- Artifact row (name, timestamp_display)
            |               +-- Content area (lazy-loaded via AJAX)
            +-- JavaScript
                    +-- Expand/collapse with localStorage persistence
                    +-- AJAX fetch to /artifact-content?path=...
                    +-- Polling /dynamic for stage_summaries updates
```

### Trade-off Analysis

**Chosen: Server-side stage computation with client-side lazy loading**

Pros:
- Single source of truth for stage/status logic in Python
- Template receives pre-computed data; no complex client logic
- Artifact content deferred to AJAX keeps initial payload small
- Existing /artifact-content endpoint reused without modification

Cons:
- Every /dynamic poll recomputes all stages (includes filesystem stat calls)
- Stage computation is not cached between page load and first poll

**Alternative: Client-side stage computation from raw artifact list** - Rejected
because it duplicates stage-ordering and status-matrix logic in JavaScript,
harder to maintain, violates existing server-side rendering pattern.

**Alternative: Embed all artifact content at page load** - Rejected because it
produces slow initial load for items with many execution logs and wastes
bandwidth for collapsed stages the user never expands.

### Scalability Considerations

- **Artifact count growth:** Execution stage can accumulate unbounded log files.
  Lazy loading handles this (content fetched only on expand). /dynamic returns
  only artifact_count. Pagination within a stage could be added without changing
  the StageInfo model.

- **New pipeline stages:** Adding a stage requires only appending to STAGE_ORDER
  and adding a row to _BASE_MATRIX. build_stages() and template iterate
  dynamically over STAGE_ORDER.

- **New artifact types:** Adding an artifact to an existing stage requires only
  adding a discovery block in Pass 1 of build_stages(). No schema changes needed.

---

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | Artifacts grouped under parent pipeline stage instead of flat list |
| AC2 | D1 | Single long page replaced by structured, navigable layout with section boundaries |
| AC3 | D1 | Each artifact visually indicates pipeline stage via nesting under stage header |
| AC4 | D1, D3 | Temporal sequence apparent through stage ordering and timestamps |
| AC5 | D3 | Completed stage displays completion timestamp |
| AC6 | D4 | Each artifact displays created-or-last-modified timestamp from file mtime |
| AC7 | D6 | Users can collapse any stage section they are not interested in |
| AC8 | D6 | Collapsed sections remain collapsed until user explicitly expands them (localStorage) |
| AC9 | D5 | Page loads without rendering all artifact content upfront |
| AC10 | D5 | Initial page load faster because artifact content is deferred to AJAX |
| AC11 | D1 | Intake stage contains: User Request, Clause Register, 5 Whys Analysis |
| AC12 | D1 | Requirements stage contains: Structured Requirements document |
| AC13 | D1 | Planning stage contains: Design Document, YAML Plan |
| AC14 | D1 | Execution stage contains: per-task results, validation reports |
| AC15 | D1 | Verification stage appears only for defects, contains final verification report |
| AC16 | D1 | Archive stage contains: completion status, outcome |
| AC17 | D1 | Stages presented in order: Intake, Requirements, Planning, Execution, Verification, Archive |
| AC18 | D2 | Each stage displays status: not started, in progress, or done |
| AC19 | D3 | Each stage section shows its completion timestamp |
| AC20 | D1 | Artifacts nested under their parent stage |
| AC21 | D4 | Each artifact within a stage displays created-or-last-modified timestamp |
| AC22 | D6 | Each stage section can be collapsed and expanded by the user |
| AC23 | D5 | Artifact contents fetched only when parent stage is expanded |
| AC24 | D5 | Page loads without fetching all artifact content upfront |
| AC25 | D5 | Expanding a stage loads artifacts without a full page refresh |
| AC26 | D7 | Label "Raw Input" replaced with "User Request" in Intake stage |
| AC27 | D7 | Underlying data still references same artifact content after rename |

---

## Design Competition Judgment

### Scoring Matrix

| Design | Alignment | Completeness | Feasibility | Integration | Clarity | Total |
|--------|-----------|--------------|-------------|-------------|---------|-------|
| Design 1 - Systems Architecture (0.1) | 10 | 9 | 10 | 10 | 9 | 48 |
| Design 2 - UX Design (0.2) | 8 | 8 | 9 | 9 | 10 | 44 |
| Design 3 - Frontend Implementation (0.3) | 6 | 4 | 7 | 7 | 5 | 29 |

### Winner: Design 1 - Systems Architecture (48/50)

Design 1 provides the most comprehensive and implementation-ready specification covering
all 27 acceptance criteria. Its data models (StageInfo/ArtifactInfo), build_stages()
three-pass algorithm, status computation matrix, /dynamic API extension, and artifact-to-stage
mapping table give implementers a complete blueprint. UX visual hierarchy, loading spinner
CSS, and responsive breakpoints from Design 2 should be incorporated into the implementation.

Full judgment: tmp/worker-output/74-item-page-step-explorer-judgment.md
