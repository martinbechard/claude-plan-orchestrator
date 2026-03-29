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

## Data Model

### ArtifactInfo TypedDict

Represents a single discoverable artifact within a stage.

```
class ArtifactInfo(TypedDict):
    name: str              # Display name (e.g. "User Request", "Clause Register")
    path: str              # Relative file path for lazy content fetch
    timestamp: float       # File mtime (epoch seconds) for display
    timestamp_display: str # Pre-formatted relative or absolute time string
```

Fields:
- name: Human-readable label shown in the UI. Uses "User Request" (not "Raw
  Input") per FR1/AC8.
- path: Relative path from project root, passed to the existing
  /item/{slug}/artifact-content?path= endpoint for on-demand loading.
- timestamp: Raw epoch float from os.path.getmtime(), used for sorting and
  computing stage completion timestamps.
- timestamp_display: Pre-formatted string for Jinja2 rendering. Format:
  "YYYY-MM-DD HH:MM" (local time). Server-side formatting avoids the need
  for client-side date logic.

### StageInfo TypedDict

Represents one pipeline stage containing zero or more artifacts.

```
class StageInfo(TypedDict):
    id: str                          # Machine-readable key (e.g. "intake")
    name: str                        # Display name (e.g. "Intake")
    status: str                      # "not_started" | "in_progress" | "done"
    artifacts: list[ArtifactInfo]    # Ordered list of artifacts in this stage
    completion_ts: Optional[str]     # Formatted timestamp when done, None otherwise
    completion_epoch: Optional[float] # Raw epoch for JSON serialization
```

Fields:
- id: Lowercase stage identifier used as a CSS class suffix, localStorage key
  component, and JSON field name. One of: "intake", "requirements", "planning",
  "execution", "verification", "archive".
- name: Title-case display label for the accordion header.
- status: One of three string literals. Computed from pipeline_stage mapping
  and artifact presence (see Stage Status Computation below).
- artifacts: List of ArtifactInfo dicts. Empty list when no artifacts exist
  for a stage (the stage still renders with "No artifacts" text).
- completion_ts: Formatted timestamp string (same format as artifact timestamps)
  derived from the latest artifact mtime in the stage. Only populated when
  status is "done". None otherwise.
- completion_epoch: Raw epoch float for the /dynamic JSON response (the
  frontend may use this for relative time formatting in future iterations).

### Stage Ordering Constant

```
STAGE_ORDER: list[tuple[str, str]] = [
    ("intake", "Intake"),
    ("requirements", "Requirements"),
    ("planning", "Planning"),
    ("execution", "Execution"),
    ("verification", "Verification"),
    ("archive", "Archive"),
]
```

This constant enforces AC9 (fixed pipeline order) and is the single source
of truth for stage identity and display names.

---

## build_stages() Function

### Signature

```
def build_stages(
    slug: str,
    item_type: Optional[str],
    pipeline_stage: str,
) -> list[StageInfo]:
```

### Algorithm

The function performs three passes:

**Pass 1: Discover artifacts per stage**

Each stage has a fixed set of artifact discovery calls that reuse existing
helper functions from item.py:

Stage: intake
  - "User Request": _find_original_request_file(slug) -> path or None
  - "Clause Register": ws_path_fn(slug) / "clauses.md" -> check .exists()
  - "5 Whys Analysis": ws_path_fn(slug) / "five-whys.md" -> check .exists()

Stage: requirements
  - "Structured Requirements": _find_structured_requirements_file(slug) -> path or None

Stage: planning
  - "Design Document": _find_design_doc(slug) -> path or None
  - "YAML Plan": _find_plan_yaml(slug) -> path or None

Stage: execution
  - "Output Files": iterate _list_output_files(slug), each file becomes an
    ArtifactInfo with path = WORKER_OUTPUT_DIR / slug / filename
  - "Validation Results": iterate ws_path_fn(slug) / "validation" / "validation-*.json",
    each file becomes an ArtifactInfo

Stage: verification (omitted when item_type == "feature", per D1/AC5)
  - "Verification Report": ws_path_fn(slug) / "verification-report.md" -> check .exists()
  - Also check WORKER_OUTPUT_DIR / slug for verification-report.md

Stage: archive
  - "Completion Record": for each dir in COMPLETED_DIRS.values(), check
    Path(dir) / f"{slug}.md" -> first match becomes the artifact

For each discovered file, create an ArtifactInfo with:
  - name: the label above
  - path: str(file_path) (relative to project root)
  - timestamp: file_path.stat().st_mtime (wrapped in try/except, default 0.0)
  - timestamp_display: formatted from timestamp

**Pass 2: Compute stage status**

For each stage, apply the status computation matrix (see below) using the
pipeline_stage argument and whether artifacts list is non-empty.

**Pass 3: Compute completion timestamps**

For each stage where status == "done" and artifacts is non-empty:
  - completion_epoch = max(a["timestamp"] for a in artifacts)
  - completion_ts = format_timestamp(completion_epoch)

For stages where status != "done":
  - completion_epoch = None
  - completion_ts = None

### Return Value

Returns the list of StageInfo dicts in STAGE_ORDER sequence, skipping the
verification stage when item_type == "feature".

---

## Stage Status Computation

The status of each stage is derived from the item's pipeline_stage (already
computed by _derive_pipeline_stage()) using a deterministic mapping.

### Pipeline Stage to Stage Status Matrix

```
pipeline_stage     | intake       | requirements | planning     | execution    | verification | archive
-------------------|--------------|--------------|--------------|--------------|--------------|--------
queued             | not_started  | not_started  | not_started  | not_started  | not_started  | not_started
unknown            | not_started  | not_started  | not_started  | not_started  | not_started  | not_started
claimed            | in_progress  | not_started  | not_started  | not_started  | not_started  | not_started
designing          | done*        | done*        | in_progress  | not_started  | not_started  | not_started
planning           | done*        | done*        | in_progress  | not_started  | not_started  | not_started
executing          | done*        | done*        | done*        | in_progress  | not_started  | not_started
validating         | done*        | done*        | done*        | done*        | in_progress  | not_started
completed          | done         | done         | done         | done         | done**       | done
stuck              | (artifact)   | (artifact)   | (artifact)   | (artifact)   | (artifact)   | not_started
```

Notes:
- "done*" means done IF the stage has at least one artifact, otherwise
  in_progress. This handles edge cases where a stage might be passed through
  without producing artifacts.
- "done**" for verification in completed state: done if item_type is "defect"
  (and verification artifacts exist), stage is omitted entirely for "feature".
- "stuck" uses artifact-based fallback: a stage is "done" if it has artifacts,
  "in_progress" for the first stageless stage, and "not_started" for later
  stages. This ensures stuck items still show progress up to the point of
  failure.

### Implementation Pattern

```
def _compute_stage_statuses(
    stages: list[StageInfo],
    pipeline_stage: str,
) -> None:
    """Mutate stages in place to set status fields."""
```

The function uses a lookup dict mapping pipeline_stage to a list of expected
statuses per stage index, then applies the artifact-presence adjustment for
"done*" entries.

---

## /dynamic Endpoint Extension

### Current Response Shape

The /item/{slug}/dynamic endpoint returns JSON used by the polling script to
update the page without full reload. Current fields:

```
{
    "pipeline_stage": str,
    "active_worker": dict | null,
    "total_cost_usd": float,
    "total_duration_s": float,
    "total_tokens": int,
    "avg_velocity": float | null,
    "plan_tasks": list | null,
    "validation_results": list
}
```

### Extended Response Shape

Add a "stages" field containing the stage status summary (without full artifact
details, to keep the polling payload lightweight):

```
{
    ... existing fields ...,
    "stages": [
        {
            "id": "intake",
            "status": "done",
            "completion_ts": "2026-03-29 14:23",
            "completion_epoch": 1743267780.0,
            "artifact_count": 3
        },
        {
            "id": "requirements",
            "status": "in_progress",
            "completion_ts": null,
            "completion_epoch": null,
            "artifact_count": 1
        },
        ...
    ]
}
```

Each stage summary includes:
- id: Stage identifier for matching DOM elements
- status: Current status string
- completion_ts: Formatted completion timestamp or null
- completion_epoch: Raw epoch or null
- artifact_count: Number of discovered artifacts (allows the frontend to
  detect when new artifacts appear and trigger a content re-fetch)

### Implementation

In item_dynamic(), after computing pipeline_stage:

```
stages = build_stages(slug, item_type, pipeline_stage)
stage_summaries = [
    {
        "id": s["id"],
        "status": s["status"],
        "completion_ts": s["completion_ts"],
        "completion_epoch": s["completion_epoch"],
        "artifact_count": len(s["artifacts"]),
    }
    for s in stages
]
```

Add "stages": stage_summaries to the response dict. The item_type detection
(_detect_item_type) is called in item_dynamic() since it is needed for
build_stages() and was not previously called there.

---

## On-Demand Content Loading Architecture

### Page Load (Server-Side)

At initial render, item_detail() calls build_stages() and passes the stages
list to the Jinja2 template context. The template renders:

- Stage headers with name, status badge, completion timestamp
- Artifact metadata rows (name, timestamp) under each stage
- Empty content containers (hidden pre elements) for each artifact

No artifact content is fetched or embedded at page load time (AC14, AC23, AC24).

### Content Fetch (Client-Side)

When a user expands a collapsed stage:

1. JavaScript iterates the artifact elements within the stage
2. For each artifact whose content has not been fetched (check data-loaded attr):
   a. Show a "Loading..." indicator in the pre container
   b. Fetch /item/{slug}/artifact-content?path={artifact.path}
   c. On success: populate pre with response text, set data-loaded="1"
   d. On error: show "Failed to load content" message
3. Cache: once fetched, content stays in the DOM (data-loaded flag). Collapsing
   and re-expanding does not re-fetch.

### Content Cache Strategy

The existing artifact viewer in item.html already uses a data-loaded attribute
pattern for on-demand fetch caching. The step explorer reuses this same pattern.
No JS Map cache is needed -- the DOM itself serves as the cache via the
data-loaded flag on each pre element.

### Live Updates via /dynamic Polling

The existing polling script (10-second interval) is extended to:

1. Read the "stages" array from the /dynamic response
2. For each stage in the response:
   a. Update the status badge CSS class and text
   b. Update or show/hide the completion timestamp
   c. If artifact_count increased since last poll: mark affected pre
      elements as data-loaded="" (clearing the cache) so the next expansion
      triggers a fresh fetch

The polling does NOT fetch artifact content -- it only updates stage metadata.
Content fetches happen on user-initiated stage expansion.

### Integration with item_detail()

The item_detail() function is modified to:

1. Call build_stages(slug, item_type, pipeline_stage) after deriving
   pipeline_stage and item_type
2. Pass "stages" to the template context
3. The existing per-section rendering (original_request_html,
   clause_register_html, etc.) remains available but the template no longer
   uses them inline -- instead the step explorer's on-demand fetch replaces
   the pre-rendered HTML approach

The individual _load_*_html() calls in item_detail() can be removed once
the step explorer is fully wired, since the template will fetch content
via artifact-content endpoint instead. However, these helpers should be
retained during the transition and removed only after the step explorer
is confirmed working.

---

## Data Flow Summary

```
Page Load:
  item_detail(slug)
    -> _derive_pipeline_stage(slug, completions)
    -> _detect_item_type(slug)
    -> build_stages(slug, item_type, pipeline_stage)
       -> discovers artifacts using existing helpers
       -> computes status per stage
       -> computes completion timestamps
    -> template renders stage headers + artifact metadata (no content)

User Expands Stage:
  click event -> JS toggles stage visibility
    -> for each un-fetched artifact:
       fetch /item/{slug}/artifact-content?path={path}
       -> render content into DOM pre element

Live Polling (every 10s):
  fetch /item/{slug}/dynamic
    -> response includes "stages" summary array
    -> JS updates status badges and timestamps in DOM
    -> JS detects new artifacts (artifact_count change)
       -> clears data-loaded on affected artifacts for next expansion
```

---

## Design Decisions

### D1: Stage-based artifact grouping data model

Addresses: P1, FR1
Satisfies: AC1, AC2, AC3, AC4, AC5, AC6, AC9, AC11, AC15, AC17

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

The STAGE_ORDER constant enforces chronological pipeline ordering (AC9) and
serves as the single source of truth for stage identity and display names.
Artifacts are nested under their parent stage (AC11), and the grouping makes
it clear which stage produced each artifact (AC15, AC17).

Files: langgraph_pipeline/web/routes/item.py

### D2: Stage status computation

Addresses: FR1
Satisfies: AC7

Approach: Each stage's status is computed as one of three values: "not_started",
"in_progress", or "done". The logic uses the item's pipeline_stage (already
computed by _derive_pipeline_stage()) and artifact presence:

- A stage is "done" when all its expected artifacts exist
- A stage is "in_progress" when it matches the current pipeline phase
- A stage is "not_started" when the pipeline has not yet reached it

The _derive_pipeline_stage() returns 9 states (queued, unknown, claimed,
designing, planning, executing, validating, completed, stuck). These map to
the six UI stages via a lookup matrix. The "stuck" state uses artifact-based
fallback to show progress up to the point of failure.

Files: langgraph_pipeline/web/routes/item.py

### D3: Timestamps on stages and artifacts

Addresses: P2
Satisfies: AC10, AC11, AC12, AC18, AC19

Approach: Each artifact's timestamp is its file modification time (os.path.getmtime),
formatted as "YYYY-MM-DD HH:MM" (local time). Each stage's completion timestamp
is the latest mtime among its artifacts (only shown when stage status is "done").
Stages that have not completed show no timestamp (the template omits the timestamp
element). Server-side formatting avoids client-side date logic.

The combination of stage completion timestamps (AC10) and per-artifact timestamps
(AC12) allows users to determine the temporal order of work (AC19). Timestamps
appear on both stages and artifacts (AC18), and artifacts are nested under their
parent stage with their own timestamps (AC11).

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D4: Collapsible stage accordion with persistence

Addresses: P3, UC1
Satisfies: AC9, AC16, AC20, AC21, AC22, AC25, AC26

Approach: Each stage renders as a section with a clickable header that toggles
the body visibility. A CSS class "collapsed" on the stage container hides the
body. JavaScript manages toggle and persists the open/closed state of each
stage in localStorage keyed by slug + stage name, so collapse state survives
page reloads and interactions with other stages.

The most recent active stage defaults to expanded on first visit; all others
default to collapsed. Subsequent visits restore the persisted state.

Visual hierarchy: stage headers use larger font, bold text, status badge, and
timestamp. Artifact items are indented and use smaller font, creating a clear
parent-child relationship (AC16). Users can collapse (AC20) and expand (AC21)
individual stage sections independently (AC25), enabling task-focused navigation
(AC26). Collapsed sections eliminate scrolling past hidden content (AC22).
The accordion enforces the six-stage chronological order (AC9).

Files: langgraph_pipeline/web/templates/item.html

### D5: On-demand artifact loading

Addresses: P4, FR2
Satisfies: AC13, AC14, AC23, AC24

Approach: At page load, the template renders only stage headers and artifact
metadata (name, timestamp) but not artifact content. When a user expands a
stage, JavaScript fetches each artifact's content via the existing
/item/{slug}/artifact-content?path={path} endpoint. A loading indicator is
shown during fetch. Fetched content is cached via a data-loaded DOM attribute
so re-expanding a stage does not re-fetch.

Artifacts are loaded only when their parent stage is expanded (AC13). The
initial page load avoids fetching artifact content (AC14), rendering quickly
(AC23) and keeping the initial view manageable even for items with many
accumulated artifacts (AC24).

The /dynamic endpoint is extended to include a stages array so live polling
can update stage statuses and detect new artifacts without fetching content.

Files: langgraph_pipeline/web/routes/item.py, langgraph_pipeline/web/templates/item.html

### D6: Rename Raw Input to User Request

Addresses: FR1
Satisfies: AC8

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
| AC1 | D1 | Intake stage maps: User Request, clause register, 5 whys analysis |
| AC2 | D1 | Requirements stage maps: structured requirements document |
| AC3 | D1 | Planning stage maps: design document, YAML plan |
| AC4 | D1 | Execution stage maps: per-task results, validation reports |
| AC5 | D1 | Verification stage maps: final verification report (defects only) |
| AC6 | D1 | Archive stage maps: completion status, outcome |
| AC7 | D2 | Three-state status indicator (not_started / in_progress / done) per stage |
| AC8 | D6 | "User Request" label in build_stages() for raw input artifact |
| AC9 | D1, D4 | STAGE_ORDER constant enforces six-stage order; accordion renders collapsible sections |
| AC10 | D3 | Stage completion timestamp from latest artifact mtime when status is done |
| AC11 | D1, D3 | Artifacts nested under parent stage, each with its own timestamp |
| AC12 | D3 | Each artifact displays file mtime as creation/modification timestamp |
| AC13 | D5 | AJAX lazy loading fetches only when parent stage is expanded |
| AC14 | D5 | Initial page load renders headers and metadata only, no artifact content |
| AC15 | D1 | Artifacts grouped into six pipeline stage sections instead of flat list |
| AC16 | D4 | Stage headers use larger font/bold; artifacts indented with smaller font |
| AC17 | D1 | Each artifact is visually nested under its producing stage |
| AC18 | D3 | Timestamps displayed on both stages (completion) and artifacts (mtime) |
| AC19 | D3 | Chronological stage order plus per-artifact timestamps show temporal sequence |
| AC20 | D4 | Click stage header to collapse and hide artifacts |
| AC21 | D4 | Click collapsed stage header to expand and reveal artifacts |
| AC22 | D4 | Collapsed stages eliminate scrolling; user reaches target section directly |
| AC23 | D5 | Content fetched on-demand when stage expanded; page loads quickly |
| AC24 | D5 | Initial page renders only metadata; not overwhelming with many artifacts |
| AC25 | D4 | Independent expand/collapse per stage; expanding one does not affect others |
| AC26 | D4 | User views one or few stages at a time while others remain collapsed |
