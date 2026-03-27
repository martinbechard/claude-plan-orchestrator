# Design: Tool Calls Missing from Traces (#16)

## Status: Review Required

This defect was previously implemented. The design below documents the
architecture for verification and any remaining fixes.

## Architecture Overview

Tool calls (Read, Edit, Bash, etc.) are stored in the traces DB as children of
graph node runs (execute_plan, create_plan), making them grandchildren of the
root run. The trace detail page must fetch and display these grandchildren.

### Current Implementation

The following components already exist:

1. **Grandchild fetching** (proxy.py route, lines ~213-272):
   - `count_children_batch(child_ids)` counts grandchildren per child
   - `get_children_batch(run_ids)` fetches all grandchildren in one query
   - `grandchildren_by_parent` dict passed to template

2. **Timeline SVG rendering** (proxy_trace.html):
   - Grandchild bars rendered indented under parent nodes (GC_INDENT = 16px)
   - Connector lines between parent and grandchild bars
   - Color classification: Tool (cyan), LLM (purple), Other (amber)
   - Tool name set: Bash, Edit, Write, Read, Glob, Grep, Skill, MultiEdit, NotebookEdit

3. **Expandable detail sections** (proxy_trace.html lines ~319-360):
   - Details/summary toggles per child showing nested tool calls
   - Inputs/outputs JSON blocks for each tool call

4. **Batch query** (proxy.py TracingProxy):
   - `get_children_batch()` uses IN clause to avoid N+1 queries
   - `count_children_batch()` returns count map for UI decisions

## Key Files

| File | Role |
|------|------|
| langgraph_pipeline/web/routes/proxy.py | Route fetching root, children, grandchildren |
| langgraph_pipeline/web/proxy.py | TracingProxy DB methods (get_children, get_children_batch) |
| langgraph_pipeline/web/templates/proxy_trace.html | Timeline SVG + expandable detail rendering |
| tests/langgraph/web/test_proxy.py | Tests for proxy routes and DB methods |

## Verification Focus

Since this was previously implemented, the task is to verify:

1. Grandchildren are actually fetched and passed to the template
2. Timeline SVG renders tool call bars correctly under parent nodes
3. Expandable sections show tool call details
4. Color classification works for all tool types
5. Edge cases: runs with no grandchildren, runs with many grandchildren
6. Tests cover grandchild fetching and display

## Design Decisions

- Reuse existing implementation rather than rewrite
- Fix any gaps found during verification
- Ensure test coverage for grandchild fetching path
