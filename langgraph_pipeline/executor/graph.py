# langgraph_pipeline/executor/graph.py
# Executor StateGraph assembly: wires all nodes and conditional edges.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Executor subgraph for the task execution pipeline.

Assembles the full executor StateGraph that replaces the subprocess bridge in
execute_plan.py.  All task selection, Claude CLI execution, validation,
parallel worktree execution, circuit breaking, and model escalation happen
inside this subgraph.

Graph topology:
  find_next_task --[all_done]----------> END
  find_next_task --[needs_validation]--> validate_task
  find_next_task --[single_task]-------> execute_task
  find_next_task --[parallel_group]----> execute_parallel_task (fan-out) --> fan_in --> find_next_task
  find_next_task --[empty_parallel]----> fan_in --> find_next_task
  execute_task   --[circuit_break]-----> END
  execute_task   --[continue]----------> validate_task
  validate_task  --[pass/fail]---------> find_next_task
  validate_task  --[retry]-------------> escalate --> execute_task

Note on the LangGraph Send API:
  In LangGraph 1.0.x, parallel dispatch via Send() must originate from a
  conditional edge function (not a node return value).  The routing function
  _route_after_find_next_task() merges the parallel_check route decision with
  fan_out's Send dispatch into a single conditional edge.
"""

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from langgraph_pipeline.executor.edges import (
    ROUTE_ALL_DONE,
    ROUTE_CIRCUIT_BREAK,
    ROUTE_CONTINUE,
    ROUTE_FAIL,
    ROUTE_NEEDS_VALIDATION,
    ROUTE_PARALLEL_GROUP,
    ROUTE_PASS,
    ROUTE_RETRY,
    ROUTE_SINGLE_TASK,
    circuit_check,
    parallel_check,
    retry_check,
)
from langgraph_pipeline.executor.escalation import escalate_model
from langgraph_pipeline.executor.nodes.parallel import (
    execute_parallel_task,
    fan_in,
    fan_out,
)
from langgraph_pipeline.executor.nodes.task_runner import execute_task
from langgraph_pipeline.executor.nodes.task_selector import find_next_task
from langgraph_pipeline.executor.nodes.validator import validate_task
from langgraph_pipeline.executor.state import TaskState
from langgraph_pipeline.shared.langsmith import add_trace_metadata, configure_tracing

# ─── Node name constants ──────────────────────────────────────────────────────
# These must match the string names registered with add_node() below.

NODE_FIND_NEXT_TASK = "find_next_task"
NODE_EXECUTE_TASK = "execute_task"
NODE_VALIDATE_TASK = "validate_task"
NODE_EXECUTE_PARALLEL_TASK = "execute_parallel_task"
NODE_FAN_IN = "fan_in"
NODE_ESCALATE = "escalate"


# ─── Escalate node ────────────────────────────────────────────────────────────


def _escalate_node(state: TaskState) -> dict:
    """Advance effective_model to the next tier and reset the task attempt counter.

    Called by the retry_check conditional edge when validate_task returns FAIL
    and retries remain.  The next execute_task invocation uses the upgraded model.

    Emits pipeline_decision trace metadata recording the escalation decision.

    Args:
        state: Current TaskState after validate_task has run.

    Returns:
        Partial state dict with upgraded effective_model and reset task_attempt.
    """
    current_model = state.get("effective_model") or "sonnet"
    new_model = escalate_model(current_model)
    print(f"[escalate] Model upgrade: {current_model!r} -> {new_model!r}")
    add_trace_metadata({
        "decision": "escalate",
        "reason": "validator_failed_retry_available",
        "cycle_number": state.get("task_attempt") or 0,
        "from_model": current_model,
        "to_model": new_model,
    })
    return {"effective_model": new_model, "task_attempt": 1}


# ─── Routing helpers ──────────────────────────────────────────────────────────


def _route_after_find_next_task(state: TaskState):
    """Conditional edge function routing out of find_next_task.

    Merges the parallel_check route decision with fan_out's Send dispatch
    into a single conditional edge, satisfying LangGraph 1.0.x's requirement
    that Send objects originate from conditional edge functions.

    Decision tree:
    1. parallel_check returns ROUTE_ALL_DONE        -> END
    2. parallel_check returns ROUTE_NEEDS_VALIDATION -> NODE_VALIDATE_TASK
       (task was selected by the validation-pending scan; bypass execute_task)
    3. parallel_check returns ROUTE_SINGLE_TASK     -> NODE_EXECUTE_TASK
    4. parallel_check returns ROUTE_PARALLEL_GROUP:
       a. fan_out returns non-empty list     -> list[Send] to execute_parallel_task
       b. fan_out returns empty list         -> NODE_FAN_IN (no-op fan-in)

    Args:
        state: TaskState after find_next_task has run.

    Returns:
        END, a node name string, or a list[Send] for parallel dispatch.
    """
    route = parallel_check(state)

    if route == ROUTE_ALL_DONE:
        return END

    if route == ROUTE_NEEDS_VALIDATION:
        return NODE_VALIDATE_TASK

    if route == ROUTE_SINGLE_TASK:
        return NODE_EXECUTE_TASK

    # ROUTE_PARALLEL_GROUP: call fan_out to get Send objects
    sends = fan_out(state)
    if sends:
        return sends

    # No runnable parallel tasks — route directly to fan_in
    print("[executor_graph] Parallel group has no runnable tasks; routing to fan_in")
    return NODE_FAN_IN


# ─── Graph assembly ───────────────────────────────────────────────────────────


def build_executor_graph() -> StateGraph:
    """Build and return the uncompiled executor StateGraph.

    The returned graph is uncompiled.  Callers may compile it with or without
    a checkpointer depending on whether crash recovery is needed.

    Returns:
        Uncompiled StateGraph[TaskState] with all nodes and edges wired.
    """
    configure_tracing()
    graph = StateGraph(TaskState)

    graph.add_node(NODE_FIND_NEXT_TASK, find_next_task)
    graph.add_node(NODE_EXECUTE_TASK, execute_task)
    graph.add_node(NODE_VALIDATE_TASK, validate_task)
    graph.add_node(NODE_EXECUTE_PARALLEL_TASK, execute_parallel_task)
    graph.add_node(NODE_FAN_IN, fan_in)
    graph.add_node(NODE_ESCALATE, _escalate_node)

    graph.set_entry_point(NODE_FIND_NEXT_TASK)

    # find_next_task -> route -> execute_task | validate_task | execute_parallel_task(s) | fan_in | END
    graph.add_conditional_edges(
        NODE_FIND_NEXT_TASK,
        _route_after_find_next_task,
        {
            NODE_EXECUTE_TASK: NODE_EXECUTE_TASK,
            NODE_VALIDATE_TASK: NODE_VALIDATE_TASK,
            NODE_FAN_IN: NODE_FAN_IN,
            END: END,
            # list[Send] to execute_parallel_task is handled implicitly by LangGraph
        },
    )

    # execute_task -> circuit_check -> validate_task | END
    graph.add_conditional_edges(
        NODE_EXECUTE_TASK,
        circuit_check,
        {
            ROUTE_CIRCUIT_BREAK: END,
            ROUTE_CONTINUE: NODE_VALIDATE_TASK,
        },
    )

    # validate_task -> retry_check -> find_next_task | escalate
    graph.add_conditional_edges(
        NODE_VALIDATE_TASK,
        retry_check,
        {
            ROUTE_PASS: NODE_FIND_NEXT_TASK,
            ROUTE_FAIL: NODE_FIND_NEXT_TASK,
            ROUTE_RETRY: NODE_ESCALATE,
        },
    )

    # escalate -> execute_task (retry with upgraded model)
    graph.add_edge(NODE_ESCALATE, NODE_EXECUTE_TASK)

    # execute_parallel_task -> fan_in (parallel branches converge here)
    graph.add_edge(NODE_EXECUTE_PARALLEL_TASK, NODE_FAN_IN)

    # fan_in -> find_next_task (continue after parallel batch completes)
    graph.add_edge(NODE_FAN_IN, NODE_FIND_NEXT_TASK)

    return graph
