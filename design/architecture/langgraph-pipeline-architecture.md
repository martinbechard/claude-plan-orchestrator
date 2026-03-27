# LangGraph Pipeline Architecture

## Overview

This document describes the target architecture for replacing the current two-script
pipeline (auto-pipeline.py + plan-orchestrator.py) with a single-process LangGraph
StateGraph design. The migration is incremental: shared modules are extracted first,
then the pipeline graph wraps the existing orchestrator, and finally the task execution
subgraph replaces the subprocess boundary entirely.

## Motivation

1. **Better structure and extensibility** -- formal state machine replaces nested loops
2. **LangSmith observability** -- traces, runs, debugging dashboards out of the box
3. **Ecosystem tooling** -- checkpointing, interrupts, subgraphs, conditional edges
4. **Greenfield build** -- new langgraph_pipeline/ folder with its own tests

---

## Problems With the Current Architecture

### Two Monolithic Scripts

The system consists of two Python scripts totaling 9,246 lines:

- auto-pipeline.py (3,367 lines) -- backlog scanning, plan creation, verification, archival
- plan-orchestrator.py (5,879 lines) -- task execution, validation, Slack, budget, worktrees

These scripts communicate via subprocess spawning, YAML file writes, and exit codes.
There is no shared library; instead auto-pipeline.py uses an importlib.util hack
(lines 44-58) that executes the entire 5,879-line orchestrator as a side effect to
import 8 symbols (SlackNotifier, AgentIdentity, suspension helpers).

### Specific Problems

| Problem | Impact |
|---------|--------|
| importlib.util hack loads entire orchestrator to steal 8 symbols | Slow startup, fragile coupling, side effects on import |
| Duplicated logic (rate limit detection, output collection, stop semaphore) | Drift risk, double maintenance burden |
| No formal state machine -- nested loops with implicit transitions | Hard to reason about, test, extend, or visualize |
| Subprocess boundary between pipeline and orchestrator | No shared memory; communication limited to files and exit codes |
| SlackNotifier is ~1,500 lines inside plan-orchestrator.py | Impossible to test or reuse in isolation |
| Global mutable state (_active_child_process, _saved_terminal_settings) | Thread safety issues, testing friction |
| Verification state stored as regex-parsed markdown sections | Fragile parsing, no structured query capability |
| Crash recovery via PID file + stop semaphore + startup sweep | Ad-hoc; misses edge cases (orphaned worktrees, partial commits) |
| No formal event system (simple threading.Event) | Filesystem watcher can miss rapid edits |
| Slack calls are blocking with no backoff | Pipeline stalls if Slack API is degraded |
| Hardcoded paths scattered across both scripts | No path abstraction layer |

### Current Interaction Model

```
auto-pipeline.py                      plan-orchestrator.py
1. Write plan YAML
2. Check stop semaphore
3. Spawn orchestrator subprocess --> 4. Load plan
                                     5. Loop over tasks
                                     6. Execute Claude CLI per task
                                     7. Update plan YAML
                                     8. Git commit
                          <--------- 9. Exit with code
10. Check exit code
11. Decide: archive / retry / suspend
```

All state between the two scripts passes through the filesystem (YAML plan, .stop
semaphore, PID file, exit code). This makes the system brittle and hard to extend.

---

## Proposed LangGraph Design

### Two-Level Graph Architecture

The system decomposes into two StateGraphs:

1. **Pipeline Graph** (top-level) -- replaces auto-pipeline.py main_loop()
2. **Task Execution Subgraph** (nested) -- replaces plan-orchestrator.py run_orchestrator()

The subgraph is a node within the pipeline graph, compiled separately with its own
state schema. Communication between the two uses shared state keys.

### Pipeline Graph (Top-Level)

```
                    +------------------+
                    |   CLI pre-scan   |
                    | (scan_backlog)   |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  item found?     |
                    +---+----------+---+
                        |          |
                     no |          | yes
                        |          |
                  +-----v----+ +---v-----------+
                  | sleep/   | | intake_analyze |<-----------+
                  | wait     | +---+-----------+            |
                  +----------+     |                        |
                               +----v-----------+           |
                               | create_plan    |           |
                               +----+-----------+           |
                                    |                       |
                          +---------v----------+            |
                          | execute_plan       |            |
                          | (TASK SUBGRAPH)    |            |
                          +---------+----------+            |
                                    |                       |
                          +---------v------------------+    |
                          | route_after_execution      |    |
                          +----+-------------------+---+    |
                               |                   |        |
                        feature|                   |defect  |
                               |    +--------------v----+   |
                               |    | verify_fix        |   |
                               |    +-----+-------------+   |
                               |          |                  |
                               |    +-----v------+          |
                               |    | pass?      |          |
                               |    +--+-----+---+          |
                               |       |     |              |
                               |    yes|     |no            |
                               |       |  +--v-----+        |
                               |       |  |cycles  |        |
                               |       |  |< 3?    |        |
                               |       |  +--+--+--+        |
                               |       |     |  |           |
                               |       |   yes  no          |
                               |       |     |  |           |
                          +----v-------v-+ +-v--v--+        |
                          |   archive    | |exhaust|        |
                          +----+---------+ +---+---+        |
                               |               |            |
                               +-------+-------+            |
                                       |                    |
                                       +--------------------+
```

### Task Execution Subgraph

```
                    +------------------+
                    |      START       |
                    +--------+---------+
                             |
                    +--------v---------+
              +---->| find_next_task   |<-----------+
              |     +--------+---------+            |
              |              |                      |
              |     +--------v---------+            |
              |     |  all_done?       |            |
              |     +---+----------+---+            |
              |         |          |                |
              |      yes|          |no              |
              |         |          |                |
              |  +------v---+ +---v-----------+    |
              |  |   END    | | parallel?     |    |
              |  +----------+ +--+--------+---+    |
              |                  |        |        |
              |               no |        | yes    |
              |                  |   +----v-----+  |
              |                  |   | fan_out   |  |
              |                  |   | worktrees |  |
              |                  |   +----+-----+  |
              |                  |        |        |
              |                  |   +----v-----+  |
              |                  |   | fan_in    |  |
              |                  |   | merge     |  |
              |                  |   +----+-----+  |
              |                  |        |        |
              |            +-----v--------v---+    |
              |            | execute_task      |    |
              |            +-----+-------------+    |
              |                  |                  |
              |            +-----v-------------+    |
              |            | validate_task     |    |
              |            +-----+-------------+    |
              |                  |                  |
              |            +-----v-------------+    |
              |            | success?          |    |
              |            +--+------------+---+    |
              |               |            |        |
              |            yes|            |no      |
              |               |     +------v------+ |
              |               |     | retry?      | |
              |               |     | escalate?   | |
              |               |     | circuit brk?| |
              |               |     +------+------+ |
              |               |            |        |
              |         +-----v------+     |        |
              |         | commit &   |     |        |
              |         | update yaml|     |        |
              |         +-----+------+     |        |
              |               |            |        |
              |               +------+-----+        |
              |                      |              |
              +----------------------+--------------+
```

---

## State Schema

### Pipeline State

```python
class PipelineState(TypedDict):
    # Current work item
    item_path: str
    item_slug: str
    item_type: str                    # "defect" | "feature" | "analysis"
    item_name: str

    # Plan lifecycle
    plan_path: Optional[str]
    design_doc_path: Optional[str]
    verification_cycle: int           # 0-based, max 2
    verification_history: Annotated[list[dict], operator.add]

    # Control
    should_stop: bool                 # Replaces stop semaphore file
    rate_limited: bool
    rate_limit_reset: Optional[str]   # ISO timestamp

    # Session tracking
    session_cost_usd: float
    session_input_tokens: int
    session_output_tokens: int
```

### Task Execution State (Subgraph)

```python
class TaskState(TypedDict):
    # Plan context
    plan_path: str
    plan_data: dict                   # Loaded YAML

    # Current task
    current_task_id: Optional[str]
    task_attempt: int
    task_results: Annotated[list[dict], operator.add]  # Reducer for fan-in

    # Model escalation
    effective_model: str              # "haiku" | "sonnet" | "opus"
    consecutive_failures: int         # Circuit breaker counter

    # Budget
    plan_cost_usd: float
    plan_input_tokens: int
    plan_output_tokens: int
```

### What State Replaces

| Current mechanism | LangGraph replacement |
|---|---|
| In-memory sets (failed_items, completed_items) | Checkpointed state |
| PID file + stop semaphore | should_stop flag + graph interrupt |
| Regex-parsed verification history in .md files | verification_history list |
| Exit codes between scripts | Subgraph return state |
| threading.Event for new items | Graph re-invocation with fresh scan |

---

## Module Decomposition

The 9,246 lines in 2 files become ~15 focused modules in a new langgraph_pipeline/
folder. Each module is independently testable and importable.

```
langgraph_pipeline/
  __init__.py

  pipeline/
    __init__.py
    graph.py              # Top-level StateGraph definition (~100 lines)
    state.py              # PipelineState TypedDict (~80 lines)
    nodes/
      __init__.py
      scan.py             # Backlog scanning + prioritization
      intake.py           # 5-Whys analysis, idea classification
      plan_creation.py    # Claude session for design + YAML plan
      verification.py     # Symptom verification for defects
      archival.py         # Move to completed-backlog, clean up
    edges.py              # Conditional routing functions

  executor/
    __init__.py
    graph.py              # Task execution subgraph definition
    state.py              # TaskState TypedDict
    nodes/
      __init__.py
      task_selector.py    # Find next task, check deps/budget/circuit breaker
      task_runner.py      # Spawn Claude CLI, parse results
      validator.py        # Per-task validation pipeline
      parallel.py         # Worktree creation, fan-out via Send(), merge
    escalation.py         # Model tier logic (haiku -> sonnet -> opus)
    circuit_breaker.py    # Failure tracking + backoff

  slack/
    __init__.py
    notifier.py           # Message posting, channel discovery (~400 lines)
    poller.py             # Inbound message polling + filtering (~400 lines)
    identity.py           # AgentIdentity, signing, self-skip (~200 lines)
    suspension.py         # Question posting, reply polling (~200 lines)

  shared/
    __init__.py
    config.py             # Orchestrator config loading from .claude/orchestrator-config.yaml
    claude_cli.py         # Claude subprocess management, output streaming
    rate_limit.py         # Rate limit detection + wait calculation (ONE copy)
    git.py                # Git operations (commit, worktree, stash)
    budget.py             # BudgetGuard, usage tracking
    logging.py            # Structured logging, per-item log files
    paths.py              # Path constants and resolution
```

### Key Wins

- **SlackNotifier** splits from ~1,500 lines into 4 modules (200-400 lines each)
- **Rate limit detection** exists once in shared/rate_limit.py, not duplicated
- **Output collection** exists once in shared/claude_cli.py
- **importlib.util hack eliminated** -- everything is a proper import
- **Each node function** is independently testable with mocked state
- **Path constants** centralized in shared/paths.py instead of scattered across files

---

## LangSmith Integration

### Observability

LangGraph graphs compiled with a checkpointer automatically emit traces to LangSmith
when configured. Each node execution becomes a trace span with:

- Input state snapshot
- Output state delta
- Duration and token usage
- Error details if the node fails

### Configuration

```python
import os

os.environ["LANGSMITH_API_KEY"] = "..."
os.environ["LANGSMITH_PROJECT"] = "claude-plan-orchestrator"
os.environ["LANGSMITH_TRACING"] = "true"
```

### Dashboard Capabilities

- **Run history** -- every pipeline invocation with state at each checkpoint
- **Trace waterfall** -- node-by-node execution timeline
- **Error drill-down** -- stack traces, state snapshots at failure point
- **Cost tracking** -- token usage aggregated by node, task, and plan
- **Comparison** -- diff two runs to understand regressions

### What This Replaces

Currently, debugging requires reading log files in logs/YYYY-MM-DD/, parsing YAML plan
status fields, and correlating timestamps across auto-pipeline and plan-orchestrator
output. LangSmith replaces all of this with a single dashboard showing the graph
execution in real time.

---

## How Current Problems Map to LangGraph Solutions

### Crash Recovery -> Checkpointing

**Current**: PID file, stop semaphore, startup sweep for orphaned artifacts.

**LangGraph**: SQLite checkpointer saves state at every super-step. On restart, the
graph resumes from the last checkpoint with full state. No PID file needed. Orphaned
worktrees are cleaned up by the archival node if the state shows an incomplete plan.

```python
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver.from_conn_string(".claude/pipeline-state.db")
compiled = pipeline_graph.compile(checkpointer=checkpointer)
# Resume from last checkpoint automatically
result = compiled.invoke(None, {"configurable": {"thread_id": "pipeline-main"}})
```

### Slack Suspension -> Interrupts

**Current**: Plan-orchestrator writes a question to Slack, then polls for responses
in a blocking loop. If the process crashes, the question context is lost.

**LangGraph**: The interrupt() function pauses the graph and persists the pending
question in the checkpoint. A separate poller (or Slack event handler) calls
Command(resume=answer) to continue. The graph picks up exactly where it stopped.

```python
from langgraph.types import interrupt, Command

def execute_task(state: TaskState) -> dict:
    if needs_clarification(state):
        answer = interrupt({
            "question": "How should we handle X?",
            "channel": "orchestrator-questions"
        })
        return {"clarification": answer}
    # ... continue execution
```

### Subprocess Boundary -> Subgraph

**Current**: auto-pipeline spawns plan-orchestrator as a child process. Communication
is limited to YAML files and exit codes.

**LangGraph**: The task execution subgraph runs in the same process as the pipeline
graph. State flows directly between parent and child via shared TypedDict keys. No
serialization, no exit code parsing, no file-based IPC.

### Parallel Execution -> Fan-Out/Fan-In

**Current**: plan-orchestrator.py uses concurrent.futures.ThreadPoolExecutor with
manual worktree management and result merging.

**LangGraph**: The Send() API creates dynamic parallel branches at runtime. Each
branch runs in its own worktree. Fan-in uses a reducer (operator.add) to merge task
results. The super-step is transactional: if any branch fails, none of that step's
state updates are applied.

```python
from langgraph.constants import Send

def route_parallel(state: TaskState) -> list[Send]:
    parallel_tasks = find_parallel_tasks(state["plan_data"])
    return [
        Send("execute_in_worktree", {"task_id": t["id"], "plan_path": state["plan_path"]})
        for t in parallel_tasks
    ]
```

### Implicit State Machine -> Explicit Graph

**Current**: Nested while loops with if/elif chains determine what happens next.
The state machine is implicit in the control flow.

**LangGraph**: The StateGraph definition is the state machine. Nodes are functions,
edges are transitions, conditional edges encode routing logic. The graph is
visualizable, testable, and self-documenting.

### Global Mutable State -> Immutable State Updates

**Current**: Global variables like _active_child_process and _saved_terminal_settings
create thread safety issues.

**LangGraph**: Each node receives an immutable state snapshot and returns a delta.
The framework applies updates atomically. No global mutable state needed.

---

## What Stays the Same

These elements are preserved as-is:

- **YAML plan format** -- plans are still .claude/plans/*.yaml with sections, tasks, depends_on
- **Backlog .md format** -- defect/feature/analysis items remain markdown files in docs/
- **Claude Code CLI** -- tasks are still executed by spawning fresh claude sessions
- **Git worktrees** -- parallel execution still uses .worktrees/ for isolation
- **Slack channels** -- orchestrator-{notifications,defects,features,questions}
- **Agent definitions** -- .claude/agents/*.md files with YAML frontmatter
- **Orchestrator config** -- .claude/orchestrator-config.yaml for runtime settings
- **Log structure** -- logs/YYYY-MM-DD/ for per-run output files

The LangGraph migration changes HOW the pipeline orchestrates work, not WHAT work
it orchestrates. The external interfaces (backlog items in, completed items out,
Slack notifications, git commits) remain identical.

---

## Migration Strategy

The migration proceeds in 4 phases, each independently valuable:

### Phase 1: Extract Shared Modules (No LangGraph)

Extract duplicated logic into langgraph_pipeline/shared/ and langgraph_pipeline/slack/.
Both old scripts import from these modules. The importlib.util hack is eliminated.
This phase has zero risk -- it is pure refactoring with the same runtime behavior.

### Phase 2: Pipeline Graph (Wraps Existing Orchestrator)

Replace auto-pipeline.py main_loop() with a StateGraph. The execute_plan node still
spawns plan-orchestrator.py as a subprocess. SQLite checkpointing replaces the PID
file and startup sweep. This phase proves the LangGraph framework works.

### Phase 3: Task Execution Subgraph (Replaces Subprocess)

Implement the task execution subgraph that replaces the plan-orchestrator.py subprocess
call. Port CircuitBreaker, EscalationConfig, ValidationConfig, and parallel worktree
execution into graph nodes. The subprocess boundary is eliminated.

### Phase 4: LangSmith Observability

Add LangSmith tracing to all nodes. Configure the project, set up trace filtering,
and document dashboard usage. This phase adds observability without changing behavior.

---

## Dependencies Between Phases

```
Phase 1 (shared modules) ----+
                              |
Phase 1 (slack modules) ------+--> Phase 2 (pipeline graph) --> Phase 3 (subgraph) --> Phase 4 (LangSmith)
                              |
Phase 0 (scaffold) ----------+
```

Phase 0 (project scaffold) can start immediately. Phases 1a and 1b (shared + Slack
extraction) can proceed in parallel. Phase 2 depends on both. Phase 3 depends on
Phase 2. Phase 4 can be done after Phase 2 or Phase 3.
