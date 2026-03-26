# Design: Fix Cost Posting Env Var and Wiring

## Problem

`_post_cost_to_api` in `task_runner.py` and `validator.py` uses `LANGCHAIN_ENDPOINT`
(a LangSmith SDK setting) to determine where to post cost data. It only fires when
that variable starts with `http://localhost`. Since `LANGCHAIN_ENDPOINT` is only set
to a localhost URL when the local tracing proxy is active, and the pipeline is
typically run without `--web`, cost data is never posted.

## Fix Strategy

### 1. Introduce `ORCHESTRATOR_WEB_URL` as a dedicated env var

Add a constant `ENV_ORCHESTRATOR_WEB_URL = "ORCHESTRATOR_WEB_URL"` in
`langgraph_pipeline/shared/paths.py` (or a new `constants.py`). This variable
holds the base URL of the local web server when it is running.

### 2. Set `ORCHESTRATOR_WEB_URL` at pipeline startup

In `cli.py`, after `start_web_server()` returns the active port, set:

```python
os.environ[ENV_ORCHESTRATOR_WEB_URL] = f"http://localhost:{web_port}"
```

Worker subprocesses inherit the env var from the supervisor process, so no further
propagation logic is needed.

### 3. Update `_post_cost_to_api` in both nodes

Replace the `LANGCHAIN_ENDPOINT` guard with `ORCHESTRATOR_WEB_URL`:

```python
endpoint = os.environ.get("ORCHESTRATOR_WEB_URL", "")
if not endpoint:
    return
url = f"{endpoint}/api/cost"
```

The `startswith("http://localhost")` check is no longer needed because the variable
is only ever set to a localhost URL by the pipeline itself.

### 4. Clean up fake test rows

The stale `item_slug = 'test'` rows were already deleted by work item 32. No further
DB cleanup is needed for this work item.

## Key Files to Modify

- `langgraph_pipeline/shared/paths.py` — add `ENV_ORCHESTRATOR_WEB_URL` constant
- `langgraph_pipeline/cli.py` — set `ORCHESTRATOR_WEB_URL` after web server starts
- `langgraph_pipeline/executor/nodes/task_runner.py` — use `ORCHESTRATOR_WEB_URL`
- `langgraph_pipeline/executor/nodes/validator.py` — use `ORCHESTRATOR_WEB_URL`

## Design Decisions

- `ORCHESTRATOR_WEB_URL` is set in the supervisor process environment; workers
  inherit it automatically via `os.fork` / subprocess env inheritance.
- `LANGCHAIN_ENDPOINT` continues to serve its intended purpose (LangSmith routing)
  and is no longer touched by cost-posting logic.
- The cleanup DELETE is idempotent and safe to run on every startup.
- No config file change needed; the URL is derived from the active port at runtime.
