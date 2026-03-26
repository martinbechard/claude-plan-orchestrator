# Design: Rename Misleading Graph Node Names (Defect 41)

## Overview

Several LangGraph node and edge function names are misleading. This design covers
renaming them to match the naming pattern established in the codebase and to
accurately reflect what each node/edge does.

## Renames Required

### Node function: verify_symptoms → verify_fix

- File: langgraph_pipeline/pipeline/nodes/verification.py
  - Rename function `verify_symptoms` to `verify_fix`
  - Update all internal `print` log tags from `[verify_symptoms]` to `[verify_fix]`
  - Update `node_name` in `add_trace_metadata` call from `"verify_symptoms"` to `"verify_fix"`
- File: langgraph_pipeline/pipeline/nodes/__init__.py
  - Update import and re-export from `verify_symptoms` to `verify_fix`
- File: langgraph_pipeline/pipeline/graph.py
  - Rename constant `NODE_VERIFY_SYMPTOMS` to `NODE_VERIFY_FIX`, value `"verify_fix"`
  - Update module docstring graph topology comment
  - Update import from nodes package
  - Update all uses of the constant and node string
- File: langgraph_pipeline/pipeline/edges.py
  - Rename constant `NODE_VERIFY_SYMPTOMS` to `NODE_VERIFY_FIX`, value `"verify_fix"`
  - Rename function `is_defect` to `route_after_execution`
  - Rename function `after_intake` to `route_after_intake`
  - Rename function `after_create_plan` to `route_after_plan`
  - Update all internal references to use new constants and names
  - Update docstrings to reflect new names

### Edge function renames (edges.py)

| Old name          | New name               | Reason                               |
|-------------------|------------------------|--------------------------------------|
| is_defect         | route_after_execution  | It routes post-execution, not checks |
| after_intake      | route_after_intake     | Matches route_after_* pattern        |
| after_create_plan | route_after_plan       | Matches route_after_* pattern        |

Note: `verify_result` already has a clear name — no rename needed.

### graph.py wiring updates

The `add_conditional_edges` calls must use the renamed edge functions imported from edges.py.

## Files to Modify

- langgraph_pipeline/pipeline/nodes/verification.py
- langgraph_pipeline/pipeline/nodes/__init__.py
- langgraph_pipeline/pipeline/graph.py
- langgraph_pipeline/pipeline/edges.py
- tests/langgraph/pipeline/test_edges.py
- tests/langgraph/pipeline/test_graph_integration.py

## No State or Behavior Changes

This is a pure rename. No logic changes, no state field changes. All string node
names registered with LangGraph must match new constants exactly.

## Test Strategy

All existing tests must pass after the rename. Update test references from old
names to new names. Run the full test suite to confirm no regressions.
