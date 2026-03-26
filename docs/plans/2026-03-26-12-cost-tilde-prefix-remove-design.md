# Design: Remove ~ Prefix from Cost Displays

## Overview

Cost values throughout the codebase use a `~$` prefix (e.g. `~$0.0123`) intended
to signal that API costs are estimates. The tilde is visually noisy and adds no
useful information. This change removes the tilde everywhere, displaying plain
`$0.0123` instead.

## Affected Files

### Backend Python

- `langgraph_pipeline/shared/budget.py` — 7 occurrences in log/summary strings
- `langgraph_pipeline/supervisor.py` — 6 occurrences in log and Slack messages
- `langgraph_pipeline/cli.py` — 5 occurrences in log strings
- `langgraph_pipeline/worker.py` — 1 occurrence in log string
- `langgraph_pipeline/executor/nodes/task_runner.py` — 1 occurrence in file write
- `langgraph_pipeline/pipeline/nodes/execute_plan.py` — 1 occurrence in summary string
- `scripts/plan-orchestrator.py` — 4 occurrences in log/Slack strings

### Frontend

- `langgraph_pipeline/web/static/dashboard.js` — 2 occurrences in `formatCost()`
- `langgraph_pipeline/web/templates/analysis.html` — 4 occurrences in column headers and cell values
- `langgraph_pipeline/web/routes/proxy.py` — 1 occurrence in `display_cost` field

### Tests

- `tests/test_token_usage.py` — 3 assertions checking for `~$` must be updated to `$`

## Design Decisions

- Strip only the `~` character, leaving `$` and all formatting unchanged.
- No tooltip or footnote is added; the backlog item defers that as optional.
- The `analysis.html` column header `Cost (~$)` becomes `Cost ($)`.
- The `proxy_list.html` template renders `display_cost` set by `proxy.py`, so
  fixing `proxy.py` is sufficient for that template.
- Tests asserting `~$` strings must be updated to `$` to stay green.
