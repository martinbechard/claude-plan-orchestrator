# Unified LangGraph Pipeline Runner

## Status: Open

## Priority: High

## Summary

A single entry point script that runs the complete LangGraph pipeline graph,
replacing both auto-pipeline.py (backlog scanning, intake, verification loop)
and plan-orchestrator.py (task execution) with one invocation. The legacy
scripts remain untouched as the v1 runtime for fallback support.

The pipeline StateGraph from langgraph_pipeline/pipeline/graph.py already
encodes the full workflow (scan, intake, plan creation, execute, verify,
archive) and the executor subgraph already replaces what plan-orchestrator.py
did. This feature wires everything together behind a single CLI.

## Scope

### Entry Point Script

Create scripts/run-pipeline.py (or langgraph_pipeline/__main__.py) that:

1. Parses CLI arguments (budget cap, dry-run, single-item mode, backlog paths,
   log level, Slack enable/disable)
2. Loads configuration from .claude/slack.local.yaml via shared/config.py
3. Configures LangSmith tracing via shared/langsmith.py
4. Initializes the Slack facade from slack/__init__.py
5. Builds the pipeline StateGraph with SqliteSaver checkpointing
6. Runs the graph in a continuous scan loop or single-item mode
7. Handles graceful shutdown on SIGINT/SIGTERM with PID file
   (.claude/plans/.pipeline.pid)

### CLI Arguments

At minimum, support the same controls the legacy scripts expose:

- --budget-cap: Maximum API cost in dollars before stopping
- --dry-run: Scan and intake only, do not execute plans
- --single-item PATH: Process one backlog item and exit
- --backlog-dir: Override default backlog directory paths
- --log-level: DEBUG, INFO, WARNING, ERROR
- --no-slack: Disable Slack notifications
- --no-tracing: Disable LangSmith tracing

### Process Management

- Write PID file at startup, remove on shutdown (reuse shared/paths.py constants)
- Forward SIGINT/SIGTERM to graceful graph interruption via LangGraph interrupt
- Log startup banner with version, config summary, and budget cap
- Exit codes: 0 = clean shutdown, 1 = error, 2 = budget exhausted

### In-Process Execution

The pipeline graph node execute_plan currently bridges to plan-orchestrator.py
as a subprocess. This feature replaces that bridge so the executor subgraph
runs in-process within the same Python runtime. This eliminates subprocess
overhead, enables shared checkpointing, and allows the circuit breaker and
model escalation state to persist across the full pipeline lifecycle.

### Legacy Script Coexistence

- auto-pipeline.py and plan-orchestrator.py remain unchanged as v1
- The new runner can coexist: different PID file path or same path with a
  conflict check at startup
- Shared modules in langgraph_pipeline/shared/ and langgraph_pipeline/slack/
  are importable by both old and new code paths, but the legacy scripts do not
  import them (they keep their own inline implementations)

## Verification

- The runner starts, scans the backlog, and processes an item end-to-end
- SQLite checkpoint allows crash recovery: kill and restart mid-plan, execution
  resumes from last completed task
- Graceful shutdown on SIGINT stops after current node completes
- --dry-run scans and intakes but does not create or execute plans
- --single-item processes exactly one item and exits with code 0
- Budget cap triggers clean shutdown with exit code 2
- LangSmith traces appear when tracing is enabled
- Slack notifications fire at plan creation, task completion, and archival
- Legacy scripts still work independently and are unmodified

## Dependencies

- 01-langgraph-project-scaffold.md (package structure)
- 02-extract-shared-modules.md (shared utilities)
- 03-extract-slack-modules.md (Slack facade)
- 04-pipeline-graph-nodes.md (pipeline graph)
- 05-task-execution-subgraph.md (executor subgraph)
- 06-langsmith-observability.md (tracing)
