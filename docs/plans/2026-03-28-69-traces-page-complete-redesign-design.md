# Design: Traces Page Complete Redesign

## Summary

The traces page exposes raw LangSmith infrastructure telemetry instead of an
item-centric execution narrative. This redesign addresses 17 documented problems
across the list page (/proxy) and narrative detail page (/proxy/{id}/narrative).

The core transformation: replace "show what the system traced" with "show what
happened to the user's work item from start to finish."

## Architecture

### Layer 1: Data Fixes (trace_narrative.py + proxy.py)

The data layer problems must be fixed before UI changes matter:

- **Duplicate event merging (P3, P13):** Start/end trace events for the same
  pipeline phase appear as separate rows with 0.00s duration. The
  build_execution_view function must merge children that share the same phase
  classification — use the earliest start_time and latest end_time to compute
  real duration.

- **Item slug resolution (P1, P10):** When run name is "LangGraph", extract
  the slug from metadata_json (slug or item_slug field). If neither exists,
  fall back to scanning child run metadata. The _enrich_run helper in proxy.py
  must prioritize metadata slug over raw run name.

- **Duration computation (P3, P11, P12):** The current _format_duration uses
  only the individual run start/end times. For merged phases, compute duration
  from the earliest child start to the latest child end within that phase.
  For the root run total duration, use the span from first child start to
  last child end rather than the root run timestamps.

- **Cost aggregation (P4):** Sum cost values from metadata_json across all
  children. Many individual runs have no cost field, but the cost is recorded
  at deeper levels. Walk grandchildren to accumulate costs.

- **Status correction (P7):** Runs with no end_time but whose last child has
  ended should be marked "Completed" not "Running". Add a heuristic: if the
  latest child end_time is > 5 minutes ago and no children are running, the
  run is done.

- **Phase label mapping (P14):** Add "verify_fix" -> "Verification" to the
  _PHASE_PATTERNS list in trace_narrative.py. Also add "verify" as a pattern.

### Layer 2: List Page Redesign (proxy_list.html + proxy.py route)

- **Remove "Item slug" column (P2):** The slug is now the primary identifier
  shown in the "Run name" column. Remove the separate slug column.

- **Rename title (P9):** "LangSmith Traces" -> "Execution History"

- **Group by work item (P8):** The list already filters by slug. Add a
  "Group by item" toggle that collapses runs for the same slug into a single
  row with an expand arrow showing individual executions.

- **Remove collapsed detail rows (P6):** Replace the always-present
  expandable metadata JSON row with a simple click-through to the narrative
  page. The metadata JSON is developer-only and belongs behind "Show raw trace."

- **Improve status logic (P7):** Use the corrected status from Layer 1.

### Layer 3: Narrative Page Fixes (proxy_narrative.html + trace_narrative.py)

- **Use item slug as title (P10):** Display the resolved slug, not "LangGraph."

- **Real phase durations and costs (P12, P15):** The merged phase data from
  Layer 1 feeds directly into PhaseView.

- **Merge duplicate phases (P13):** Handled by Layer 1 merging logic.

- **Add agent activity detail (P15):** Each phase card already has an
  activity_summary field. Expand it to show files read/written, bash commands,
  and a summarized Claude response (first 200 chars).

- **Add work item link (P16):** Add a link to /item/{slug} in the narrative
  header.

- **Add worker output link (P17):** Scan tmp/worker-output/ for files
  matching the slug and link them from the phase card artifacts section.

- **Raw trace toggle (P6, existing):** Already implemented as a link to
  /proxy/{run_id}. Ensure it's prominent but not the default.

### Key Files to Modify

- langgraph_pipeline/web/helpers/trace_narrative.py -- duplicate merging,
  cost aggregation, phase label fixes, worker output artifact linking
- langgraph_pipeline/web/routes/proxy.py -- status correction, slug
  resolution improvements, detail row removal from list response
- langgraph_pipeline/web/templates/proxy_list.html -- remove slug column,
  rename title, remove detail rows, improve status display
- langgraph_pipeline/web/templates/proxy_narrative.html -- slug title, item
  link, worker output links, phase detail expansion

### Data Flow

```
TracingProxy.list_runs()
  |
  v
_enrich_run()  -- improved slug resolution, cost aggregation
  |
  v
proxy_list.html  -- cleaned up: slug as primary name, no detail rows
  |  click
  v
TracingProxy.get_run(run_id) + children + grandchildren
  |
  v
build_execution_view()  -- with duplicate merging and cost rollup
  |
  v
ExecutionView with merged phases, real durations, real costs
  |
  v
proxy_narrative.html  -- slug title, item link, worker output links
```

### Design Decisions

- Fix data layer first (trace_narrative.py, proxy.py) before touching
  templates, because the UI problems are symptoms of wrong data.
- Merge duplicate events at the PhaseView level rather than in SQLite,
  keeping the raw data intact for the "Show raw trace" view.
- The design competition originally called for in item 69 is unnecessary --
  the vertical timeline design from item 66 is already implemented in
  proxy_narrative.html. The work here is fixing the data and cleaning up
  the UI, not redesigning from scratch.
- Keep the raw trace page (proxy_trace.html) untouched as the developer
  escape hatch. All changes go to proxy_list.html and proxy_narrative.html.


## Acceptance Criteria

- Does the traces list show work item slugs (not "LangGraph") for
  every row? YES = pass, NO = fail
- Is the "Item slug" redundant column removed? YES = pass, NO = fail
- Does each row show the REAL duration (minutes, not 0.01s)?
  YES = pass, NO = fail
- Does each row show the REAL cost? YES = pass, NO = fail
- Are duplicate start/end trace events merged into a single row?
  YES = pass, NO = fail
- Are "RUNNING" entries that are actually finished cleaned up or
  correctly labeled? YES = pass, NO = fail
- Does clicking a row show phases with real durations and costs?
  YES = pass, NO = fail
- Are duplicate phases (Planning x2, Execution x2, verify_fix x2)
  merged? YES = pass, NO = fail
- Does "verify_fix" show as "Verification" not "Unknown"?
  YES = pass, NO = fail
- Does each phase show what the agent actually did (files, commands)?
  YES = pass, NO = fail
- Is there a link from the trace detail to /item/<slug>?
  YES = pass, NO = fail
- Is there a link to worker output logs and validation results?
  YES = pass, NO = fail
- Is raw LangSmith data hidden by default, accessible via toggle?
  YES = pass, NO = fail
