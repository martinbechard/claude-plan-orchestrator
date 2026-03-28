# Design: Rename Misleading Graph Nodes (#41)

## Status

Code-level renames were previously completed. Stale references remain in
documentation and comments. This plan addresses the remaining cleanup.

## What was already done

The following renames are complete in source code (edges.py, graph.py,
verification.py) and tests (test_edges.py):

- verify_symptoms -> verify_fix
- is_defect -> route_after_execution
- after_intake -> route_after_intake
- after_create_plan -> route_after_plan

## Remaining work

Stale old names appear in documentation and code comments:

### README.md
- Line 450: ASCII diagram references "verify_symptoms"
- Line 678: description says "verify_symptoms"
- Line 738: file tree comment says "verify_symptoms"

### design/architecture/langgraph-pipeline-architecture.md
- Line 95: diagram references "has_items?"
- Line 114: diagram references "is_defect?"

### langgraph_pipeline/pipeline/nodes/scan.py
- Lines 11, 255: comments reference "has_items conditional"

## Approach

Single task: update all stale references to use the new names. The coder agent
will read the work item file for the full mapping and update all documentation
and comments to match the current code.

## Key files to modify

- README.md
- design/architecture/langgraph-pipeline-architecture.md
- langgraph_pipeline/pipeline/nodes/scan.py


## Acceptance Criteria

- Is verify_symptoms renamed to verify_fix in graph.py, the node function,
  trace metadata, and all references? YES = pass, NO = fail
- Do traces for a defect run show "verify_fix" instead of "verify_symptoms"?
  YES = pass, NO = fail
- Do all tests pass after the rename? YES = pass, NO = fail
- Are the edge function names updated consistently? YES = pass, NO = fail
