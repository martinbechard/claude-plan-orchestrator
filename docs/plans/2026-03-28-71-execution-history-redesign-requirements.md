# Structured Requirements: 71 Execution History Redesign

Source: tmp/plans/.claimed/71-execution-history-redesign.md
Generated: 2026-03-28T22:15:01.532010+00:00

## Requirements

### P1: Shallow Tree Fetch — Only Direct Children Retrieved
Type: functional
Priority: high
Source clauses: [C30, C23]
Description: The previous implementation only fetched one level of children (direct children of the root), which meant tool calls like Read, Edit, Bash were invisible because they are grandchildren or deeper in the execution tree. This is one of 15+ recurring defects that must not recur in the redesign.
Acceptance Criteria:
- Does the tree fetch retrieve all descendants recursively with no depth limit? YES = pass, NO = fail
- Are tool calls (Read, Edit, Bash, Grep, Glob, etc.) visible in the tree even when they are grandchildren or deeper? YES = pass, NO = fail
- Can a user see a Skill call's nested sub-tool-calls in the tree? YES = pass, NO = fail

---

### P2: Placeholder Cost Values Instead of Real Data
Type: functional
Priority: high
Source clauses: [C33, C23]
Description: Previously only execute_task and validate_task recorded cost — all other nodes used 0.01 as a placeholder. This meant cost data was fundamentally inaccurate for most of the tree. This is one of 15+ recurring defects that must not recur.
Acceptance Criteria:
- Are all displayed cost values derived from actual recorded cost data rather than hardcoded placeholders? YES = pass, NO = fail
- Do nodes that have no recorded cost show a meaningful indicator (e.g., zero or absent) rather than a fake value like 0.01? YES = pass, NO = fail

---

### P3: Duration Shows Dispatch Time Instead of Wall-Clock Execution Time
Type: functional
Priority: high
Source clauses: [C36, C23]
Description: Root run timestamps show 0.01s because they measure the graph dispatch latency, not the actual execution wall-clock time. This makes duration data meaningless for understanding how long phases actually took. This is one of 15+ recurring defects that must not recur.
Acceptance Criteria:
- Is the displayed duration for a phase/node computed from its descendants' actual time ranges rather than its own span timestamps? YES = pass, NO = fail
- Does a phase that took minutes of real execution show minutes (not 0.01s)? YES = pass, NO = fail

---

### UC1: Access Execution History from Completions Page
Type: UI
Priority: high
Source clauses: [C2, C5, C6, C42]
Description: The user views the Completions page, which already displays completed work item rows with slug, outcome, cost, duration, and velocity. Each row includes a trace link. Clicking the trace link opens the execution history view for that specific item. The Completions page is the sole entry point for execution history — there is no separate Traces page to navigate to.
Acceptance Criteria:
- Does each completed work item row on the Completions page have a clickable trace link? YES = pass, NO = fail
- Does clicking the trace link open the execution history for that specific item? YES = pass, NO = fail
- Are slug, outcome, cost, duration, and velocity still visible on each row? YES = pass, NO = fail

---

### UC2: Navigate Full Recursive Execution Tree
Type: UI
Priority: high
Source clauses: [C7, C8, C9, C10, C11, C12, C13, C14, C15, C16, C29, C31, C43]
Description: The user sees a navigable tree showing everything the pipeline did for an item. The tree structure mirrors actual pipeline execution with these specific levels: (1) top-level pipeline graph nodes: intake, requirements, planning, execution, verification, archival; (2) under execution: executor subgraph nodes — task selection, task running, validation; (3) under task running: actual Claude CLI sessions (agent invocations); (4) under each agent: individual tool calls — Read, Edit, Write, Bash, Grep, Glob, Skill, etc.; (5) tool calls can nest further (e.g., a Skill call may trigger sub-tool-calls). Every level of this tree must be navigable with no depth cutoff. Users must be able to see all the way down to leaf-level tool calls. The recursive tree fetch must have no depth limit. The existing narrative template needs recursive rework.
Acceptance Criteria:
- Does the tree display top-level pipeline graph nodes (intake, requirements, planning, execution, verification, archival)? YES = pass, NO = fail
- Does the tree show executor subgraph nodes (task selection, task running, validation) under the execution node? YES = pass, NO = fail
- Does the tree show Claude CLI sessions (agent invocations) under task running? YES = pass, NO = fail
- Does the tree show individual tool calls (Read, Edit, Write, Bash, Grep, Glob, Skill, etc.) under each agent? YES = pass, NO = fail
- Does the tree show nested sub-tool-calls under tool calls like Skill? YES = pass, NO = fail
- Can the user expand/navigate every level of the tree without hitting a depth cutoff? YES = pass, NO = fail

---

### UC3: View Node Details in Side Panel
Type: UI
Priority: high
Source clauses: [C17, C18]
Description: The user selects any node in the execution tree and a side panel displays contextual details. The content varies by node type: for agent nodes, show the prompt and response; for tool call nodes, show the input and result (file path, command, etc.); for graph nodes, show state inputs/outputs. All node types display latency, token count, cost, and model where that data is available.
Acceptance Criteria:
- Does selecting an agent node show prompt and response in the side panel? YES = pass, NO = fail
- Does selecting a tool call node show input and result (file path, command, etc.) in the side panel? YES = pass, NO = fail
- Does selecting a graph node show state inputs/outputs in the side panel? YES = pass, NO = fail
- Are latency, token count, cost, and model displayed where available? YES = pass, NO = fail
- Does the side panel update when a different node is selected? YES = pass, NO = fail

---

### UC4: Deep-Dive Prompt/Response Inspection
Type: UI
Priority: medium
Source clauses: [C19, C20]
Description: The user opens a deep-dive view for prompt/response inspection. This view displays the system prompt and agent response side-by-side in scrollable panels, along with latency and token metrics. The purpose is debugging agent reasoning in complex nested chains.
Acceptance Criteria:
- Does the deep-dive view show system prompt and agent response side-by-side? YES = pass, NO = fail
- Are both panels independently scrollable? YES = pass, NO = fail
- Are latency and token metrics displayed in the deep-dive view? YES = pass, NO = fail

---

### UC5: View Surfaced Observability Metadata
Type: UI
Priority: medium
Source clauses: [C38, C39]
Description: The user sees observability metadata surfaced directly in the UI where it exists, without having to dig through raw JSON. Specific metadata types include: validator verdicts, pipeline decisions, subprocess exit codes, and plan state snapshots.
Acceptance Criteria:
- Are validator verdicts displayed when present on a node? YES = pass, NO = fail
- Are pipeline decisions displayed when present? YES = pass, NO = fail
- Are subprocess exit codes displayed when present? YES = pass, NO = fail
- Are plan state snapshots displayed when present? YES = pass, NO = fail
- Can the user see this metadata without opening raw JSON? YES = pass, NO = fail

---

### UC6: Toggle Raw Trace Data for Debugging
Type: UI
Priority: low
Source clauses: [C40]
Description: The user can toggle a "show raw trace data" view for developer debugging purposes. This toggle is hidden by default and only shown when the user explicitly activates it.
Acceptance Criteria:
- Is there a "show raw trace data" toggle? YES = pass, NO = fail
- Is the toggle hidden by default? YES = pass, NO = fail
- Does activating the toggle show the full raw trace data for the selected node? YES = pass, NO = fail

---

### FR1: Eliminate Standalone Traces Page
Type: refactoring
Priority: high
Source clauses: [C1, C3]
Description: The current standalone Traces page is removed from the application. A prototype design exists in prototype_traces/ with three screens showing the replacement concept. All execution history access is consolidated into the Completions page integration (see UC1, FR2).
Acceptance Criteria:
- Is the standalone Traces page removed from the application? YES = pass, NO = fail
- Is there no navigation link or route pointing to the old Traces page? YES = pass, NO = fail
- Does the prototype in prototype_traces/ serve as the design reference for the replacement? YES = pass, NO = fail

---

### FR2: Completions Page as Single Entry Point
Type: refactoring
Priority: high
Source clauses: [C4]
Description: The Completions page becomes the single entry point for all execution history access. There is no alternative path to view trace data — users must go through the Completions page.
Acceptance Criteria:
- Is the Completions page the only way to access execution history? YES = pass, NO = fail
- Are there no other pages or routes that provide execution history access? YES = pass, NO = fail

---

### FR3: Never Display "LangGraph" as Item Name
Type: functional
Priority: high
Source clauses: [C24, C25]
Description: The system must never display "LangGraph" as an item name. The LangSmith SDK defaults root run names to "LangGraph," but the display must always resolve to the actual item slug using a three-tier fallback: (1) from the span's own metadata if available, (2) from child span metadata lookup if not found in the span, (3) from the run_id prefix as a last resort.
Acceptance Criteria:
- Does the UI never display "LangGraph" as an item name anywhere in the execution history? YES = pass, NO = fail
- Does the name resolution use metadata as the primary source? YES = pass, NO = fail
- Does the name resolution fall back to child span metadata lookup? YES = pass, NO = fail
- Does the name resolution fall back to run_id prefix as last resort? YES = pass, NO = fail

---

### FR4: No Duplicate Rows for Start/End Events
Type: functional
Priority: high
Source clauses: [C26, C27, C28]
Description: The UI must never show duplicate rows for start/end events of the same span. The DB-level upsert fix (INSERT OR REPLACE on run_id) already prevents duplicates in storage, but the UI rendering must also enforce deduplication to ensure no visual duplicates appear regardless of data state.
Acceptance Criteria:
- Does the UI show exactly one row per span (no start/end duplicates)? YES = pass, NO = fail
- Is deduplication enforced at the UI rendering level (not solely relying on DB)? YES = pass, NO = fail

---

### FR5: Real Aggregated Cost Data
Type: functional
Priority: high
Source clauses: [C21, C22, C32, C34, C41]
Description: At the phase level, the system must show real cost computed by aggregating actual cost data across the full subtree. Cost aggregation must use the recursive CTE approach that already exists in TracingProxy (get_child_costs_batch()). No dummy or placeholder values. The display must aggregate actual costs from all levels of the tree.
Acceptance Criteria:
- Is cost at the phase level computed by aggregating all descendant costs? YES = pass, NO = fail
- Does the cost aggregation use the recursive CTE approach from TracingProxy? YES = pass, NO = fail
- Are there zero placeholder or dummy cost values (e.g., 0.01) in the display? YES = pass, NO = fail
- Does the aggregation include costs from all tree levels (not just direct children)? YES = pass, NO = fail

---

### FR6: Real Wall-Clock Duration Computation
Type: functional
Priority: high
Source clauses: [C21, C35, C37, C41]
Description: At the phase level, the system must show real wall-clock duration. Duration must be computed from the earliest descendant start timestamp to the latest descendant end timestamp, not from the span's own near-zero timestamps. The TracingProxy already provides get_child_time_spans_batch() for retrieving child time ranges to support this computation.
Acceptance Criteria:
- Is duration computed from earliest descendant start to latest descendant end? YES = pass, NO = fail
- Does the computation avoid using the span's own timestamps for phase-level duration? YES = pass, NO = fail
- Does a phase with real multi-minute execution show the correct wall-clock duration? YES = pass, NO = fail

---

## Coverage Matrix

| Raw Input Section | Requirement(s) |
|---|---|
| "The current Traces page is being eliminated" | FR1 |
| "users will access execution history directly from the Completions page" | UC1, FR2 |
| "A prototype design exists in prototype_traces/" | FR1 |
| "The Completions page becomes the single entry point" | FR2 |
| "Each completed work item row already has a slug, outcome, cost, duration, and velocity" | UC1 |
| "Add a trace link that opens the execution history for that specific item" | UC1 |
| "execution history view shows the full recursive tree" | UC2 |
| "tree structure mirrors how the pipeline actually executes" | UC2 |
| "top level: pipeline graph nodes (intake, requirements, planning, execution, verification, archival)" | UC2 |
| "Under execution: executor subgraph nodes (task selection, task running, validation)" | UC2 |
| "Under task running: actual Claude CLI sessions (agent invocations)" | UC2 |
| "Under each agent: individual tool calls (Read, Edit, Write, Bash, Grep, Glob, Skill, etc.)" | UC2 |
| "Tool calls can nest further (e.g. a Skill call may trigger sub-tool-calls)" | UC2 |
| "Every level of this tree must be navigable. No depth cutoff." | UC2 |
| "Users need to see all the way down to the leaf-level tool calls" | UC2 |
| "Selecting any node in the tree shows its details in a side panel" | UC3 |
| "Show latency, token count, cost, and model where available" | UC3 |
| "deep-dive view for prompt/response inspection — system prompt and agent response side-by-side" | UC4 |
| "debugging agent reasoning in complex nested chains" | UC4 |
| "At the phase level, show real duration and real cost" | FR5, FR6 |
| "Cost must be aggregated across the full subtree using the recursive CTE approach" | FR5 |
| "15+ defect fixes and these problems must not recur" | P1, P2, P3 |
| "Never display 'LangGraph' as an item name" | FR3 |
| "SDK defaults root run names to 'LangGraph' but display must resolve to actual item slug" | FR3 |
| "Don't show duplicate rows for start/end events" | FR4 |
| "upsert fix (INSERT OR REPLACE on run_id) already prevents duplicates in DB" | FR4 |
| "UI must never show both" | FR4 |
| "Tree must go all the way down to tool calls" | UC2 |
| "previous implementation only fetched one level of children" | P1 |
| "recursive tree fetch must have no depth limit" | UC2 |
| "Cost data must be real, not dummy values" | FR5 |
| "Previously only execute_task and validate_task recorded cost — other nodes used 0.01" | P2 |
| "display must aggregate actual costs from all levels" | FR5 |
| "Duration must be real wall-clock time" | FR6 |
| "Root run timestamps show 0.01s because they measure the graph dispatch" | P3 |
| "Compute duration from earliest descendant start to latest descendant end" | FR6 |
| "Surface observability metadata — validator verdicts, pipeline decisions, subprocess exit codes, plan state snapshots" | UC5 |
| "Don't make users dig through raw JSON" | UC5 |
| "show raw trace data toggle hidden by default" | UC6 |
| "TracingProxy already has: SQLite trace DB, get_children_batch(), get_child_costs_batch(), get_child_time_spans_batch()" | FR5, FR6 |
| "Completions page already shows slug, outcome, cost, duration with trace links" | UC1 |
| "narrative template exists but needs recursive rework" | UC2 |

---

## Clause Coverage Grid

| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 | C-GOAL | FR1 | Mapped |
| C2 | C-GOAL | UC1 | Mapped |
| C3 | C-FACT | FR1 | Mapped (prototype reference) |
| C4 | C-GOAL | FR2 | Mapped |
| C5 | C-FACT | UC1 | Mapped (existing row data context) |
| C6 | C-GOAL | UC1 | Mapped |
| C7 | C-GOAL | UC2 | Mapped |
| C8 | C-CTX | UC2 | Mapped (tree structure context) |
| C9 | C-CONS | UC2 | Mapped (tree level constraint) |
| C10 | C-CONS | UC2 | Mapped (tree level constraint) |
| C11 | C-CONS | UC2 | Mapped (tree level constraint) |
| C12 | C-CONS | UC2 | Mapped (tree level constraint) |
| C13 | C-CONS | UC2 | Mapped (tree level constraint) |
| C14 | C-GOAL | UC2 | Mapped |
| C15 | C-CONS | UC2 | Mapped (no depth cutoff constraint) |
| C16 | C-GOAL | UC2 | Mapped |
| C17 | C-GOAL | UC3 | Mapped |
| C18 | C-GOAL | UC3 | Mapped |
| C19 | C-GOAL | UC4 | Mapped |
| C20 | C-CTX | UC4 | Mapped (debugging purpose context) |
| C21 | C-GOAL | FR5, FR6 | Mapped (cost to FR5, duration to FR6) |
| C22 | C-CONS | FR5 | Mapped (recursive CTE constraint) |
| C23 | C-CTX | P1, P2, P3 | Mapped (context for all problem requirements) |
| C24 | C-GOAL | FR3 | Mapped |
| C25 | C-CONS | FR3 | Mapped (name resolution fallback constraint) |
| C26 | C-GOAL | FR4 | Mapped |
| C27 | C-FACT | FR4 | Mapped (existing upsert fact) |
| C28 | C-GOAL | FR4 | Mapped |
| C29 | C-GOAL | UC2 | Mapped |
| C30 | C-PROB | P1 | Mapped |
| C31 | C-CONS | UC2, P1 | Mapped (no depth limit constraint) |
| C32 | C-GOAL | FR5 | Mapped |
| C33 | C-PROB | P2 | Mapped |
| C34 | C-GOAL | FR5 | Mapped |
| C35 | C-GOAL | FR6 | Mapped |
| C36 | C-PROB | P3 | Mapped |
| C37 | C-CONS | FR6 | Mapped (duration computation constraint) |
| C38 | C-GOAL | UC5 | Mapped |
| C39 | C-GOAL | UC5 | Mapped |
| C40 | C-GOAL | UC6 | Mapped |
| C41 | C-FACT | FR5, FR6, UC2 | Mapped (existing infrastructure reference) |
| C42 | C-FACT | UC1 | Mapped (existing Completions page state) |
| C43 | C-CONS | UC2 | Mapped (narrative template rework constraint) |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

**AC1**: Does the tree fetch retrieve all descendants recursively with no depth limit? YES = pass, NO = fail
  Origin: Derived from C30 [PROB] (inverse: "only fetched one level" → "fetches all levels")
  Belongs to: P1
  Source clauses: [C30, C31]

**AC2**: Are tool calls (Read, Edit, Bash, Grep, Glob) visible in the tree when they are grandchildren or deeper? YES = pass, NO = fail
  Origin: Derived from C30 [PROB] (inverse: "tool calls were invisible" → "tool calls are visible")
  Belongs to: P1
  Source clauses: [C30]

**AC3**: Can a user see a Skill call's nested sub-tool-calls in the tree? YES = pass, NO = fail
  Origin: Derived from C30 [PROB] (inverse, specific case: nested tool calls beyond one level)
  Belongs to: P1
  Source clauses: [C30, C13]

**AC4**: Are all displayed cost values derived from actual recorded cost data rather than hardcoded placeholders? YES = pass, NO = fail
  Origin: Derived from C33 [PROB] (inverse: "used 0.01 as placeholder" → "uses actual data")
  Belongs to: P2
  Source clauses: [C33]

**AC5**: Do nodes without recorded cost show zero or absent rather than a fake value like 0.01? YES = pass, NO = fail
  Origin: Derived from C33 [PROB] (inverse: "placeholder 0.01" → "no fake values")
  Belongs to: P2
  Source clauses: [C33]

**AC6**: Is the displayed duration for a phase/node computed from its descendants' actual time ranges rather than its own span timestamps? YES = pass, NO = fail
  Origin: Derived from C36 [PROB] (inverse: "timestamps show 0.01s measuring dispatch" → "timestamps show real execution time")
  Belongs to: P3
  Source clauses: [C36, C37]

**AC7**: Does a phase that took minutes of real execution show minutes (not 0.01s)? YES = pass, NO = fail
  Origin: Derived from C36 [PROB] (inverse: "shows 0.01s" → "shows real wall-clock time")
  Belongs to: P3
  Source clauses: [C36]

**AC8**: Does each completed work item row on the Completions page have a clickable trace link? YES = pass, NO = fail
  Origin: Derived from C6 [GOAL] (operationalized: "add a trace link" → "is there a trace link?")
  Belongs to: UC1
  Source clauses: [C6, C42]

**AC9**: Does clicking the trace link open the execution history for that specific item (not a different item, not a generic page)? YES = pass, NO = fail
  Origin: Derived from C2 [GOAL] (operationalized: "users will access execution history directly from Completions" → "does trace link open correct history?")
  Belongs to: UC1
  Source clauses: [C2, C6]

**AC10**: Are slug, outcome, cost, duration, and velocity still visible on each completed work item row? YES = pass, NO = fail
  Origin: Derived from C6 [GOAL] (operationalized: adding trace link must not remove existing data)
  Belongs to: UC1
  Source clauses: [C5, C6, C42]

**AC11**: Does the tree display top-level pipeline graph nodes (intake, requirements, planning, execution, verification, archival)? YES = pass, NO = fail
  Origin: Derived from C7 [GOAL] (operationalized: "shows the full recursive tree" → first tree level verified)
  Belongs to: UC2
  Source clauses: [C7, C9]

**AC12**: Does the tree show executor subgraph nodes (task selection, task running, validation) under the execution node? YES = pass, NO = fail
  Origin: Derived from C7 [GOAL] (operationalized: second tree level verified)
  Belongs to: UC2
  Source clauses: [C7, C10]

**AC13**: Does the tree show Claude CLI sessions (agent invocations) under task running? YES = pass, NO = fail
  Origin: Derived from C7 [GOAL] (operationalized: third tree level verified)
  Belongs to: UC2
  Source clauses: [C7, C11]

**AC14**: Does the tree show individual tool calls (Read, Edit, Write, Bash, Grep, Glob, Skill, etc.) under each agent? YES = pass, NO = fail
  Origin: Derived from C29 [GOAL] (operationalized: "tree must go all the way down to tool calls" → verified)
  Belongs to: UC2
  Source clauses: [C29, C12]

**AC15**: Does the tree show nested sub-tool-calls under tool calls like Skill? YES = pass, NO = fail
  Origin: Derived from C16 [GOAL] (operationalized: "see all the way down to leaf-level" → deepest nesting verified)
  Belongs to: UC2
  Source clauses: [C16, C13]

**AC16**: Can the user expand/navigate every level of the tree without hitting a depth cutoff? YES = pass, NO = fail
  Origin: Derived from C14 [GOAL] (operationalized: "every level must be navigable" → navigation verified at all depths)
  Belongs to: UC2
  Source clauses: [C14, C15, C31]

**AC17**: Does selecting an agent node show prompt and response in the side panel? YES = pass, NO = fail
  Origin: Derived from C17 [GOAL] (operationalized: "for agents this means the prompt and response")
  Belongs to: UC3
  Source clauses: [C17]

**AC18**: Does selecting a tool call node show input and result (file path, command, etc.) in the side panel? YES = pass, NO = fail
  Origin: Derived from C17 [GOAL] (operationalized: "for tool calls this means the input and result")
  Belongs to: UC3
  Source clauses: [C17]

**AC19**: Does selecting a graph node show state inputs/outputs in the side panel? YES = pass, NO = fail
  Origin: Derived from C17 [GOAL] (operationalized: "for graph nodes this means state inputs/outputs")
  Belongs to: UC3
  Source clauses: [C17]

**AC20**: Are latency, token count, cost, and model displayed where available on the selected node? YES = pass, NO = fail
  Origin: Derived from C18 [GOAL] (operationalized: "show latency, token count, cost, and model" → verified per node)
  Belongs to: UC3
  Source clauses: [C18]

**AC21**: Does the side panel update when a different node is selected? YES = pass, NO = fail
  Origin: Derived from C17 [GOAL] (operationalized: "selecting any node" implies panel reflects current selection)
  Belongs to: UC3
  Source clauses: [C17]

**AC22**: Does the deep-dive view show system prompt and agent response side-by-side? YES = pass, NO = fail
  Origin: Derived from C19 [GOAL] (operationalized: "system prompt and agent response side-by-side")
  Belongs to: UC4
  Source clauses: [C19]

**AC23**: Are both panels in the deep-dive view independently scrollable? YES = pass, NO = fail
  Origin: Derived from C19 [GOAL] (operationalized: "scrollable panels")
  Belongs to: UC4
  Source clauses: [C19]

**AC24**: Are latency and token metrics displayed in the deep-dive view? YES = pass, NO = fail
  Origin: Derived from C19 [GOAL] (operationalized: "with latency and token metrics")
  Belongs to: UC4
  Source clauses: [C19]

**AC25**: Are validator verdicts displayed when present on a node? YES = pass, NO = fail
  Origin: Derived from C38 [GOAL] (operationalized: "surface observability metadata" → validator verdicts)
  Belongs to: UC5
  Source clauses: [C38]

**AC26**: Are pipeline decisions displayed when present on a node? YES = pass, NO = fail
  Origin: Derived from C38 [GOAL] (operationalized: "surface observability metadata" → pipeline decisions)
  Belongs to: UC5
  Source clauses: [C38]

**AC27**: Are subprocess exit codes displayed when present on a node? YES = pass, NO = fail
  Origin: Derived from C38 [GOAL] (operationalized: "surface observability metadata" → exit codes)
  Belongs to: UC5
  Source clauses: [C38]

**AC28**: Are plan state snapshots displayed when present on a node? YES = pass, NO = fail
  Origin: Derived from C38 [GOAL] (operationalized: "surface observability metadata" → plan state)
  Belongs to: UC5
  Source clauses: [C38]

**AC29**: Can the user see all observability metadata without opening raw JSON? YES = pass, NO = fail
  Origin: Derived from C39 [GOAL] (operationalized: "don't make users dig through raw JSON" → metadata visible natively)
  Belongs to: UC5
  Source clauses: [C39]

**AC30**: Is there a "show raw trace data" toggle in the UI? YES = pass, NO = fail
  Origin: Derived from C40 [GOAL] (operationalized: "show raw trace data toggle")
  Belongs to: UC6
  Source clauses: [C40]

**AC31**: Is the raw trace data toggle hidden by default? YES = pass, NO = fail
  Origin: Derived from C40 [GOAL] (operationalized: "hidden by default")
  Belongs to: UC6
  Source clauses: [C40]

**AC32**: Does activating the toggle show the full raw trace data for the selected node? YES = pass, NO = fail
  Origin: Derived from C40 [GOAL] (operationalized: toggle must actually reveal raw data)
  Belongs to: UC6
  Source clauses: [C40]

**AC33**: Is the standalone Traces page removed from the application? YES = pass, NO = fail
  Origin: Derived from C1 [GOAL] (operationalized: "Traces page is being eliminated" → is it gone?)
  Belongs to: FR1
  Source clauses: [C1]

**AC34**: Is there no navigation link or route pointing to the old Traces page? YES = pass, NO = fail
  Origin: Derived from C1 [GOAL] (operationalized: elimination means no residual references)
  Belongs to: FR1
  Source clauses: [C1]

**AC35**: Is the Completions page the only way to access execution history? YES = pass, NO = fail
  Origin: Derived from C4 [GOAL] (operationalized: "becomes the single entry point" → exclusivity verified)
  Belongs to: FR2
  Source clauses: [C4]

**AC36**: Are there no other pages or routes that provide execution history access? YES = pass, NO = fail
  Origin: Derived from C4 [GOAL] (operationalized: inverse check — no alternative paths exist)
  Belongs to: FR2
  Source clauses: [C4]

**AC37**: Does the UI never display "LangGraph" as an item name anywhere in the execution history? YES = pass, NO = fail
  Origin: Derived from C24 [GOAL] (operationalized: "never display LangGraph as an item name")
  Belongs to: FR3
  Source clauses: [C24]

**AC38**: Does name resolution use the span's own metadata as the primary source? YES = pass, NO = fail
  Origin: Derived from C24 [GOAL] (operationalized: first tier of fallback chain)
  Belongs to: FR3
  Source clauses: [C24, C25]

**AC39**: Does name resolution fall back to child span metadata lookup when span metadata is unavailable? YES = pass, NO = fail
  Origin: Derived from C24 [GOAL] (operationalized: second tier of fallback chain)
  Belongs to: FR3
  Source clauses: [C24, C25]

**AC40**: Does name resolution fall back to run_id prefix as last resort when both metadata sources are unavailable? YES = pass, NO = fail
  Origin: Derived from C24 [GOAL] (operationalized: third tier of fallback chain)
  Belongs to: FR3
  Source clauses: [C24, C25]

**AC41**: Does the UI show exactly one row per span (no start/end duplicates)? YES = pass, NO = fail
  Origin: Derived from C26 [GOAL] (operationalized: "don't show duplicate rows for start/end events")
  Belongs to: FR4
  Source clauses: [C26, C28]

**AC42**: Is deduplication enforced at the UI rendering level (not solely relying on DB upsert)? YES = pass, NO = fail
  Origin: Derived from C28 [GOAL] (operationalized: "UI must never show both" → UI-level guarantee required)
  Belongs to: FR4
  Source clauses: [C28, C27]

**AC43**: Is cost at the phase level computed by aggregating all descendant costs across the full subtree? YES = pass, NO = fail
  Origin: Derived from C21 [GOAL] (operationalized: "show real cost — computed from actual child span data")
  Belongs to: FR5
  Source clauses: [C21, C34]

**AC44**: Does the cost aggregation use the recursive CTE approach from TracingProxy (get_child_costs_batch)? YES = pass, NO = fail
  Origin: Derived from C34 [GOAL] (operationalized: "aggregate actual costs" → implementation uses existing CTE)
  Belongs to: FR5
  Source clauses: [C34, C22, C41]

**AC45**: Are there zero placeholder or dummy cost values (e.g., 0.01) anywhere in the display? YES = pass, NO = fail
  Origin: Derived from C32 [GOAL] (operationalized: "cost data must be real, not dummy values")
  Belongs to: FR5
  Source clauses: [C32]

**AC46**: Does the cost aggregation include costs from all tree levels (not just direct children)? YES = pass, NO = fail
  Origin: Derived from C34 [GOAL] (operationalized: "aggregate actual costs from all levels")
  Belongs to: FR5
  Source clauses: [C34, C22]

**AC47**: Is duration at the phase level computed from earliest descendant start to latest descendant end? YES = pass, NO = fail
  Origin: Derived from C21 [GOAL] (operationalized: "show real duration — computed from actual child span time ranges")
  Belongs to: FR6
  Source clauses: [C21, C37]

**AC48**: Does the duration computation avoid using the span's own near-zero timestamps for phase-level display? YES = pass, NO = fail
  Origin: Derived from C35 [GOAL] (operationalized: "duration must be real wall-clock time" → own timestamps excluded)
  Belongs to: FR6
  Source clauses: [C35, C37]

**AC49**: Does a phase with real multi-minute execution show the correct wall-clock duration (not 0.01s)? YES = pass, NO = fail
  Origin: Derived from C35 [GOAL] (operationalized: end-to-end correctness check)
  Belongs to: FR6
  Source clauses: [C35, C36]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2, AC3 | 3 |
| P2 | AC4, AC5 | 2 |
| P3 | AC6, AC7 | 2 |
| UC1 | AC8, AC9, AC10 | 3 |
| UC2 | AC11, AC12, AC13, AC14, AC15, AC16 | 6 |
| UC3 | AC17, AC18, AC19, AC20, AC21 | 5 |
| UC4 | AC22, AC23, AC24 | 3 |
| UC5 | AC25, AC26, AC27, AC28, AC29 | 5 |
| UC6 | AC30, AC31, AC32 | 3 |
| FR1 | AC33, AC34 | 2 |
| FR2 | AC35, AC36 | 2 |
| FR3 | AC37, AC38, AC39, AC40 | 4 |
| FR4 | AC41, AC42 | 2 |
| FR5 | AC43, AC44, AC45, AC46 | 4 |
| FR6 | AC47, AC48, AC49 | 3 |

---

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | GOAL | AC33, AC34 | Operationalized |
| C2 | GOAL | AC9 | Operationalized |
| C3 | FACT | -- | Design reference for FR1; not independently testable (prototype is an input artifact, not a runtime behavior) |
| C4 | GOAL | AC35, AC36 | Operationalized |
| C5 | FACT | AC10 | Context for UC1; preservation verified via AC10 |
| C6 | GOAL | AC8, AC9 | Operationalized |
| C7 | GOAL | AC11, AC12, AC13, AC14 | Operationalized (one AC per tree level) |
| C8 | CTX | -- | Structural context explaining tree shape for UC2; the shape itself is verified by AC11-AC15 |
| C9 | CONS | AC11 | Constraint operationalized as specific tree level check |
| C10 | CONS | AC12 | Constraint operationalized as specific tree level check |
| C11 | CONS | AC13 | Constraint operationalized as specific tree level check |
| C12 | CONS | AC14 | Constraint operationalized as specific tree level check |
| C13 | CONS | AC3, AC15 | Constraint operationalized as nesting depth check |
| C14 | GOAL | AC16 | Operationalized |
| C15 | CONS | AC16 | Constraint folded into navigability AC |
| C16 | GOAL | AC15 | Operationalized |
| C17 | GOAL | AC17, AC18, AC19, AC21 | Operationalized (one AC per node type + update behavior) |
| C18 | GOAL | AC20 | Operationalized |
| C19 | GOAL | AC22, AC23, AC24 | Operationalized |
| C20 | CTX | -- | Motivational context for UC4; the debugging purpose drives the design but is not a testable behavior |
| C21 | GOAL | AC43, AC47 | Operationalized (cost to AC43/FR5, duration to AC47/FR6) |
| C22 | CONS | AC44, AC46 | Constraint on implementation approach for cost aggregation |
| C23 | CTX | -- | Historical context ("15+ defects") motivating P1/P2/P3; the specific defects are tested via their respective ACs |
| C24 | GOAL | AC37, AC38, AC39, AC40 | Operationalized |
| C25 | CONS | AC38, AC39, AC40 | Constraint specifying the three-tier fallback chain |
| C26 | GOAL | AC41, AC42 | Operationalized |
| C27 | FACT | AC42 | Existing DB-level fix; AC42 verifies UI-level enforcement is not solely dependent on it |
| C28 | GOAL | AC41, AC42 | Operationalized |
| C29 | GOAL | AC14 | Operationalized |
| C30 | PROB | AC1, AC2, AC3 | Inverse |
| C31 | CONS | AC1, AC16 | Constraint folded into recursive fetch and navigability ACs |
| C32 | GOAL | AC45 | Operationalized |
| C33 | PROB | AC4, AC5 | Inverse |
| C34 | GOAL | AC43, AC44, AC46 | Operationalized |
| C35 | GOAL | AC47, AC48, AC49 | Operationalized |
| C36 | PROB | AC6, AC7, AC49 | Inverse |
| C37 | CONS | AC47, AC48 | Constraint on duration computation method |
| C38 | GOAL | AC25, AC26, AC27, AC28 | Operationalized (one AC per metadata type) |
| C39 | GOAL | AC29 | Operationalized |
| C40 | GOAL | AC30, AC31, AC32 | Operationalized |
| C41 | FACT | AC44 | Existing infrastructure reference; AC44 verifies the CTE approach is actually used |
| C42 | FACT | AC10 | Existing Completions page state; AC10 verifies existing fields are preserved |
| C43 | CONS | -- | Implementation constraint ("narrative template needs recursive rework"); verified indirectly by UC2's tree ACs (AC11-AC16) which require the reworked template to pass |
