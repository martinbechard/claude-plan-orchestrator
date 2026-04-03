# Design: 71 Execution History Redesign

Source: tmp/plans/.claimed/71-execution-history-redesign.md
Requirements: docs/plans/2026-03-28-71-execution-history-redesign-requirements.md
Prototype: prototype_traces/ (3 screens)

## Architecture Overview

Replace the standalone Traces page (/proxy, /proxy/{run_id}, /proxy/{run_id}/narrative)
with an integrated execution history view accessible from the Completions page. The new
view renders a full recursive execution tree with a detail side panel and deep-dive modal.

### Current Architecture (being replaced)

- Routes: /proxy (list), /proxy/{run_id} (detail), /proxy/{run_id}/narrative
- Templates: proxy_list.html, proxy_trace.html, proxy_narrative.html
- Helper: trace_narrative.py (build_execution_view with 2-level depth: children + grandchildren)
- Nav link: "Traces" in base.html

### New Architecture

- Route: GET /execution-history/{run_id} (HTML page with recursive tree + side panel)
- Route: GET /api/execution-tree/{run_id} (JSON API returning full recursive tree)
- Template: execution_history.html (tree view + side panel + deep-dive modal)
- Helper: execution_tree.py (recursive tree builder with no depth limit)
- Completions trace links updated to point to /execution-history/{run_id}
- Old /proxy routes and templates removed
- "Traces" nav link removed from base.html

### Data Flow

1. User clicks trace link on Completions page
2. Browser navigates to /execution-history/{run_id}
3. Server renders page shell with loading state
4. Client JS fetches /api/execution-tree/{run_id}
5. API returns full recursive tree as JSON with computed cost/duration
6. Client renders tree in left panel, detail in right panel
7. Clicking tree nodes updates the side panel
8. "Deep Dive" button on agent nodes opens the side-by-side modal

---

## Design Decisions

### D1: Recursive Tree Fetch with No Depth Limit

Addresses: P1, UC2
Satisfies: AC1, AC2, AC3, AC11, AC12, AC13, AC14, AC15, AC16
Approach: Add a get_full_tree() method to TracingProxy that recursively fetches all
descendants of a run_id using iterative breadth-first traversal with
get_children_batch(). Returns a nested tree structure where each node contains
its children. No depth limit -- traversal continues until no more children exist.
The tree structure mirrors pipeline execution: graph nodes > executor subgraph >
agent sessions > tool calls > nested sub-tool-calls.
Files:
- Modify: langgraph_pipeline/web/proxy.py (add get_full_tree method)
- Create: langgraph_pipeline/web/helpers/execution_tree.py (tree builder + node types)
- Create: tests/langgraph/web/helpers/test_execution_tree.py

### D2: Three-Tier Name Resolution

Addresses: FR3
Satisfies: AC37, AC38, AC39, AC40
Approach: Implement a resolve_display_name() function with three-tier fallback:
(1) span metadata slug/item_slug field, (2) child span metadata scan,
(3) run_id prefix extraction. Applied during tree construction so no node
ever displays "LangGraph". The existing _scan_children_for_slug pattern in
trace_narrative.py serves as the template; the new implementation extends it
to work with the recursive tree nodes.
Files:
- Create: langgraph_pipeline/web/helpers/execution_tree.py (resolve_display_name function)

### D3: UI-Level Deduplication

Addresses: FR4
Satisfies: AC41, AC42
Approach: During tree construction, deduplicate nodes by run_id. If multiple rows
exist for the same run_id (start/end events), keep only the most complete row
(the one with end_time populated, or the latest created_at). This is a belt-and-
suspenders approach on top of the existing DB-level INSERT OR REPLACE.
Files:
- Create: langgraph_pipeline/web/helpers/execution_tree.py (dedup logic in tree builder)

### D4: Real Cost Aggregation via Recursive CTE

Addresses: P2, FR5
Satisfies: AC4, AC5, AC43, AC44, AC45, AC46
Approach: Use the existing get_child_costs_batch() recursive CTE to compute real
cost for each subtree root. During tree construction, attach aggregated cost to
each intermediate node. Leaf nodes display their own cost from metadata_json.
Nodes with no recorded cost display zero or "---" (never 0.01 placeholder).
Files:
- Create: langgraph_pipeline/web/helpers/execution_tree.py (cost aggregation in tree builder)

### D5: Real Wall-Clock Duration from Descendant Time Spans

Addresses: P3, FR6
Satisfies: AC6, AC7, AC47, AC48, AC49
Approach: Use the existing get_child_time_spans_batch() to compute real wall-clock
duration for phase-level nodes. For nodes whose own duration is near-zero
(< 1.0s), replace with the earliest-descendant-start to latest-descendant-end
span. This ensures phases that took minutes show real minutes, not 0.01s.
Files:
- Create: langgraph_pipeline/web/helpers/execution_tree.py (duration computation in tree builder)

### D6: Execution History API Endpoint

Addresses: UC2, UC3, UC5, UC6
Satisfies: AC11-AC16, AC17-AC21, AC25-AC32
Approach: Create a JSON API endpoint GET /api/execution-tree/{run_id} that returns
the full recursive tree as a JSON response. Each tree node includes: run_id, name,
display_name, node_type (graph_node | agent | tool_call | subgraph), status,
duration, cost, model, token_count, inputs_json, outputs_json, metadata_json,
children[]. The frontend uses this to render tree, side panel, and raw data toggle.
Files:
- Create: langgraph_pipeline/web/routes/execution_history.py (API endpoint)
- Modify: langgraph_pipeline/web/server.py (mount new router)
- Create: tests/langgraph/web/routes/test_execution_history.py

### D7: Remove Old Traces Page

Addresses: FR1, FR2
Satisfies: AC33, AC34, AC35, AC36
Approach: Remove the /proxy routes, templates, and navigation link. The standalone
Traces page is eliminated. Update completions trace links from /proxy?trace_id=X
to /execution-history/X. Remove the "Traces" nav link from base.html. The
Completions page becomes the sole entry point for execution history.
Files:
- Modify: langgraph_pipeline/web/templates/base.html (remove Traces nav link)
- Modify: langgraph_pipeline/web/templates/completions.html (update trace links)
- Modify: langgraph_pipeline/web/server.py (remove proxy_router include)
- Delete or deprecate: langgraph_pipeline/web/routes/proxy.py
- Delete or deprecate: langgraph_pipeline/web/templates/proxy_list.html
- Delete or deprecate: langgraph_pipeline/web/templates/proxy_trace.html
- Delete or deprecate: langgraph_pipeline/web/templates/proxy_narrative.html
- Delete or deprecate: langgraph_pipeline/web/helpers/trace_narrative.py

### D8: Execution History Page with Tree View and Side Panel (UI - Design Competition)

Addresses: UC1, UC2, UC3
Satisfies: AC8, AC9, AC10, AC11-AC16, AC17-AC21
Approach: Subject to Phase 0 design competition. Three competing designs will
propose the tree view layout, side panel interaction, and navigation flow.
The winning design will be implemented in the execution_history.html template
and associated JS/CSS. Key UI elements: collapsible tree with expand/collapse
icons, node-type badges (phase/agent/tool), side panel with tabbed content
(details/prompt-response/metadata), and contextual metrics display.
Files:
- Create: langgraph_pipeline/web/templates/execution_history.html
- Create or modify: langgraph_pipeline/web/static/execution_history.js
- Create or modify: langgraph_pipeline/web/static/style.css (additions)

### D9: Deep-Dive Prompt/Response View (UI - Design Competition)

Addresses: UC4
Satisfies: AC22, AC23, AC24
Approach: Subject to Phase 0 design competition. The deep-dive view shows system
prompt and agent response side-by-side in scrollable panels with latency and token
metrics. Implemented as a modal overlay triggered from agent nodes in the tree.
Each panel is independently scrollable. Latency and token counts displayed in a
metrics bar between or above the panels.
Files:
- Create: langgraph_pipeline/web/templates/execution_history.html (modal section)

### D10: Observability Metadata Surfacing and Raw Data Toggle (UI - Design Competition)

Addresses: UC5, UC6
Satisfies: AC25-AC32
Approach: Subject to Phase 0 design competition. Structured observability metadata
(validator verdicts, pipeline decisions, subprocess exit codes, plan state snapshots)
is extracted from metadata_json and displayed in a dedicated section of the side
panel. A "Show Raw Data" toggle (hidden by default) reveals the full JSON for
debugging. The toggle is per-node and remembers state during the session.
Files:
- Create: langgraph_pipeline/web/templates/execution_history.html (metadata section)

---

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | Recursive tree fetch with no depth limit via iterative BFS |
| AC2 | D1 | Tool calls visible at any depth in the recursive tree |
| AC3 | D1 | Nested sub-tool-calls traversed recursively |
| AC4 | D4 | Real cost from metadata_json, no placeholders |
| AC5 | D4 | Zero or absent display for nodes without cost data |
| AC6 | D5 | Duration from descendant time spans, not own timestamps |
| AC7 | D5 | Phase duration shows real wall-clock minutes |
| AC8 | D8 | Trace link on each completions row |
| AC9 | D8 | Trace link opens execution history for specific item |
| AC10 | D8 | Existing slug, outcome, cost, duration, velocity preserved |
| AC11 | D1, D8 | Tree shows top-level pipeline graph nodes |
| AC12 | D1, D8 | Tree shows executor subgraph nodes under execution |
| AC13 | D1, D8 | Tree shows agent sessions under task running |
| AC14 | D1, D8 | Tree shows tool calls under agents |
| AC15 | D1, D8 | Tree shows nested sub-tool-calls |
| AC16 | D1, D8 | No depth cutoff on tree navigation |
| AC17 | D6, D8 | Agent node shows prompt/response in side panel |
| AC18 | D6, D8 | Tool call node shows input/result in side panel |
| AC19 | D6, D8 | Graph node shows state inputs/outputs in side panel |
| AC20 | D6, D8 | Latency, token count, cost, model displayed per node |
| AC21 | D8 | Side panel updates on node selection |
| AC22 | D9 | Deep-dive shows prompt and response side-by-side |
| AC23 | D9 | Both panels independently scrollable |
| AC24 | D9 | Latency and token metrics in deep-dive view |
| AC25 | D10 | Validator verdicts displayed from metadata |
| AC26 | D10 | Pipeline decisions displayed from metadata |
| AC27 | D10 | Subprocess exit codes displayed from metadata |
| AC28 | D10 | Plan state snapshots displayed from metadata |
| AC29 | D10 | Metadata visible without opening raw JSON |
| AC30 | D10 | Raw trace data toggle present |
| AC31 | D10 | Toggle hidden by default |
| AC32 | D10 | Toggle reveals full raw trace data |
| AC33 | D7 | Standalone Traces page removed |
| AC34 | D7 | No nav link or route to old Traces page |
| AC35 | D7 | Completions page is sole execution history entry point |
| AC36 | D7 | No alternative routes for execution history |
| AC37 | D2 | "LangGraph" never displayed as item name |
| AC38 | D2 | Name resolution uses span metadata first |
| AC39 | D2 | Fallback to child span metadata lookup |
| AC40 | D2 | Final fallback to run_id prefix |
| AC41 | D3 | One row per span, no duplicates |
| AC42 | D3 | Deduplication enforced at UI rendering level |
| AC43 | D4 | Phase cost aggregated from all descendants |
| AC44 | D4 | Cost uses recursive CTE from TracingProxy |
| AC45 | D4 | Zero placeholder or dummy cost values |
| AC46 | D4 | Aggregation includes all tree levels |
| AC47 | D5 | Duration from earliest descendant start to latest end |
| AC48 | D5 | Own near-zero timestamps not used for phase duration |
| AC49 | D5 | Multi-minute phases show correct wall-clock duration |

---

## Phase 0 Design Competition Results

### Scoring Matrix

| Design | Alignment | Completeness | Feasibility | Integration | Clarity | Total |
|--------|-----------|--------------|-------------|-------------|---------|-------|
| Design 1 - Systems Architecture (0.1) | 7 | 7 | 9 | 6 | 8 | 37 |
| Design 2 - UX Design (0.2) | 9 | 9 | 8 | 8 | 9 | 43 |
| Design 3 - Frontend Implementation (0.3) | 9 | 8 | 9 | 9 | 9 | 44 |

### Winner: Design 3 - Frontend Implementation (44/50)

Design 3 wins on the strength of its implementation-readiness and codebase integration.
It provides concrete Jinja2 recursive macros, CSS Grid layouts, and vanilla JS with
named functions following existing patterns (dashboard.js, analysis.js). The server-rendered
tree approach enables progressive enhancement, and the /execution/ URL namespace cleanly
replaces the old /proxy/ routes.

### Improvements Incorporated from Runner-ups

1. **Responsive breakpoints** from Design 2: three-tier layout (1024px+, 768-1023px, <768px)
2. **WCAG 2.1 AA accessibility** from Design 2: WAI-ARIA TreeView roles, focus trapping,
   aria-live regions, prefers-reduced-motion
3. **Loading/empty states** from Design 2: skeleton shimmer, "no spans" message, node count badge

Full judgment: tmp/worker-output/71-execution-history-redesign-judgment.md
