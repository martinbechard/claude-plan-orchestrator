# Design: Wire Up Real Cost Data Pipeline (#33)

## Context

This item has been "completed" twice with fake implementations where test data
was inserted into the DB rather than real pipeline data flowing through. Defect
#30 fixed the env var wiring (ENV_ORCHESTRATOR_WEB_URL is now set in cli.py
after the web server starts). The pipeline should now POST real cost data.

The remaining work is to validate end-to-end flow and clean up stale test data.

## Architecture

The cost data pipeline is already wired:

```
task_runner.py / validator.py
  -> _post_cost_to_api()
  -> reads ENV_ORCHESTRATOR_WEB_URL from env
  -> POST /api/cost (langgraph_pipeline/web/routes/cost.py)
  -> INSERT into cost_tasks table (orchestrator-traces.db)
  -> /analysis page reads cost_tasks and renders
```

cli.py sets ENV_ORCHESTRATOR_WEB_URL after starting the web server:
```
os.environ[ENV_ORCHESTRATOR_WEB_URL] = f"http://localhost:{web_port}"
```

## What Needs to Happen

### 1. Clean up fake test data
Delete all rows with item_slug="12-test-item" from cost_tasks table in the
traces DB (~/.claude/orchestrator-traces.db).

### 2. Validate real data flow
Verify that _post_cost_to_api is called with correct parameters during a real
pipeline run. Check that:
- ENV_ORCHESTRATOR_WEB_URL is set before task execution begins
- The POST payload contains real item slugs from plan meta.source_item
- cost_usd, input_tokens, output_tokens come from actual Claude API usage
- /analysis page renders the real data

### 3. Guard against future fake data
Add a warning log if cost_usd is exactly 0.01 with input_tokens=100 and
output_tokens=50 (the known fake data pattern) to catch future test insertions.

## Key Files

| File | Action |
|------|--------|
| langgraph_pipeline/executor/nodes/task_runner.py | Verify _post_cost_to_api wiring |
| langgraph_pipeline/executor/nodes/validator.py | Verify _post_cost_to_api wiring |
| langgraph_pipeline/cli.py | Verify ENV_ORCHESTRATOR_WEB_URL set before pipeline |
| langgraph_pipeline/web/routes/cost.py | Verify /api/cost endpoint accepts real data |
| langgraph_pipeline/web/routes/analysis.py | Verify /analysis renders real data |
| langgraph_pipeline/web/proxy.py | DB cleanup of fake rows |

## Design Decisions

1. **No new configuration needed** -- ENV_ORCHESTRATOR_WEB_URL is already auto-set
   by cli.py, satisfying the "no manual env var setup" acceptance criterion
2. **DB cleanup via one-time script** -- delete fake data rows rather than
   migrating or recreating the table
3. **Validation focus** -- since the wiring exists, the task is primarily
   verification and cleanup, not new feature development
