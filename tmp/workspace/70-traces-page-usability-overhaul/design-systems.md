# Systems Architecture Design: Traces Page Usability Overhaul

## 1. Executive Summary

This proposal addresses the traces page overhaul from a systems architecture perspective,
covering data architecture, component hierarchy, API boundaries, and template structure
for both the list page (proxy_list.html) and the detail/narrative page (proxy_narrative.html).

The core architectural insight is that the existing data layer already has correct batch
queries but the presentation layer fails to use them properly.  The fix requires surgical
changes to the enrichment pipeline and template data contracts, not a ground-up rebuild.

## 2. Current Architecture Analysis

### 2.1 Three-Layer Architecture

```
[SQLite DB]
    |
    v
[TracingProxy]         -- Data layer: batch queries, CRUD, cost CTEs
    |
    v
[Route Handlers]       -- Business layer: enrichment, context assembly
    |
    v
[Jinja2 Templates]     -- Presentation layer: HTML rendering
```

### 2.2 Data Flow: List Page

```
proxy_list() route handler:
  1. proxy.list_runs()              -> raw_runs: list[dict]
  2. proxy.get_child_time_spans_batch()  -> {run_id: ChildTimeSpan}
  3. proxy.get_child_costs_batch()       -> {run_id: float}
  4. proxy.get_child_models_batch()      -> {run_id: str}
  5. proxy.get_child_slugs_batch()       -> {run_id: str}
  6. _enrich_run(run, child_agg)    -> enriched run with display_* fields
  7. proxy.count_children_batch()   -> {run_id: int}
  8. Template receives: runs, groups, grouped, pagination, filters
```

### 2.3 Data Flow: Narrative Page

```
proxy_narrative() route handler:
  1. proxy.get_run(run_id)              -> root run dict
  2. proxy.get_children(run_id)         -> children: list[dict]
  3. proxy.count_children_batch()       -> grandchild counts
  4. proxy.get_children_batch()         -> grandchildren by parent
  5. build_execution_view(run, children, grandchildren)
       -> ExecutionView (item_slug, total_duration, total_cost, phases[])
  6. _find_worker_logs(slug)            -> matching log filenames
  7. Template receives: run, view, worker_logs
```

### 2.4 Identified Architectural Issues

| Issue | Root Cause | Layer |
|-------|-----------|-------|
| Duration shows 0.01s | Root span timestamps used instead of child-aggregated span | Enrichment (_enrich_run) |
| Cost shows dashes | metadata_json cost fields empty on root runs; child CTE cost not surfaced | Enrichment + Data |
| Model shows dashes | Root model field empty; child model query only checks direct children | Data query scope |
| Names show "LangGraph" | Old root runs never backfilled from child metadata | Data (needs migration) |
| "Item slug" column redundant | display_slug duplicates run name; no type badge | Template |
| Title says "LangSmith Traces" | Hard-coded developer jargon | Template |
| Phases duplicated | Children with same phase name not merged | Narrative builder |
| Phase names show "Unknown" | _PHASE_PATTERNS missing entries for verify_fix etc. | Narrative classifier |
| No operational detail | Phases only show PASS with no file/command counts | Narrative builder |
| No artifact links | Worker logs, design docs, validation results not linked | Template + Narrative |
| No raw trace toggle | Separate page link instead of inline toggle | Template |

## 3. Proposed Architecture

### 3.1 Component Hierarchy

```
base.html
  |
  +-- proxy_list.html          (List Page)
  |     |
  |     +-- Macro: run_row()           -- Single run row
  |     +-- Macro: status_badge()      -- Status indicator
  |     +-- Macro: type_badge()        -- NEW: defect/feature badge
  |     +-- Macro: outcome_badge()     -- NEW: pass/fail/running
  |     +-- Filter bar component       -- Slug, model, date filters
  |     +-- Pagination component
  |     +-- Group toggle + grouped table variant
  |
  +-- proxy_narrative.html     (Detail Page)
        |
        +-- Header card component      -- Item name, status, duration, cost
        +-- Links bar component        -- NEW: work item, design, logs, git
        +-- Phase timeline component
        |     +-- Phase card component (per phase)
        |           +-- Phase header (summary metrics)
        |           +-- Phase body (expandable)
        |                 +-- Activity pills
        |                 +-- File detail groups
        |                 +-- Bash command list
        |                 +-- Artifact links
        +-- Raw trace toggle           -- REVISED: inline JSON, not separate page
```

### 3.2 Data Architecture Changes

#### 3.2.1 New Data Types

```python
@dataclass
class ItemTypeBadge:
    """Type classification for a work item (defect vs feature)."""
    item_type: str      # "defect" | "feature" | "unknown"
    css_class: str      # "badge-defect" | "badge-feature" | "badge-unknown"
    label: str          # "Defect" | "Feature" | ""

@dataclass
class OutcomeBadge:
    """Outcome classification for a completed run."""
    outcome: str        # "pass" | "fail" | "running" | "stale" | "unknown"
    css_class: str      # maps to badge CSS classes
    label: str          # human-readable label
```

#### 3.2.2 Enhanced Enrichment Contract

The _enrich_run() function currently produces these display_* fields:
- display_duration, display_slug, display_model, display_cost, display_status

Proposed additions:
- display_item_type: str           -- "defect" | "feature" | "unknown"
- display_outcome: str             -- "pass" | "fail" | "running" | "stale"
- display_start_time: str          -- Pre-formatted local-friendly timestamp
- display_trace_id_short: str      -- First 8 chars of run_id

The item type can be inferred from metadata_json fields (item_type key) or from
the slug pattern.  Defects typically have numeric prefixes (e.g. "01-fix-login"),
features use descriptive names.

#### 3.2.3 Backfill Strategy (D2, D3)

Two new methods on TracingProxy, called once during init:

```
backfill_root_run_slugs():
    For root runs where name = 'LangGraph':
    1. Use existing _CHILD_SLUGS_BATCH_SQL pattern on these run_ids
    2. UPDATE name = resolved_slug, metadata_json slug field
    3. Idempotent: only touches rows where name = 'LangGraph'

backfill_stale_status():
    For root runs with no end_time:
    1. Find those whose children all have end_time set
    2. SET end_time = MAX(children.end_time)
    3. Infer status from child error presence
    4. Idempotent: only touches rows with NULL end_time
```

Both are write-once operations that fix historical data.  New traces are
recorded correctly by the existing create_root_run() which already uses
the item slug.

### 3.3 API Boundaries

#### 3.3.1 Route Handler -> Template Contract

**List Page Template Context:**

```python
# Current context keys (unchanged)
context = {
    "runs": list[dict],         # enriched run dicts
    "groups": list[RunGroup],   # grouped runs (when group=1)
    "grouped": bool,
    "group": int,
    "page": int,
    "total_pages": int,
    "slug": str,
    "model": str,
    "date_from": str,
    "date_to": str,
    "trace_id": str,
}

# Each run dict gains these display_* fields from enhanced _enrich_run:
run = {
    # Existing fields (from DB)
    "run_id": str,
    "name": str,
    "start_time": str,
    "end_time": str,
    "metadata_json": str,
    "error": str,
    "model": str,
    "child_count": int,

    # Existing display fields (from _enrich_run)
    "display_duration": str,       # e.g. "5m 23s"
    "display_slug": str,           # resolved item name
    "display_model": str,          # e.g. "opus"
    "display_cost": str,           # e.g. "$0.1234"
    "display_status": str,         # "completed" | "error" | "stale" | "running"

    # NEW display fields
    "display_item_type": str,      # "defect" | "feature" | "unknown"
}
```

**Narrative Page Template Context:**

```python
context = {
    "run": dict,                # enriched root run
    "view": ExecutionView,      # phase-level data
    "worker_logs": list[str],   # log filenames
    # NEW context fields:
    "artifact_links": ArtifactLinks,  # resolved URLs for header links
    "raw_trace_json": str,      # pre-serialized JSON for inline toggle
}

# ArtifactLinks dataclass
@dataclass
class ArtifactLinks:
    work_item_url: str          # "/item/{slug}" or ""
    design_doc_path: str        # path to design doc or ""
    worker_log_paths: list[str] # full paths to log files
    validation_report: str      # path or ""
    git_log_url: str            # link to filtered git log or ""
    raw_trace_url: str          # "/proxy/{run_id}" for the timeline view
```

#### 3.3.2 ExecutionView Enhancement

The existing ExecutionView dataclass is well-designed.  Proposed changes:

```python
@dataclass
class ExecutionView:
    item_slug: str
    item_type: str              # NEW: "defect" | "feature" | "unknown"
    total_duration: str
    total_cost: str
    phases: list[PhaseView]
    overall_status: str
    # NEW fields for header links
    design_doc_path: str        # resolved from phase artifacts
    validation_report_path: str # resolved from phase artifacts
```

PhaseView already has: phase_name, run_name, run_id, agent, status, duration,
cost, activity_summary, artifacts, files_read, files_written, bash_commands.
No changes needed to PhaseView itself.

### 3.4 Template Structure

#### 3.4.1 List Page (proxy_list.html)

**Column structure change:**

Current columns: Trace ID | Item | Start time | Duration | Cost | Model | Status

Proposed columns: Item | Type | Start time | Duration | Cost | Outcome

Changes:
- Remove "Trace ID" as a primary column (move to tooltip on Item link)
- Remove "Model" column (low value; available in detail page)
- Add "Type" column with defect/feature badge
- Rename "Status" to "Outcome" with pass/fail/running/error badge
- Item column shows display_slug as clickable link to narrative page
- Trace ID available via copy button on Item name hover

**Title change:** "Execution History" (already done in current template -- verified)

**Filter bar:** Keep current filters.  The Name filter already does substring
matching which will work correctly once run names are backfilled from child slugs.

#### 3.4.2 Detail/Narrative Page (proxy_narrative.html)

**Header section:**

```
[Back to traces]                                    [Show raw trace]

  {display_name}  [Completed]
  Started: 2026-03-28 14:23:01
  Total duration: 12m 34s
  Total cost: $0.4567
  Phases: 5

  [View work item] [Design doc] [Validation report] [Worker logs] [Git log]
```

**Phase timeline:** Keep existing vertical timeline with phase cards.  Already
supports expandable sections with files read/written, bash commands, and artifacts.

**Raw trace toggle:** Replace the current separate-page link with an inline toggle.
When toggled on, render a pre-formatted JSON block at the bottom of the page
showing the full root run metadata and raw child data.  The route handler
pre-serializes this to avoid template-level JSON formatting.

### 3.5 Duration Fix Architecture (D4)

The root cause of near-zero durations is that LangSmith SDK records graph-level
start/end events nearly simultaneously.  The real execution time is in child spans.

**List page fix:**
_enrich_run() already has logic to prefer child spans when root duration < 1s
(the _NEAR_ZERO_DURATION_S constant).  The issue is that some paths bypass this.
Fix: ensure the child_agg.time_span is ALWAYS used when available and non-null,
regardless of root duration.  The root duration should only be used as fallback
when no child time span data exists.

**Narrative page fix:**
build_execution_view() already computes total duration from children or
grandchildren with a fallback chain.  The issue is the _NEAR_ZERO_DURATION_S
threshold (1.0s) may be too aggressive for some real short phases.  Fix: always
prefer the children span when it produces a larger value than the root span.

**Per-phase duration fix:**
_build_phase_view() already prefers grandchild spans.  The merged phase view
(_build_merged_phase_view) correctly uses earliest_start/latest_end across
merged children.  Verify this works end-to-end with real data.

### 3.6 Cost and Model Fix Architecture (D5)

**Cost:** The _CHILD_COSTS_BATCH_SQL_TEMPLATE uses a recursive CTE that walks the
full subtree and sums total_cost_usd from metadata_json.  This is correct but only
works when cost data is actually recorded in metadata.  The fix requires ensuring
that the trace recording path (record_run / update_run) includes cost data when
available from the LLM response.

For the display layer: _enrich_run() already formats child cost when root cost
is missing.  The display_cost field should show the child-aggregated value.

**Model:** The _CHILD_MODELS_BATCH_SQL_TEMPLATE finds the most common model among
direct children.  This may miss models recorded only at the grandchild level.
Fix: extend the query to include grandchildren (one level deeper) using a
UNION in the CTE, or query grandchild models in a separate batch.

### 3.7 Phase Processing Fix Architecture (D6, D7)

**Deduplication (already implemented):**
build_execution_view() groups children by phase name and calls
_build_merged_phase_view() when multiple children share the same phase.
This is already in the codebase (trace_narrative.py lines 147-165).

**Name resolution fix:**
_classify_phase() uses _PHASE_PATTERNS with ordered substring matching.
Current patterns already include "verify_fix" -> "Verification" and
"validate" -> "Validation".  The issue is that the "Unknown" fallback
provides no useful information.

Fix: change _classify_phase() fallback from _UNKNOWN_PHASE to
title-cased raw run name (e.g., "verify_fix" -> "Verify Fix").  Remove
the "Unknown" constant entirely.

**Operational detail enhancement:**
_format_activity_summary() already generates summaries like
"Read 5 files, edited 2, ran 8 bash commands".  The issue is that for
phases with no tool calls detected, it returns empty string which the
template renders as nothing.

Fix: generate a fallback summary from the phase status and duration,
e.g., "Completed in 2m 15s" or "3 files changed, 2 commands run,
all checks passed".

### 3.8 Artifact Links Architecture (D9)

The narrative page needs clickable links in the header.  These are derived
from multiple sources:

| Link | Source | Resolution |
|------|--------|-----------|
| Work item page | display_slug | "/item/{slug}" -- existing route |
| Design document | Phase artifacts with "docs/plans/" pattern | Already extracted by _extract_artifacts() |
| Validation report | Phase artifacts with validation pattern | Already extracted by _extract_artifacts() |
| Worker output logs | _find_worker_logs(slug) | Already implemented in route handler |
| Git commits | git log filtered by slug | New: generate URL "/git-log?slug={slug}" or show inline git entries |

Most artifact data is already extracted by the narrative builder.  The route
handler needs to aggregate these from phase-level artifacts into a header-level
links structure (ArtifactLinks dataclass).

### 3.9 Raw Trace Toggle Architecture (D10)

**Current:** A link to "/proxy/{run_id}" which renders a separate timeline page.

**Proposed:** An inline toggle button that shows/hides a pre-formatted JSON block.

Implementation:
1. Route handler serializes the raw run + children data as indented JSON
2. Pass as raw_trace_json string in template context
3. Template renders a hidden <pre> block with the JSON
4. JavaScript toggles visibility on button click
5. Keep the link to the timeline page as a secondary option

This avoids a page reload for quick debugging while preserving the full
timeline view for detailed trace inspection.

## 4. Implementation Sequence

```
Phase 0: Design competition (this document + UX + frontend proposals)
    |
    v
Phase 1: Data backfill (D2, D3) -- independent of UI
    |     - backfill_root_run_slugs()
    |     - backfill_stale_status()
    |
Phase 2: Metrics fixes (D4, D5) -- independent of UI
    |     - Duration computation fix in _enrich_run and build_execution_view
    |     - Cost/model aggregation fixes
    |
Phase 3: Phase processing fixes (D6, D7) -- independent of UI
    |     - Phase name fallback (title-case instead of "Unknown")
    |     - Operational detail enrichment
    |
Phase 4: List page UI (D8) -- depends on Phases 1-3
    |     - Column restructure: remove Trace ID + Model, add Type + Outcome
    |     - display_item_type enrichment
    |
Phase 5: Detail page UI (D9, D10) -- depends on Phases 1-3
          - Header links (ArtifactLinks)
          - Inline raw trace toggle
          - Phase expansion (already functional)
```

Phases 1, 2, and 3 can run in parallel since they modify different code paths.
Phase 4 and 5 can run in parallel once the data fixes land.

## 5. Acceptance Criteria Coverage

### List Page (AC4, AC12, AC21-AC29)

| AC | How Addressed |
|----|--------------|
| AC4 | Remove redundant "Item slug" column; add type badge column |
| AC12 | Page title "Execution History" (already set in current template) |
| AC21 | Slug filter input preserved in filter bar |
| AC22 | Filter narrows to matching traces (existing behavior, works after backfill) |
| AC23 | Filtered results show real item names (via backfilled display_slug) |
| AC24 | Each row displays item slug (display_slug in Item column) |
| AC25 | Each row displays type badge (new display_item_type field) |
| AC26 | Each row displays start time (existing start_time column) |
| AC27 | Real duration in list rows (child-aggregated via _enrich_run fix) |
| AC28 | Real cost in list rows (child CTE cost via _enrich_run fix) |
| AC29 | Each row displays outcome badge (renamed status column) |

### Detail Page (AC13, AC19, AC20, AC30-AC44)

| AC | How Addressed |
|----|--------------|
| AC13 | Detail page title shows item slug (already using display_name resolution) |
| AC19 | Link to work item page (ArtifactLinks.work_item_url) |
| AC20 | Link to worker output logs (already rendered, needs URL enhancement) |
| AC30 | Row click navigates to detail view (existing href to /narrative) |
| AC31 | Phase shows real elapsed duration (grandchild span preference) |
| AC32 | Phase shows real cost (aggregate from phase children + grandchildren) |
| AC33 | Expandable phase sections (already implemented with phase-card toggle) |
| AC34 | Expanded view shows files read (already in phase.files_read) |
| AC35 | Expanded view shows commands run (already in phase.bash_commands) |
| AC36 | Expanded view shows agent responses (activity_summary) |
| AC37 | Link to design document (ArtifactLinks.design_doc_path) |
| AC38 | Link to validation results (ArtifactLinks.validation_report) |
| AC39 | Link to worker output logs (ArtifactLinks.worker_log_paths) |
| AC40 | Link to git commits (ArtifactLinks.git_log_url) |
| AC41 | Raw trace toggle present (inline toggle button) |
| AC42 | Toggle off by default (hidden <pre> block) |
| AC43 | Toggle reveals full raw JSON (pre-serialized in route handler) |
| AC44 | Toggle hides raw JSON when off (JavaScript visibility toggle) |

## 6. Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Backfill takes too long on large DBs | Use batch UPDATE with LIMIT; run async |
| Child cost CTE returns 0 when no cost recorded | Show dash instead of "$0.0000" |
| Phase classification misses new node types | Fallback to title-cased raw name |
| Raw trace JSON too large for inline display | Cap at 100KB; truncate with notice |
| Type badge inference from slug is unreliable | Fall back to "unknown" badge; use metadata.item_type when available |

## 7. Key Design Decisions

### D1: Minimal Refactoring Over Rebuild

The existing architecture is sound.  The enrichment pipeline (_enrich_run), batch
queries, and narrative builder all work correctly in isolation.  The issues are:
data gaps (missing backfill), presentation gaps (wrong columns, missing links),
and threshold bugs (near-zero duration detection).  A targeted fix strategy
preserves the working infrastructure while addressing every reported issue.

### D8: List Page Column Reduction

Remove Trace ID and Model columns.  Rationale:
- Trace ID is rarely needed and creates visual noise
- Model is a debugging detail, not a user-facing metric
- Adding Type badge requires column budget
- Trace ID available via copy button on hover
- Model available on the detail page

### D9: Header Links as First-Class Component

Instead of scattering artifact links across phase cards, aggregate them into a
dedicated header links bar.  This gives one-click access to the most common
navigation targets (work item, design doc, validation results, worker logs).
Phase-level artifacts remain in their respective expanded sections.

### D10: Inline Raw Trace Over Separate Page

The timeline page (/proxy/{run_id}) is useful for trace engineers but disorienting
for regular users.  An inline JSON toggle provides quick debugging access without
leaving the narrative context.  The timeline page remains accessible as a
secondary link within the toggle panel.
