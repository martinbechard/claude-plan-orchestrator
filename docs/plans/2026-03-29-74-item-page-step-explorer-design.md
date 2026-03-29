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
| langgraph_pipeline/web/routes/item.py | Modify: add stage data model, stage builder, stage-based API |
| langgraph_pipeline/web/templates/item.html | Modify: replace two-column layout with step explorer accordion |

---

## Design Decisions

### D1: Stage-based artifact grouping data model

Addresses: P1, FR1
Satisfies: AC1, AC5, AC6, AC7, AC8, AC9, AC10, AC11, AC12, AC13

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

Addresses: FR2, P2
Satisfies: AC2, AC14, AC15

Approach: Each stage's status is computed as one of three values: "not_started",
"in_progress", or "done". The logic uses the item's pipeline_stage (already
computed by _derive_pipeline_stage()) and artifact presence:

- A stage is "done" when all its expected artifacts exist
- A stage is "in_progress" when it matches the current pipeline phase
- A stage is "not_started" when the pipeline has not yet reached it

The pipeline_stage string maps to stage phases:
- queued/unknown -> all stages not_started
- intake/claimed (no plan) -> intake in_progress
- designing/planning -> planning in_progress (intake, requirements done)
- executing -> execution in_progress (intake, requirements, planning done)
- validating -> verification in_progress (earlier stages done)
- completed -> all stages done (archive done)

Files: langgraph_pipeline/web/routes/item.py

### D3: Timestamps on stages and artifacts

Addresses: FR3
Satisfies: AC3, AC16, AC17, AC18, AC19

Approach: Each artifact's timestamp is its file modification time (os.path.getmtime),
formatted as a human-readable relative or absolute string. Each stage's
completion timestamp is the latest mtime among its artifacts (only shown when
stage status is "done"). Stages that have not completed show no timestamp
(the template omits the timestamp element).

For artifacts discovered through the artifact manifest, the manifest's
recorded timestamp is preferred over file mtime.

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D4: Collapsible stage accordion with persistence

Addresses: UC1, P2
Satisfies: AC4, AC22, AC23

Approach: Each stage renders as a section with a clickable header that toggles
the body visibility. A CSS class "collapsed" on the stage container hides the
body. JavaScript manages toggle and persists the open/closed state of each
stage in localStorage keyed by slug + stage name, so collapse state survives
page reloads and interactions with other stages.

The most recent active stage defaults to expanded on first visit; all others
default to collapsed. Subsequent visits restore the persisted state.

Files: langgraph_pipeline/web/templates/item.html

### D5: On-demand artifact loading

Addresses: FR4
Satisfies: AC20, AC21

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

Addresses: FR5
Satisfies: AC24, AC25

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
| AC1 | D1 | Artifacts grouped into stage sections instead of flat page |
| AC2 | D2, D4 | Visual hierarchy via stage headers with status indicators |
| AC3 | D3 | Timestamps displayed on completed stages and artifacts |
| AC4 | D4 | Collapsible stage sections with toggle and persistence |
| AC5 | D1 | Step explorer with stages in chronological order |
| AC6 | D1 | Six stages in specified order enforced by build_stages() |
| AC7 | D1 | Intake stage contains User Request, clause register, 5 whys |
| AC8 | D1 | Requirements stage contains structured requirements |
| AC9 | D1 | Planning stage contains design doc and YAML plan |
| AC10 | D1 | Execution stage contains per-task results and validation |
| AC11 | D1 | Verification stage contains final verification report |
| AC12 | D1 | Verification stage omitted for feature items |
| AC13 | D1 | Archive stage contains completion status and outcome |
| AC14 | D2 | Stage name and three-state status indicator displayed |
| AC15 | D2 | Status derived from pipeline state reflects actual progress |
| AC16 | D3 | Completed stages show completion timestamp |
| AC17 | D3 | Incomplete stages omit timestamp |
| AC18 | D3 | Artifacts nested under stages with individual timestamps |
| AC19 | D3 | Each artifact shows created-or-last-modified timestamp |
| AC20 | D5 | No artifact content in initial page load |
| AC21 | D5 | Content fetched on stage expand via AJAX |
| AC22 | D4 | User can expand collapsed stages to see artifacts |
| AC23 | D4 | Collapse state persists via localStorage across interactions |
| AC24 | D6 | "Raw Input" renamed to "User Request" in Intake stage |
| AC25 | D6 | "Raw Input" label removed from all artifact labels |
