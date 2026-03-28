# Design: 71 Execution History Redesign

Source: tmp/plans/.claimed/71-execution-history-redesign.md
Requirements: docs/plans/2026-03-28-71-execution-history-redesign-requirements.md
Date: 2026-03-28

## Architecture Overview

This redesign replaces the standalone Traces page with an integrated execution
history accessible from the Completions page. The architecture has three layers:

1. **Data Layer** (TracingProxy): Recursive tree fetch, real cost aggregation,
   wall-clock duration, slug resolution, deduplication -- all via SQLite
   recursive CTEs in proxy.py.

2. **View Model Layer** (trace_narrative.py): Transforms flat DB rows into a
   recursive tree structure (TreeNode) with computed metrics at every level.
   Replaces the current 2-level (children + grandchildren) model with unlimited
   depth.

3. **Presentation Layer** (templates + JS): Tree view with expand/collapse,
   detail side panel, deep-dive prompt/response view. The Completions page
   gets trace links; the standalone Traces nav entry is removed.

### Key Files

| File | Role |
|---|---|
| langgraph_pipeline/web/proxy.py | TracingProxy: new get_full_subtree(), upgraded time spans |
| langgraph_pipeline/web/helpers/trace_narrative.py | Recursive TreeNode model, replaces 2-level ExecutionView |
| langgraph_pipeline/web/routes/proxy.py | Execution history route, slug resolution, dedup |
| langgraph_pipeline/web/templates/execution_history.html | New: recursive tree + side panel + deep-dive |
| langgraph_pipeline/web/templates/completions.html | Trace link update |
| langgraph_pipeline/web/templates/base.html | Nav bar: remove standalone Traces link |
| langgraph_pipeline/web/static/execution_history.js | New: tree expand/collapse, panel switching, lazy load |

### Prototype Reference

Three prototype screens in prototype_traces/ show the target UX:
- Screen 1: Completions page with Trace column links
- Screen 2: Recursive tree view with side panel (agents, tool calls)
- Screen 3: Deep-dive prompt/response inspection (side-by-side panels)

---

## Design Decisions

### D1: Recursive Full-Subtree Fetch via Single Recursive CTE

Addresses: P1, FR1
Satisfies: AC1, AC2, AC18, AC19, AC20, AC21, AC22, AC23, AC24, AC25
Approach: Add a get_full_subtree(run_id) method to TracingProxy that uses a
single WITH RECURSIVE CTE to fetch all descendants of a root run in one query.
Returns flat rows with parent_run_id linkage. Python code assembles rows into a
tree structure (dict with children list). No depth limit -- the CTE recurses
until no more children exist. This replaces the current get_children_batch +
get_children pattern that only goes 1-2 levels deep.
Files: langgraph_pipeline/web/proxy.py

### D2: Real Cost Aggregation -- Eliminate Placeholders

Addresses: P2, FR2
Satisfies: AC3, AC4, AC26, AC27, AC28
Approach: Leverage the existing get_child_costs_batch() recursive CTE which
already traverses the full subtree. Ensure every node in the tree displays
aggregated cost from its descendants. Filter out zero-cost nodes (where
total_cost_usd is 0.0 or absent) from aggregation so placeholders like 0.01
never appear. The view model layer computes display cost at each tree level
by summing descendant costs.
Files: langgraph_pipeline/web/proxy.py, langgraph_pipeline/web/helpers/trace_narrative.py

### D3: Wall-Clock Duration via Recursive Descendant Time Spans

Addresses: P3, FR3
Satisfies: AC5, AC29, AC30, AC31
Approach: Upgrade get_child_time_spans_batch() from a direct-children-only
query to a recursive CTE that finds MIN(start_time) and MAX(end_time) across
the full descendant subtree. This mirrors how get_child_costs_batch() already
works recursively. Near-zero durations from root span timestamps are replaced
with the computed wall-clock duration. The existing _NEAR_ZERO_DURATION_S
threshold (1.0s) is used to detect dispatch-only timestamps.
Files: langgraph_pipeline/web/proxy.py, langgraph_pipeline/web/helpers/trace_narrative.py

### D4: Item Slug Resolution -- Never Display "LangGraph"

Addresses: FR4
Satisfies: AC32, AC33, AC34, AC35
Approach: Multi-tier resolution strategy applied at the view model layer:
(1) Extract item_slug from metadata_json if present.
(2) Fall back to existing _CHILD_SLUGS_BATCH_SQL child span metadata lookup.
(3) Fall back to run_id prefix (first 8 chars) as last resort.
A display-layer guard ensures the string "LangGraph" is never rendered as an
item name -- any occurrence is replaced via the resolution chain. This uses
the existing resolve_child_slugs_batch() infrastructure.
Files: langgraph_pipeline/web/helpers/trace_narrative.py, langgraph_pipeline/web/routes/proxy.py

### D5: UI-Layer Deduplication of Start/End Events

Addresses: FR5
Satisfies: AC36, AC37
Approach: The DB already uses INSERT OR REPLACE on run_id to prevent storage
duplicates. Add a UI-layer safety net: when building the tree, group nodes by
run_id and keep only the most complete row (the one with end_time if both
exist). This prevents any display of duplicate start/end events.
Files: langgraph_pipeline/web/helpers/trace_narrative.py

### D6: Completions Page as Sole Entry Point (UI Design Competition)

Addresses: UC1
Satisfies: AC6, AC7, AC8
Approach: Phase 0 design competition determines the exact UI treatment. The
winning design will specify how trace links appear on completions rows and
how the execution history page is navigated to. The base.html nav bar removes
the standalone "Traces" link. Every completed row with a run_id gets a
visible trace link.
Files: langgraph_pipeline/web/templates/completions.html, langgraph_pipeline/web/templates/base.html

### D7: Recursive Tree UI with Expand/Collapse (UI Design Competition)

Addresses: UC2
Satisfies: AC9, AC10, AC11
Approach: Phase 0 design competition determines the tree rendering approach.
Options include: fully server-rendered nested HTML with JS toggle, lazy-loaded
AJAX expansion, or client-side tree from JSON API. The winning design must
support unlimited depth with no artificial cutoff. Each node is independently
expandable/collapsible.
Files: new template (execution_history.html), new JS (execution_history.js)

### D8: Node Detail Side Panel with Metrics and Metadata (UI Design Competition)

Addresses: UC3, FR6, FR7, FR8
Satisfies: AC12, AC13, AC14, AC38, AC39, AC40, AC41, AC42, AC43, AC44, AC45, AC46, AC47, AC48, AC49, AC50
Approach: Phase 0 design competition determines panel layout and content
rendering. The panel content varies by node type:
- Graph nodes: state inputs/outputs
- Agent nodes: prompt and response
- Tool call nodes: input and result (file path, command, etc.)
Metrics (latency, tokens, cost, model) shown conditionally -- omitted when
absent. Observability metadata (validator verdicts, pipeline decisions,
subprocess exit codes, plan state snapshots) displayed in structured format.
Raw JSON toggle hidden by default, reveals full trace data when enabled.
Files: new template (execution_history.html), new JS

### D9: Deep-Dive Prompt/Response Inspection (UI Design Competition)

Addresses: UC4
Satisfies: AC15, AC16, AC17
Approach: Phase 0 design competition determines the layout. Target: side-by-side
scrollable panels showing system prompt (left) and agent response (right).
Both panels independently scrollable. Latency and token metrics displayed
above or below the panels. Can be a modal overlay or a dedicated sub-page.
Files: new template (execution_history.html or dedicated deep_dive.html)

---

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | Recursive CTE fetches all depths; tree displays depth 3+ |
| AC2 | D1 | Tool calls (Read, Edit, Bash, etc.) visible as descendants in tree |
| AC3 | D2 | All phases use aggregated cost from recursive CTE, not placeholders |
| AC4 | D2 | Zero-cost placeholders filtered out of aggregation |
| AC5 | D3 | Recursive descendant time spans replace near-zero root timestamps |
| AC6 | D6 | Completions row trace link opens execution history |
| AC7 | D6 | Standalone Traces page removed; Completions is sole entry point |
| AC8 | D6 | Every completed row with run_id displays trace link |
| AC9 | D7 | Tree nodes expandable/collapsible at any depth |
| AC10 | D7 | Full navigation from pipeline node to leaf tool call |
| AC11 | D7 | No artificial depth limit in tree rendering |
| AC12 | D8 | Side panel shows state inputs/outputs for graph nodes |
| AC13 | D8 | Side panel shows prompt/response for agent nodes |
| AC14 | D8 | Side panel shows input/result for tool call nodes |
| AC15 | D9 | Side-by-side system prompt and agent response |
| AC16 | D9 | Both panels independently scrollable |
| AC17 | D9 | Latency and token metrics in deep-dive view |
| AC18 | D1 | Top-level pipeline graph nodes (intake, requirements, etc.) in tree |
| AC19 | D1 | Executor subgraph nodes under execution |
| AC20 | D1 | Claude CLI sessions under task running |
| AC21 | D1 | Individual tool calls under each agent |
| AC22 | D1 | Nested sub-tool-calls within Skill invocations |
| AC23 | D1 | Recursive fetch has no hardcoded depth limit |
| AC24 | D1 | Full recursive tree of everything pipeline did |
| AC25 | D1 | Tree extends to leaf tool calls without intermediate cutoff |
| AC26 | D2 | Phase cost aggregated from all subtree descendants |
| AC27 | D2 | Uses existing recursive CTE from TracingProxy |
| AC28 | D2 | Zero-cost placeholders excluded from aggregation |
| AC29 | D3 | Duration from earliest descendant start to latest end |
| AC30 | D3 | Uses TracingProxy child time span infrastructure (upgraded to recursive) |
| AC31 | D3 | Near-zero root timestamps replaced with wall-clock durations |
| AC32 | D4 | Slug resolved from metadata when available |
| AC33 | D4 | Falls back to child span metadata lookup |
| AC34 | D4 | Falls back to run_id prefix as last resort |
| AC35 | D4 | "LangGraph" never appears as item name |
| AC36 | D5 | At most one row per run_id in tree |
| AC37 | D5 | No visible duplicate start/end events |
| AC38 | D8 | Latency displayed when timing data available |
| AC39 | D8 | Token count displayed when token data available |
| AC40 | D8 | Cost displayed when cost data available |
| AC41 | D8 | Model name displayed when model data available |
| AC42 | D8 | Missing metrics omitted gracefully |
| AC43 | D8 | Validator verdicts in readable format |
| AC44 | D8 | Pipeline decisions displayed |
| AC45 | D8 | Subprocess exit codes displayed |
| AC46 | D8 | Plan state snapshots displayed |
| AC47 | D8 | Metadata in structured form, not raw JSON |
| AC48 | D8 | Raw trace toggle hidden by default |
| AC49 | D8 | Toggle reveals full raw JSON |
| AC50 | D8 | Toggle can be disabled to re-hide |
