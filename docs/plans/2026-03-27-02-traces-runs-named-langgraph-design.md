# Design: Traces Runs Named LangGraph (Validation)

## Problem

Every root trace in the LangSmith proxy was named "LangGraph" with slug
"LangGraph", making the traces list unreadable. This defect was previously
implemented and is now in "Review Required" status.

## Prior Implementation

Fixes were applied across three code paths:

1. **finalize_root_run** (langgraph_pipeline/shared/langsmith.py:314-344):
   Now accepts item_slug parameter and uses it as RunTree name instead of "root".

2. **cli.py graph invocations** (langgraph_pipeline/cli.py:440-442, 510-512, 747-749):
   All three invocation paths (single-item, once, loop) now set run_name in
   thread_config from the item_slug.

3. **executor subgraph** (langgraph_pipeline/pipeline/nodes/execute_plan.py:75):
   Passes item_slug as run_name in executor config.

## Acceptance Criteria to Validate

1. Root traces in DB have names matching actual work item slugs (not "LangGraph")
2. The /proxy traces list page shows item slug in the Name column
3. Filtering traces by slug name returns meaningful results

## Key Files

| File | Role |
|------|------|
| langgraph_pipeline/shared/langsmith.py | create_root_run / finalize_root_run |
| langgraph_pipeline/cli.py | run_name in thread_config |
| langgraph_pipeline/pipeline/nodes/execute_plan.py | executor run_name config |
| langgraph_pipeline/web/routes/proxy.py | Trace list display and slug filter |
| langgraph_pipeline/web/proxy.py | SQLite trace storage and query |
| tests/langgraph/shared/test_langsmith.py | Unit tests for langsmith helpers |

## Design Decisions

- This is a validation-only plan: verify the existing code changes work
- If any acceptance criterion fails, fix the specific code path
- No DB migration needed: new traces get correct names, old rows remain
