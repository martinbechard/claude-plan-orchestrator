# Design: 70 Traces Page Usability Overhaul

## Architecture Overview

The traces page consists of three views backed by the TracingProxy SQLite layer:

1. **List view** (`/proxy`) - Paginated, filterable list of root runs rendered by `proxy_list.html`
2. **Timeline view** (`/proxy/{run_id}`) - Gantt chart of run hierarchy rendered by `proxy_trace.html`
3. **Narrative view** (`/proxy/{run_id}/narrative`) - Phase-by-phase execution story rendered by `proxy_narrative.html`

The existing codebase already has substantial infrastructure: batch queries for child
time spans, costs, models, and slugs; a narrative view with phase classification and
artifact extraction; filtering by slug/model/date; and grouping by slug. The overhaul
addresses two categories of issues:

- **Data quality**: Run names default to "LangGraph", durations show near-zero values,
  cost/model data missing, stale RUNNING status, duplicate/unknown phases, no operational detail
- **UI/UX**: Redundant columns, developer jargon titles, missing navigation links,
  no phase expansion for agent actions, raw JSON exposed instead of toggled

**Strategy**: Fix data layer computation and backfill (Sections 2-4, can run in parallel)
while running a UI design competition (Phase 0 Section 1), then implement the winning
UI design using the corrected data (Sections 5-6).

## Key Files

**Python (data layer)**:
- `langgraph_pipeline/web/proxy.py` - TracingProxy: backfill methods, batch queries, status resolution
- `langgraph_pipeline/web/helpers/trace_narrative.py` - ExecutionView: phase dedup, name resolution, operational detail
- `langgraph_pipeline/web/routes/proxy.py` - Route handlers: data enrichment for templates

**Templates (UI layer)**:
- `langgraph_pipeline/web/templates/proxy_list.html` - List page columns, title, row layout
- `langgraph_pipeline/web/templates/proxy_narrative.html` - Detail page title, phases, links, toggle

**Tests**:
- `tests/langgraph/web/test_proxy_backfill.py` (new)
- `tests/langgraph/web/test_trace_narrative.py` (new or enhanced)

## Design Decisions

### D1: Phase 0 UI Design Competition

- **Addresses**: P2, P8, P9, P15, UC2, UC3, UC4, FR2
- **Satisfies**: AC4, AC12, AC13, AC19, AC20, AC24-AC36, AC37-AC44
- **Approach**: Run three competing design proposals for the traces page UX:
  - Systems-designer: data architecture, component hierarchy, API boundaries
  - UX-designer: information architecture, interaction patterns, accessibility
  - Frontend-coder: component implementation, responsive layout, CSS patterns
  Design-judge selects winner. Planner extends with implementation specifics.
- **Files**: Design proposals written to `tmp/workspace/70-traces-page-usability-overhaul/`

### D2: Run Name Backfill from Child Span Metadata

- **Addresses**: P1
- **Satisfies**: AC1, AC2, AC3
- **Approach**: Add `backfill_root_run_slugs()` method to TracingProxy that:
  1. Queries root runs where `name = 'LangGraph'`
  2. Uses existing `_CHILD_SLUGS_BATCH_SQL` pattern to resolve correct item slugs from child span metadata
  3. Updates `name` and `metadata_json` fields with the resolved slug
  4. Called during proxy initialization so old data is fixed on startup
- **Files**: `langgraph_pipeline/web/proxy.py`, `tests/langgraph/web/test_proxy_backfill.py`

### D3: Stale Status Resolution and end_time Backfill

- **Addresses**: P6
- **Satisfies**: AC9, AC10
- **Approach**: Add `backfill_stale_status()` method to TracingProxy that:
  1. Finds root runs with no `end_time` that have children with `end_time` set
  2. Infers root `end_time` from `MAX(children.end_time)`
  3. Updates status from RUNNING to COMPLETED/FAILED based on child error presence
  4. Called during proxy initialization after run name backfill
- **Files**: `langgraph_pipeline/web/proxy.py`, `tests/langgraph/web/test_proxy_backfill.py`

### D4: Duration Computation Fix

- **Addresses**: P3, P10, P11
- **Satisfies**: AC5, AC6, AC14, AC15, AC27
- **Approach**: The existing `get_child_time_spans_batch()` returns correct child spans
  but the duration display has bugs:
  1. **List page**: Ensure `proxy_list` route uses child time span data to compute real
     wall-clock duration instead of near-zero root span timestamps
  2. **Detail page total**: Fix `build_execution_view()` to use child span aggregation
     for total duration
  3. **Phase durations**: Fix per-phase duration computation in `build_execution_view()`
     to use phase start/end timestamps from child runs
- **Files**: `langgraph_pipeline/web/proxy.py`, `langgraph_pipeline/web/helpers/trace_narrative.py`, `langgraph_pipeline/web/routes/proxy.py`

### D5: Cost and Model Data Aggregation Fix

- **Addresses**: P4, P5
- **Satisfies**: AC7, AC8, AC28
- **Approach**:
  1. **Cost**: Verify and fix `get_child_costs_batch()` recursive CTE to properly sum
     `total_cost_usd` from `metadata_json`. Ensure cost data is written during trace recording.
  2. **Model**: Verify and fix `get_child_models_batch()` to extract model name from child
     spans. Ensure model field is populated during trace recording.
  3. **Display**: Ensure list view route passes cost and model data to template context.
- **Files**: `langgraph_pipeline/web/proxy.py`, `langgraph_pipeline/web/routes/proxy.py`

### D6: Phase Deduplication and Name Resolution

- **Addresses**: P12, P13
- **Satisfies**: AC16, AC17
- **Approach**:
  1. **Deduplication**: Add dedup logic in `build_execution_view()` to merge duplicate
     phase entries. When multiple child runs map to the same phase (e.g., two "Planning"
     runs), merge their data into a single phase with combined duration and aggregated details.
  2. **Name resolution**: Extend the phase name mapping in `trace_narrative.py` to handle
     all phase types including `verify_fix`, `validate_task`, and any other unmapped names.
     Add a fallback that title-cases the raw run name instead of showing "Unknown".
- **Files**: `langgraph_pipeline/web/helpers/trace_narrative.py`, `tests/langgraph/web/test_trace_narrative.py`

### D7: Phase Operational Detail Enrichment

- **Addresses**: P14
- **Satisfies**: AC18
- **Approach**: Enhance phase summary generation in `build_execution_view()`:
  1. Instead of just "PASS", generate summaries like "Validated 3 files, ran 2 commands,
     all checks passed"
  2. Extract actionable metrics: files changed count, commands run count, validation details
  3. Include key outcomes: test results, lint results, build status where available
- **Files**: `langgraph_pipeline/web/helpers/trace_narrative.py`, `tests/langgraph/web/test_trace_narrative.py`

### D8: List Page UI Redesign

- **Addresses**: P2, P7, P8, UC1, UC2
- **Satisfies**: AC4, AC11, AC12, AC21, AC22, AC23, AC24, AC25, AC26, AC27, AC28, AC29
- **Approach**: Implement winning Phase 0 design for list page:
  1. **Title**: Change from "LangSmith Traces" to user-facing language (e.g., "Pipeline Runs")
  2. **Columns**: Remove redundant "Item slug" column. Each row shows: item slug/name,
     type badge (defect/feature), start time, real duration, real cost, outcome badge
  3. **Filter**: Ensure slug filter works correctly with backfilled names for partial matching
  4. **Grouping**: Existing group-by-slug works correctly once run names are backfilled
- **Files**: `langgraph_pipeline/web/templates/proxy_list.html`, `langgraph_pipeline/web/routes/proxy.py`

### D9: Detail Page Core Redesign

- **Addresses**: P9, P15, UC3, FR1
- **Satisfies**: AC13, AC19, AC20, AC30, AC31, AC32, AC37, AC38, AC39, AC40
- **Approach**: Implement winning Phase 0 design for narrative detail page:
  1. **Title**: Display actual item name/slug instead of "LangGraph"
  2. **Links**: Add clickable links to work item page, worker output logs, design document,
     validation results, and git commits
  3. **Phase metrics**: Each phase shows real elapsed duration and real cost
  4. **Navigation**: Clicking a list row navigates to detail view (already works)
- **Files**: `langgraph_pipeline/web/templates/proxy_narrative.html`, `langgraph_pipeline/web/routes/proxy.py`, `langgraph_pipeline/web/helpers/trace_narrative.py`

### D10: Phase Expansion and Raw Trace Toggle

- **Addresses**: UC4, FR2
- **Satisfies**: AC33, AC34, AC35, AC36, AC41, AC42, AC43, AC44
- **Approach**:
  1. **Phase expansion**: Add collapsible sections within each phase card showing agent
     actions: files read/written, commands run, agent responses. Leverage existing file/command
     extraction from `trace_narrative.py`.
  2. **Raw trace toggle**: Add a toggle button (hidden/off by default) that reveals full
     raw trace/metadata JSON inline. When disabled, raw JSON is completely hidden. Replace
     current "switch to trace view" link with inline toggle.
- **Files**: `langgraph_pipeline/web/templates/proxy_narrative.html`

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D2 | Backfill root run names from child span metadata |
| AC2 | D2 | Backfill ensures unique display names per row |
| AC3 | D2 | Backfill extracts slugs from child span metadata |
| AC4 | D8 | Remove redundant column, replace with type badge |
| AC5 | D4 | Fix duration computation to use child time spans |
| AC6 | D4 | Child span aggregation produces real wall-clock duration |
| AC7 | D5 | Fix cost extraction from metadata_json |
| AC8 | D5 | Fix model extraction from child spans |
| AC9 | D3 | Infer terminal status from child outcomes |
| AC10 | D3 | Backfill end_time from MAX(children.end_time) |
| AC11 | D8 | Slug filter works with backfilled names |
| AC12 | D8 | Change page title to user-facing language |
| AC13 | D9 | Detail page title shows item slug |
| AC14 | D4 | Total duration uses child span aggregation |
| AC15 | D4 | Per-phase duration from phase start/end timestamps |
| AC16 | D6 | Merge duplicate phase entries |
| AC17 | D6 | Map all phase types including verify_fix |
| AC18 | D7 | Generate meaningful phase summaries |
| AC19 | D9 | Add link to work item page |
| AC20 | D9 | Add link to worker output logs |
| AC21 | D8 | Slug filter input on list page |
| AC22 | D8 | Filter narrows to matching traces |
| AC23 | D8 | Filtered results show real item names |
| AC24 | D8 | Each row displays item slug |
| AC25 | D8 | Each row displays type badge |
| AC26 | D8 | Each row displays start time |
| AC27 | D4, D8 | Real duration in list rows |
| AC28 | D5, D8 | Real cost in list rows |
| AC29 | D8 | Each row displays outcome badge |
| AC30 | D9 | Row click navigates to detail view |
| AC31 | D4, D9 | Phase shows real elapsed duration |
| AC32 | D5, D9 | Phase shows real cost |
| AC33 | D10 | Expandable phase sections |
| AC34 | D10 | Expanded view shows files read/written |
| AC35 | D10 | Expanded view shows commands run |
| AC36 | D10 | Expanded view shows agent responses |
| AC37 | D9 | Link to design document |
| AC38 | D9 | Link to validation results |
| AC39 | D9 | Link to worker output logs |
| AC40 | D9 | Link to git commits |
| AC41 | D10 | Raw trace toggle present |
| AC42 | D10 | Toggle off by default |
| AC43 | D10 | Toggle reveals full raw JSON |
| AC44 | D10 | Toggle hides raw JSON when off |
