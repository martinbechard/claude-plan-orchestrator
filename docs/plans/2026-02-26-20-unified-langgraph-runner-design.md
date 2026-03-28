# Unified LangGraph Pipeline Runner - Design

## Overview

A single CLI entry point that runs the complete LangGraph pipeline graph,
replacing both auto-pipeline.py (backlog scanning, intake, verification loop)
and plan-orchestrator.py (task execution) with one invocation. The executor
subgraph already runs in-process within execute_plan node; this feature wires
the outer pipeline graph to a proper CLI with process management.

## Architecture

The runner is a thin CLI wrapper around the existing pipeline StateGraph.
No new graph nodes are needed -- the graph topology from pipeline/graph.py
already encodes the full workflow (scan, intake, plan creation, execute,
verify, archive) and the executor subgraph already replaces what
plan-orchestrator.py did in-process.

```
scripts/run-pipeline.py (CLI entry point)
  |
  +-- parse CLI args (argparse)
  +-- load config (shared/config.py)
  +-- configure tracing (shared/langsmith.py, conditional on --no-tracing)
  +-- initialize Slack (slack/__init__.py, conditional on --no-slack)
  +-- write PID file (shared/paths.py PID_FILE_PATH)
  +-- register SIGINT/SIGTERM handlers
  +-- open pipeline_graph() context manager (SqliteSaver checkpointing)
  |     |
  |     +-- continuous scan loop (or single-item mode)
  |     |     graph.invoke(initial_state, config=thread_config)
  |     |     check budget after each item
  |     |
  |     +-- on budget exhaustion: exit code 2
  |     +-- on clean shutdown: exit code 0
  |
  +-- remove PID file on exit
```

## Key Files

### New Files

- scripts/run-pipeline.py -- CLI entry point with argparse, signal handling,
  scan loop, and budget enforcement
- tests/langgraph/test_run_pipeline.py -- unit tests for CLI argument parsing,
  signal handling, PID file management, budget exit codes, and single-item mode

### Modified Files

- langgraph_pipeline/shared/paths.py -- add LANGGRAPH_PID_FILE_PATH constant
  (separate from legacy PID_FILE_PATH to allow coexistence)
- langgraph_pipeline/pipeline/state.py -- add budget_cap_usd field to
  PipelineState for budget enforcement within graph nodes

### Unchanged Files

- langgraph_pipeline/pipeline/graph.py -- already has build_graph() and
  pipeline_graph() context manager with SqliteSaver
- langgraph_pipeline/pipeline/nodes/execute_plan.py -- already runs executor
  subgraph in-process
- scripts/auto-pipeline.py -- legacy v1 runtime, untouched

## Design Decisions

### Separate PID File Path

The new runner uses a distinct PID file path (e.g. .claude/plans/.lg-pipeline.pid)
so it can coexist with the legacy auto-pipeline.py without conflict. At startup,
the runner checks for a stale PID file and warns if another instance is running.

### Scan Loop vs Single-Item Mode

- Default: continuous scan loop. After processing one item, re-scan the backlog.
  Sleep briefly between scans when no items are found.
- --single-item PATH: process exactly one item and exit with code 0.
  Skips the scan node entirely, sets item_path directly in initial state.

### Budget Enforcement

Budget cap is enforced at the runner level after each graph.invoke() returns.
The runner checks session_cost_usd from the returned state against the --budget-cap
CLI value. Exit code 2 when budget is exhausted.

### Graceful Shutdown

SIGINT/SIGTERM set a threading.Event flag checked between graph invocations.
The current graph invocation completes (current node finishes), then the
runner exits cleanly with code 0. The PID file is removed in a finally block.

### Tracing and Slack as Runner Concerns

The runner initializes tracing and Slack before entering the graph loop.
--no-tracing skips configure_tracing(). --no-slack disables the Slack facade.
Graph nodes read Slack state from the facade singleton; when disabled, calls
are no-ops.

### Exit Codes

- 0: clean shutdown (SIGINT/SIGTERM or no more items in single-item mode)
- 1: unhandled error
- 2: budget exhausted
