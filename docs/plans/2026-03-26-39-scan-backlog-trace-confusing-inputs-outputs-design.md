# Design: scan_backlog Trace — Confusing Inputs/Outputs (Defect 39)

## Problem

When viewing a scan_backlog trace, the "Inputs" section shows the fully-populated
work item (item_path, item_slug, item_type already set) while "Outputs" is `{}`.
This looks backwards: scan_backlog's job is to find the next item, so it seems like
it received the answer it was supposed to produce.

Root cause: LangGraph passes the full graph state as "inputs" to every node, not
just the node's actual parameters. When the CLI pre-scans the backlog and populates
state before invoking the graph, scan_backlog short-circuits with `return {}` — so
the trace accurately reflects the LangGraph convention, but it is misleading to
anyone unfamiliar with that convention.

## Fix

Three complementary changes targeting the trace detail UI and the scan_backlog node:

### 1. Relabel in proxy_trace.html (Option 1 from defect)

In the "Run data" section, change:
- "Inputs" → "State before"
- "Outputs" → "State changes"

This makes the LangGraph semantics explicit: "inputs" is the full state snapshot
entering the node, and "outputs" is the partial state returned (which can be empty
when the node short-circuits).

Only the "Run data" section (main run) is relabeled. The grandchildren section
(tool call Inputs/Outputs) keeps its original labels because those are actual
tool call arguments and results, not graph state snapshots.

### 2. Hide empty state-changes (Option 3 from defect)

If `outputs_json` parses to an empty dict `{}`, suppress the "State changes" section
entirely rather than showing an empty block. Uses the existing `fromjson` Jinja2
filter to parse and test emptiness.

### 3. Short-circuit metadata in scan.py (Option 2 from defect)

When scan_backlog detects that `item_path` is already populated and short-circuits,
call `add_trace_metadata` with `{"short_circuited": True, "short_circuit_reason":
"item pre-scanned by CLI"}`. This makes the reason visible in the Metadata section
of the trace viewer for anyone investigating the empty State changes block.

## Files to Modify

- `langgraph_pipeline/web/templates/proxy_trace.html` — relabel and conditionally
  hide the State changes block in the "Run data" section
- `langgraph_pipeline/pipeline/nodes/scan.py` — add trace metadata on short-circuit
- `plugin.json` and `RELEASE-NOTES.md` — version bump (patch)
