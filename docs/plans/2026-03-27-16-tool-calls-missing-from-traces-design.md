# Design: Defect 16 - Tool Calls Missing from Traces

## Status

Previously implemented. This plan validates the existing implementation and fixes
any remaining gaps.

## Architecture Overview

Tool calls (Read, Edit, Bash, Glob, Grep, Skill, Write) are stored in the traces
DB as children of graph node runs (execute_plan, create_plan, etc.), making them
grandchildren of the root run. The original defect was that only direct children
were fetched, hiding tool calls from the UI.

## Current Implementation

The fix has already been applied across three layers:

### Backend (proxy.py route)

- proxy_trace route fetches grandchildren via get_children_batch()
- Builds grandchildren_by_parent dict mapping parent run_id to enriched tool calls
- Passes grandchildren_by_parent and grandchild_counts to the template

### Timeline SVG (proxy_trace.html)

- Total row count includes grandchildren for correct SVG sizing
- Grandchild bars rendered indented under parent graph nodes
- Distinct colour coding: Tool (cyan #0891b2), LLM (purple #7c3aed), Other (amber #f59e0b)
- Connector lines visually link grandchildren to parents

### Detail Section (proxy_trace.html)

- Expandable details/summary sections per parent with tool call count
- Each tool call shows: name, duration, elapsed offset, error (if any)
- Collapsible inputs/outputs JSON blocks

## Key Files

- langgraph_pipeline/web/routes/proxy.py (proxy_trace route, lines 213-272)
- langgraph_pipeline/web/proxy.py (get_children, get_children_batch methods)
- langgraph_pipeline/web/templates/proxy_trace.html (SVG + detail rendering)

## Acceptance Criteria

Per the backlog item:

1. Trace detail page shows tool calls nested under parent graph nodes
2. Timeline displays tool calls as bars within parent node time span
3. Tool calls are visually distinguishable (colour coding)

## Validation Approach

The coder task will validate the existing implementation against the acceptance
criteria, run the test suite to confirm no regressions, and fix any issues found.
