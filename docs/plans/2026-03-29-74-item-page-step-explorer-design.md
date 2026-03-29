# Design: 74 Item Page Step Explorer

Source: tmp/plans/.claimed/74-item-page-step-explorer.md
Requirements: docs/plans/2026-03-29-74-item-page-step-explorer-requirements.md

## Architecture Overview

The item detail page is restructured from a flat two-column layout into a
stage-based step explorer. A new server-side data model groups all work item
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
| langgraph_pipeline/web/routes/item.py | Modify: add stage data model, stage builder, extend /dynamic |
| langgraph_pipeline/web/templates/item.html | Modify: replace two-column layout with step explorer accordion |

---

## Design Decisions

### D1: Stage-based artifact grouping data model

Addresses: P1, FR1, UC1
Satisfies: AC1, AC7, AC8, AC16, AC17, AC18, AC19, AC20, AC21

Approach: Define a StageInfo TypedDict and an ArtifactInfo TypedDict in item.py.
A build_stages() function maps existing artifact discovery results (raw request,
clause register, five whys, structured requirements, design doc, plan YAML,
per-task results, validation reports, verification report, completion record)
into six ordered StageInfo dicts. The Verification stage is omitted when the
item type is "feature" (no verification for features). Each stage has a list
of artifacts with display name, file path (for lazy fetch), and timestamp.

The six stages and their artifact mappings:

1. Intake: User Request (raw_request), clause register, 5 whys analysis
2. Requirements: structured requirements document
3. Planning: design document, YAML plan
4. Execution: per-task results (output files), validation results
5. Verification: final verification report (defects only)
6. Archive: completion status/outcome

Files: langgraph_pipeline/web/routes/item.py

### D2: Stage status computation

Addresses: FR2
Satisfies: AC22

Approach: Each stage's status is computed as one of three values: "not_started",
"in_progress", or "done". The logic uses the item's pipeline_stage (already
computed by _derive_pipeline_stage()) and artifact presence:

- A stage is "done" when all its expected artifacts exist
- A stage is "in_progress" when it matches the current pipeline phase
- A stage is "not_started" when the pipeline has not yet reached it

The _derive_pipeline_stage() returns 8 states (queued, unknown, claimed,
designing, planning, executing, validating, completed, stuck). These map to
the six UI stages as follows:

- queued/unknown -> all stages not_started
- claimed (no plan) -> intake in_progress
- designing/planning -> planning in_progress (intake, requirements done)
- executing -> execution in_progress (intake, requirements, planning done)
- validating -> verification in_progress (earlier stages done)
- completed -> all stages done (archive done)
- stuck -> status based on which artifacts exist

Files: langgraph_pipeline/web/routes/item.py

### D3: Timestamps on stages and artifacts

Addresses: P2, UC3
Satisfies: AC3, AC4, AC13, AC14, AC15

Approach: Each artifact's timestamp is its file modification time (os.path.getmtime),
formatted as a human-readable relative or absolute string. Each stage's
completion timestamp is the latest mtime among its artifacts (only shown when
stage status is "done"). Stages that have not completed show no timestamp
(the template omits the timestamp element).

For artifacts discovered through the artifact manifest, the manifest's
recorded timestamp is preferred over file mtime.

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D4: Collapsible stage accordion with persistence

Addresses: P3, UC2
Satisfies: AC2, AC5, AC6, AC9, AC11, AC12

Approach: Each stage renders as a section with a clickable header that toggles
the body visibility. A CSS class "collapsed" on the stage container hides the
body. JavaScript manages toggle and persists the open/closed state of each
stage in localStorage keyed by slug + stage name, so collapse state survives
page reloads and interactions with other stages.

The most recent active stage defaults to expanded on first visit; all others
default to collapsed. Subsequent visits restore the persisted state.

Visual hierarchy: stage headers use larger font, bold text, status badge, and
timestamp. Artifact items are indented and use smaller font, creating a clear
parent-child relationship.

Files: langgraph_pipeline/web/templates/item.html

### D5: On-demand artifact loading

Addresses: FR3
Satisfies: AC10, AC23, AC24

Approach: At page load, the template renders only stage headers and artifact
metadata (name, timestamp) but not artifact content. When a user expands a
stage, JavaScript fetches each artifact's content via the existing
/item/{slug}/artifact-content?path={path} endpoint. A loading indicator is
shown during fetch. Fetched content is cached in a JS Map so re-expanding
a stage does not re-fetch.

The /dynamic endpoint is extended to include the stages array so live polling
can update stage statuses and add new artifacts as they appear.

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D6: Rename Raw Input to User Request

Addresses: FR4
Satisfies: AC25, AC26

Approach: The artifact display name for the original backlog file is changed
from "Raw Input" to "User Request" in the build_stages() function. The label
"Raw Input" is removed from all template text and heading references. The
underlying file path and data key (original_request) remain unchanged to
avoid breaking the data layer.

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

---

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | Artifacts grouped into six pipeline stage sections |
| AC2 | D4 | Visual hierarchy via stage headers with indent/nesting for artifacts |
| AC3 | D3 | Completed stages show completion timestamp (latest artifact mtime) |
| AC4 | D3 | Each artifact displays its file mtime timestamp |
| AC5 | D4 | Stage sections collapse via clickable header toggle |
| AC6 | D4 | Collapsed stages expand on click to reveal artifacts |
| AC7 | D1 | Step explorer with stages rendered in pipeline order |
| AC8 | D1 | build_stages() enforces Intake-Requirements-Planning-Execution-Verification-Archive order |
| AC9 | D4 | Collapsed irrelevant stages allow direct access to expanded stage |
| AC10 | D5 | AJAX lazy loading fetches only expanded stage artifacts |
| AC11 | D4, D2, D3 | Each stage is collapsible, shows name + status + timestamp + nested artifacts |
| AC12 | D4 | Collapsed stages eliminate scrolling past hidden content |
| AC13 | D3 | Stage completion timestamp from latest artifact mtime when done |
| AC14 | D3 | Artifacts nested under stages with individual timestamps |
| AC15 | D3 | Artifact timestamp shows created-or-last-modified time |
| AC16 | D1 | Intake stage maps: User Request, clause register, 5 whys |
| AC17 | D1 | Requirements stage maps: structured requirements document |
| AC18 | D1 | Planning stage maps: design document, YAML plan |
| AC19 | D1 | Execution stage maps: per-task results, validation reports |
| AC20 | D1 | Verification stage maps: final verification report (defects only) |
| AC21 | D1 | Archive stage maps: completion status, outcome |
| AC22 | D2 | Three-state status indicator (not_started / in_progress / done) |
| AC23 | D5 | Content fetched on-demand when stage expanded |
| AC24 | D5 | Initial page load renders only headers and metadata, no artifact content |
| AC25 | D6 | "User Request" label in build_stages() for raw input artifact |
| AC26 | D6 | No "Raw Input" label references remain in user-facing pages |
