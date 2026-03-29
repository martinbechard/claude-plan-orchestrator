# Execution History Redesign — Replace Traces Page

## What We Want

The current Traces page is being eliminated. Instead, users will access execution history directly from the Completions page. A prototype design exists in prototype_traces/ with three screens showing the concept.

The Completions page becomes the single entry point. Each completed work item row already has a slug, outcome, cost, duration, and velocity. Add a trace link that opens the execution history for that specific item.

The execution history view shows the full recursive tree of everything the pipeline did for that item. The tree structure mirrors how the pipeline actually executes:

- At the top level: the pipeline graph nodes (intake, requirements, planning, execution, verification, archival)
- Under execution: the executor subgraph nodes (task selection, task running, validation)
- Under task running: the actual Claude CLI sessions (the agent invocations)
- Under each agent: the individual tool calls (Read, Edit, Write, Bash, Grep, Glob, Skill, etc.)
- Tool calls can nest further (e.g. a Skill call may trigger sub-tool-calls)

Every level of this tree must be navigable. No depth cutoff. Users need to see all the way down to the leaf-level tool calls to understand what the agent actually did.

Selecting any node in the tree shows its details in a side panel — for agents this means the prompt and response, for tool calls this means the input and result (file path, command, etc.), and for graph nodes this means the state inputs/outputs. Show latency, token count, cost, and model where available.

There should also be a deep-dive view for prompt/response inspection — system prompt and agent response side-by-side in scrollable panels with latency and token metrics. This is for debugging agent reasoning in complex nested chains.

At the phase level, show real duration and real cost — computed from the actual child span time ranges, not the span's own near-zero timestamps. Cost must be aggregated across the full subtree using the recursive CTE approach that already exists in the proxy.

## Important Lessons from Past Fixes

The traces page has been through 15+ defect fixes and these problems must not recur:

Never display "LangGraph" as an item name. The SDK defaults root run names to "LangGraph" but the display must always resolve to the actual item slug — from metadata if available, from child span metadata lookup if not, or from the run_id prefix as last resort.

Don't show duplicate rows for start/end events. The upsert fix (INSERT OR REPLACE on run_id) already prevents duplicates in the DB, but the UI must never show both.

The tree must go all the way down to tool calls. The previous implementation only fetched one level of children (direct children of the root), which meant tool calls like Read, Edit, Bash were invisible because they're grandchildren or deeper. The recursive tree fetch must have no depth limit.

Cost data must be real, not dummy values. Previously only execute_task and validate_task recorded cost — other nodes used 0.01 as a placeholder. The display must aggregate actual costs from all levels.

Duration must be real wall-clock time. Root run timestamps show 0.01s because they measure the graph dispatch, not the actual execution. Compute duration from earliest descendant start to latest descendant end.

Surface observability metadata where it exists — validator verdicts, pipeline decisions, subprocess exit codes, plan state snapshots. Don't make users dig through raw JSON.

Keep a "show raw trace data" toggle hidden by default for developer debugging.

## Existing Infrastructure

The TracingProxy in langgraph_pipeline/web/proxy.py already has: SQLite trace DB, get_children_batch() for direct children, get_child_costs_batch() with recursive CTE for cost aggregation, get_child_time_spans_batch() for child time ranges. The Completions page already shows slug, outcome, cost, duration with trace links. The narrative template exists but needs recursive rework.




## 5 Whys Analysis

**Title:** Redesign Execution History as Recursive Tree Integrated into Completions Page

**Clarity:** 4/5

The request is detailed and well-structured with clear goals, existing infrastructure, and specific known defects to avoid. Minor ambiguity around deep-dive modal usage patterns and observability metadata prioritization.

---

**5 Whys:**

**W1:** Why are we redesigning how users access execution history?
  
  Because: The current Traces page is being eliminated [C1], forcing a redesign of how users can view pipeline execution details [C2]. A prototype demonstrates the redesigned approach [C3].

**W2:** Why move execution history to the Completions page instead of keeping it in a standalone Traces section?
  
  Because: The Completions page is becoming the single entry point [C4]. Each completed work item row already displays the metadata needed (slug, outcome, cost, duration) [C5], making it the natural place to add a trace link that opens execution history for that specific item [C6].

**W3:** Why must the execution history show a complete recursive tree with no depth cutoff?
  
  Because: Users need to understand what the pipeline actually did at every level [C16]—from top-level graph nodes [C9, C10] through agent invocations [C11] down to individual tool calls [C12] and nested sub-calls [C13]. This full visibility is essential for debugging agent reasoning in complex nested chains [C24].

**W4:** Why has the previous Traces implementation accumulated 15+ defects instead of stabilizing?
  
  Because: It has fundamental architectural failures [C28]: it only fetches direct children [C38], making grandchildren tool calls invisible [C39]. It displays incorrect item names (defaults to "LangGraph" instead of resolving actual slugs) [C30-C32], shows duplicate start/end event rows [C34-C36], uses placeholder cost values instead of real aggregated costs [C41-C43], and computes duration from dispatch time rather than actual execution wall-clock [C45-C46].

**W5:** Why rebuild with a properly recursive architecture instead of patching these defects again?
  
  Because: The infrastructure to solve these problems correctly now exists [C52]—recursive CTEs for cost aggregation, complete tree traversal, and metadata resolution. These defects recur [C28] because the previous approach was fundamentally incomplete [C37-C47]. A clean rebuild using proper recursive tree fetching [C40], real cost aggregation [C44], and wall-clock duration computation [C47] will eliminate root causes rather than apply another temporary fix. [ASSUMPTION: patch-based fixes have diminishing returns and consume ongoing engineering effort]

---

**Root Need:** Replace a defect-prone standalone Traces page [C1, C28] with an integrated execution history on the Completions page [C4] that displays a complete, recursively-fetched tree with no depth limit [C7, C16, C40], accurate aggregated cost [C44] and real wall-clock duration [C47], and permanent resolution of 15+ recurring data quality defects [C29-C47], leveraging the existing TracingProxy infrastructure [C52].

**Summary:** Redesign execution history as a complete, navigable recursive tree integrated into the Completions page with accurate aggregated cost and duration, replacing a systemically defect-prone standalone Traces page.
