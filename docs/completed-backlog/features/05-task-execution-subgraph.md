# Task Execution Subgraph

## Status: Open

## Priority: Medium

## Summary

Implement the task execution subgraph that replaces the subprocess call to
plan-orchestrator.py. This subgraph handles task selection, Claude CLI execution,
validation, parallel worktree execution, circuit breaking, and model escalation.
Once complete, plan-orchestrator.py is no longer spawned as a subprocess -- the
pipeline is a single LangGraph process.

## Scope

### State Schema

Define TaskState in langgraph_pipeline/executor/state.py:

```
class TaskState(TypedDict):
    plan_path: str
    plan_data: dict
    current_task_id: Optional[str]
    task_attempt: int
    task_results: Annotated[list[dict], operator.add]
    effective_model: str
    consecutive_failures: int
    plan_cost_usd: float
    plan_input_tokens: int
    plan_output_tokens: int
```

### Node Implementations

#### executor/nodes/task_selector.py -- find_next_task
- Load plan YAML and find the next pending task
- Check dependency satisfaction (depends_on resolved)
- Check budget guard (plan_cost_usd < limit)
- Check circuit breaker (consecutive_failures < threshold)
- Detect deadlock (all remaining tasks blocked by failed/suspended tasks)
- Return current_task_id or signal all_done

#### executor/nodes/task_runner.py -- execute_task
- Load agent definition for the task (infer_agent_for_task or explicit agent field)
- Build prompt with agent instructions + task description
- Spawn Claude CLI via shared/claude_cli.py
- Parse output for token usage, errors, rate limits
- Update plan YAML task status
- Git commit after successful execution
- Handle Slack suspension via interrupt():
  - If the task needs human input, call interrupt() with the question
  - The graph pauses and saves state to checkpoint
  - A Slack poller (or event handler) calls Command(resume=answer) to continue

#### executor/nodes/validator.py -- validate_task
- Run validation if enabled in plan config
- Spawn Claude CLI with validator agent
- Parse validation verdict (PASS/WARN/FAIL)
- On FAIL: increment task_attempt, check if retry is warranted

#### executor/nodes/parallel.py -- fan_out / fan_in
- Detect parallel task groups from plan YAML (parallel_group field)
- Check for exclusive_resource conflicts
- Use LangGraph Send() API to create dynamic parallel branches
- Each branch:
  1. Creates a git worktree via shared/git.py
  2. Executes the task in the worktree
  3. Copies artifacts back to main tree
  4. Cleans up worktree
- Fan-in merges task_results using the operator.add reducer

#### executor/escalation.py -- model escalation
- Track effective_model per task (haiku -> sonnet -> opus)
- On task failure, check EscalationConfig to decide if model upgrade is warranted
- Reset to default model on task success

#### executor/circuit_breaker.py -- circuit breaker
- Track consecutive_failures across tasks
- When threshold exceeded (default 3), stop execution and report
- Reset counter on any task success

### Conditional Edges

- all_done: all tasks completed or plan failed -> return to parent graph
- parallel_check: route to fan_out or single execute_task
- retry_check: on failure, route to escalate/retry or mark task failed
- circuit_check: on consecutive failures, route to circuit_break or continue

### Integration With Pipeline Graph

The task execution subgraph is compiled separately and added as a node in the pipeline
graph (replacing the subprocess bridge from feature 04):

```
pipeline_graph.add_node("execute_plan", task_execution_subgraph.compile())
```

State flows between parent and child via shared keys (plan_path, cost accumulators).

### Verification

- Unit tests for each node with mocked Claude CLI
- Integration test: run a multi-task plan through the subgraph
- Parallel test: verify worktree creation, execution, and cleanup for parallel tasks
- Circuit breaker test: verify execution stops after N consecutive failures
- Model escalation test: verify haiku -> sonnet -> opus progression
- Interrupt test: verify graph pauses on interrupt() and resumes with Command(resume=...)
- Plan-orchestrator.py is no longer spawned as a subprocess

## Safety Requirements

- Circuit breaker and budget guard are already listed in the scope above.
- The backlog creation throttle (disk-persisted) applies if the executor creates defects
  during verification failure paths. The throttle file lives on disk at
  .claude/plans/.backlog-creation-throttle.json, separate from graph state.

## Dependencies

- 01-langgraph-project-scaffold.md (package structure)
- 02-extract-shared-modules.md (shared/claude_cli.py, shared/git.py, shared/budget.py)
- 03-extract-slack-modules.md (slack/suspension.py for interrupt-based questions)
- 04-pipeline-graph-nodes.md (pipeline graph that hosts this subgraph)
