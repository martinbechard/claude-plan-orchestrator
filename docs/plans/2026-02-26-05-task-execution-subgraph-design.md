# Task Execution Subgraph -- Design Document

## Overview

This feature implements the task execution subgraph that replaces the subprocess
call to plan-orchestrator.py. The subgraph handles task selection, Claude CLI
execution, validation, parallel worktree execution, circuit breaking, and model
escalation. Once complete, the pipeline is a single LangGraph process.

## Architecture

The subgraph is compiled as an independent StateGraph and added as a node in the
pipeline graph, replacing the subprocess bridge in execute_plan.py.

```
pipeline_graph.add_node("execute_plan", task_execution_subgraph.compile())
```

### Subgraph Topology

```
find_next_task --[all_done]--> END
find_next_task --[parallel_group]--> fan_out --> fan_in --> find_next_task
find_next_task --[single_task]--> execute_task --> validate_task
validate_task --[pass]--> find_next_task
validate_task --[fail + retryable]--> escalate --> execute_task
validate_task --[fail + exhausted]--> find_next_task
execute_task --[circuit_break]--> END
execute_task --[interrupt]--> (paused, awaiting human via Slack)
```

### State Schema

TaskState in langgraph_pipeline/executor/state.py flows between parent pipeline
and child subgraph via shared keys (plan_path, cost accumulators).

Key fields:
- plan_path, plan_data: Plan file reference and parsed YAML
- current_task_id, task_attempt: Current execution context
- task_results: Annotated list with operator.add reducer for fan-in merging
- effective_model: Current model tier (haiku/sonnet/opus)
- consecutive_failures: Circuit breaker counter
- plan_cost_usd, plan_input_tokens, plan_output_tokens: Cost accumulators

### Key Modules

#### executor/state.py
TaskState TypedDict with all fields needed for subgraph execution.

#### executor/nodes/task_selector.py -- find_next_task
Loads plan YAML, finds next pending task by checking dependency satisfaction,
budget guard, circuit breaker threshold, and deadlock detection.

#### executor/nodes/task_runner.py -- execute_task
Loads agent definition, builds prompt, spawns Claude CLI via shared/claude_cli.py,
parses token usage, updates plan YAML status, git commits on success.
Supports interrupt() for Slack-based human-in-the-loop suspension.

#### executor/nodes/validator.py -- validate_task
Runs validation if enabled in plan config. Spawns Claude CLI with validator agent.
Parses PASS/WARN/FAIL verdict. On FAIL: increments task_attempt.

#### executor/nodes/parallel.py -- fan_out / fan_in
Detects parallel_group tasks, checks exclusive_resource conflicts, uses
LangGraph Send() API for dynamic branches. Each branch creates a git worktree,
executes the task, copies artifacts back, and cleans up.

#### executor/escalation.py
Tracks effective_model per task (haiku -> sonnet -> opus). On failure, checks
EscalationConfig to decide if model upgrade is warranted. Resets on success.

#### executor/circuit_breaker.py
Tracks consecutive_failures. When threshold exceeded (default 3), stops execution.
Resets on any task success.

### Conditional Edges

Defined in executor/edges.py:
- all_done: all tasks completed or plan failed -> return to parent
- parallel_check: route to fan_out or single execute_task
- retry_check: on failure, route to escalate/retry or mark failed
- circuit_check: on consecutive failures, route to circuit_break or continue

### Integration

The compiled subgraph replaces the subprocess bridge currently in
langgraph_pipeline/pipeline/nodes/execute_plan.py. State flows between
parent and child via shared keys. The pipeline graph wiring in graph.py
changes to use the compiled subgraph instead of spawning plan-orchestrator.py.

## Files to Create

- langgraph_pipeline/executor/state.py
- langgraph_pipeline/executor/edges.py
- langgraph_pipeline/executor/escalation.py
- langgraph_pipeline/executor/circuit_breaker.py
- langgraph_pipeline/executor/nodes/__init__.py
- langgraph_pipeline/executor/nodes/task_selector.py
- langgraph_pipeline/executor/nodes/task_runner.py
- langgraph_pipeline/executor/nodes/validator.py
- langgraph_pipeline/executor/nodes/parallel.py
- langgraph_pipeline/executor/graph.py (subgraph assembly)

## Files to Modify

- langgraph_pipeline/pipeline/nodes/execute_plan.py (replace subprocess bridge)
- langgraph_pipeline/pipeline/graph.py (wire compiled subgraph)

## Tests

- tests/langgraph/executor/test_state.py
- tests/langgraph/executor/test_circuit_breaker.py
- tests/langgraph/executor/test_escalation.py
- tests/langgraph/executor/nodes/test_task_selector.py
- tests/langgraph/executor/nodes/test_task_runner.py
- tests/langgraph/executor/nodes/test_validator.py
- tests/langgraph/executor/nodes/test_parallel.py
- tests/langgraph/executor/test_graph_integration.py

## Design Decisions

1. The subgraph is compiled separately and injected as a node -- this keeps
   the executor self-contained and independently testable.

2. Parallel execution uses LangGraph Send() API rather than Python threads,
   letting the framework handle concurrency and state merging.

3. Circuit breaker and budget guard are checked in task_selector (before
   execution starts) rather than after, to fail fast.

4. Model escalation state (effective_model) lives in TaskState so it survives
   graph interruptions and checkpoint recovery.

5. The backlog-creation throttle remains disk-persisted (not in graph state)
   since it must survive process restarts and apply across pipeline runs.
