# Design: Validate Cost Posting Env Var Fix (Review Pass)

## Problem

The cost posting infrastructure was previously fixed to use a dedicated
`ORCHESTRATOR_WEB_URL` env var instead of piggybacking on `LANGCHAIN_ENDPOINT`.
The backlog item is marked "Review Required" -- the implementation needs
validation that all acceptance criteria are met.

## Current State (Already Implemented)

1. `ENV_ORCHESTRATOR_WEB_URL` constant exists in `langgraph_pipeline/shared/paths.py`
2. `cli.py` sets `ORCHESTRATOR_WEB_URL` after `start_web_server()` returns
3. `_post_cost_to_api` in both `task_runner.py` and `validator.py` reads from
   `ORCHESTRATOR_WEB_URL` instead of `LANGCHAIN_ENDPOINT`
4. Fake test rows were cleaned up by work item 32

## Validation Tasks

1. Verify no remaining references to `LANGCHAIN_ENDPOINT` in cost-posting code
   paths (task_runner.py, validator.py)
2. Verify `ORCHESTRATOR_WEB_URL` is set correctly in cli.py after web server start
3. Verify tests cover the updated env var usage
4. Fix any gaps found during validation

## Key Files

- `langgraph_pipeline/shared/paths.py` -- `ENV_ORCHESTRATOR_WEB_URL` constant
- `langgraph_pipeline/cli.py` -- sets env var after web server starts
- `langgraph_pipeline/executor/nodes/task_runner.py` -- `_post_cost_to_api`
- `langgraph_pipeline/executor/nodes/validator.py` -- `_post_cost_to_api`

## Design Decisions

- No new code needed unless validation finds gaps
- The env var is set in the supervisor process; workers inherit via subprocess env
- `LANGCHAIN_ENDPOINT` remains dedicated to LangSmith SDK trace routing
