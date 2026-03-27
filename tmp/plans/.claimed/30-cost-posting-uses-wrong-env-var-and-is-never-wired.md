# Cost data posting piggybacked on LANGCHAIN_ENDPOINT and never wired up

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: High

## Summary

The POST /api/cost calls in task_runner.py and validator.py only fire when
the env var LANGCHAIN_ENDPOINT starts with "http://localhost". This variable
is a LangSmith SDK setting for trace routing, not a cost API endpoint. The
cost posting was piggybacked on it, and since it was never explicitly set in
the pipeline config, no real cost data has ever been posted.

## Fix

1. Create a dedicated env var or config setting for the cost API endpoint
   (e.g. ORCHESTRATOR_WEB_URL or read from orchestrator-config.yaml under
   web.url). Do not reuse LANGCHAIN_ENDPOINT for non-LangSmith purposes.
2. Set the web server URL automatically during pipeline startup (the web
   server already knows its own port).
3. Update _post_cost_to_api in task_runner.py and validator.py to read
   from the new config source.
4. Delete the fake "12-test-item" rows from the cost_tasks table.
5. Verify that after the fix, running a real work item produces real rows
   in cost_tasks with actual token counts and costs.

## LangSmith Trace: f919c58c-c72c-4264-b85d-b8bfa4248780
