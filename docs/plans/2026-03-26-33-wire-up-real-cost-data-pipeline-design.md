# Design: Wire Up Real Cost Data Pipeline (Item 33)

## Problem

The /analysis page shows dummy data. Two previous implementation attempts were
fake: test rows were inserted directly into the DB, the page rendered them, and
the validator accepted it. No real pipeline data ever flowed through.

## Root Cause (from code analysis)

The cost POSTing code is already correct — `task_runner.py` and `validator.py`
call `_post_cost_to_api()` which reads `ORCHESTRATOR_WEB_URL` and POSTs to
`/api/cost`. The env var is set in `cli.py` at line 836 only when
`web_enabled` is True.

`web_enabled` is computed as:
```python
web_enabled = args.web or (config.get("web", {}).get("enabled", False))
```

The orchestrator-config.yaml has `web: { port: 7070 }` but NOT `enabled: true`.
So unless `--web` is passed on the command line, the web server never starts,
`ORCHESTRATOR_WEB_URL` is never set, and `_post_cost_to_api()` silently skips.

## Fix

Extend the `web_enabled` check in `cli.py` to also enable web when `web.port`
is configured:
```python
web_config = config.get("web", {})
web_enabled = args.web or web_config.get("enabled", False) or bool(web_config.get("port"))
```

This satisfies acceptance criterion: "Is the web server URL configured
automatically without requiring manual env var setup?"

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/cli.py` | Fix `web_enabled` to check `web.port` |
| `~/.claude/orchestrator-traces.db` | DELETE fake 12-test-item rows |

## Data Model

Cost records flow: pipeline worker -> `_post_cost_to_api()` -> `POST /api/cost`
-> `TracingProxy.record_cost_task()` -> `cost_tasks` table in SQLite DB at
`~/.claude/orchestrator-traces.db`.

The /analysis page reads from `cost_tasks` via `proxy.list_cost_runs()`.

## Acceptance Criteria Mapping

- cost_tasks has real slug + cost > $0.00: satisfied by the cli.py fix
- /analysis shows real slug (not 12-test-item): satisfied by deleting fake rows + fix
- Web URL auto-configured: satisfied by cli.py fix
- Zero 12-test-item rows: satisfied by DB cleanup task
- Cost matches completions table: satisfied by the existing `_post_cost_to_api()` logic
  using `total_cost_usd` from Claude CLI output
