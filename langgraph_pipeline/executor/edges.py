# langgraph_pipeline/executor/edges.py
# Conditional edge routing functions for the executor StateGraph.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Pure routing functions that read TaskState and return destination node names.

Each function is used as a LangGraph conditional edge.  Keeping routing logic
here (separate from node implementations) makes it easy to test edge decisions
without executing any node side effects.

Subgraph topology and the routing function used at each edge:

  find_next_task  --[parallel_check]--> fan_out | execute_task | END
  execute_task    --[circuit_check] --> validate_task | END
  validate_task   --[retry_check]  --> find_next_task | escalate | find_next_task(fail)
"""

from langgraph.graph import END

from langgraph_pipeline.executor.circuit_breaker import is_circuit_open
from langgraph_pipeline.executor.state import TaskState
from langgraph_pipeline.shared.langsmith import add_trace_metadata

# ─── Route label constants ────────────────────────────────────────────────────
# Returned by routing functions; matched against path_map in add_conditional_edges.

ROUTE_ALL_DONE = "all_done"
ROUTE_PARALLEL_GROUP = "parallel_group"
ROUTE_SINGLE_TASK = "single_task"
ROUTE_CIRCUIT_BREAK = "circuit_break"
ROUTE_CONTINUE = "continue"
ROUTE_PASS = "pass"
ROUTE_RETRY = "retry"
ROUTE_FAIL = "fail"

# ─── Policy constants ─────────────────────────────────────────────────────────

DEFAULT_MAX_ATTEMPTS = 3

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _find_current_task(state: TaskState) -> dict | None:
    """Return the task dict for current_task_id from cached plan_data, or None."""
    current_id = state.get("current_task_id")
    if not current_id:
        return None
    for section in (state.get("plan_data") or {}).get("sections", []):
        for task in section.get("tasks", []):
            if task.get("id") == current_id:
                return task
    return None


# ─── Edge routing functions ───────────────────────────────────────────────────


def all_done(state: TaskState) -> bool:
    """Predicate: True when current_task_id is None.

    This occurs when find_next_task determines that execution should stop:
    all tasks are completed, the circuit breaker is open, the budget is
    exceeded, or a dependency deadlock was detected.

    Args:
        state: Current TaskState after find_next_task has run.

    Returns:
        True if there is no task to execute; False otherwise.
    """
    return not state.get("current_task_id")


def parallel_check(state: TaskState) -> str:
    """Conditional edge routing from find_next_task.

    Decision tree:
    - current_task_id is None → ROUTE_ALL_DONE  (terminate subgraph)
    - current task has parallel_group set → ROUTE_PARALLEL_GROUP
    - otherwise → ROUTE_SINGLE_TASK

    Args:
        state: Current TaskState after find_next_task has run.

    Returns:
        One of ROUTE_ALL_DONE, ROUTE_PARALLEL_GROUP, or ROUTE_SINGLE_TASK.
    """
    if all_done(state):
        return ROUTE_ALL_DONE

    task = _find_current_task(state)
    if task and task.get("parallel_group"):
        return ROUTE_PARALLEL_GROUP

    return ROUTE_SINGLE_TASK


def circuit_check(state: TaskState) -> str:
    """Conditional edge routing from execute_task.

    Opens the circuit when quota is exhausted or when consecutive_failures has
    reached the threshold, halting further execution.  Otherwise, routing
    continues to validate_task.

    Args:
        state: Current TaskState after execute_task has run.

    Returns:
        ROUTE_CIRCUIT_BREAK if quota is exhausted or the circuit is open;
        ROUTE_CONTINUE otherwise.
    """
    if state.get("quota_exhausted"):
        return ROUTE_CIRCUIT_BREAK
    consecutive_failures = state.get("consecutive_failures") or 0
    if is_circuit_open(consecutive_failures):
        return ROUTE_CIRCUIT_BREAK
    return ROUTE_CONTINUE


def _tasks_completed_str(state: TaskState) -> str:
    """Compute a 'X/Y' string of completed tasks vs total plan tasks.

    Reads task_results for completed count and plan_data.sections for total.
    Returns 'X/Y' when total is known, or 'X' when plan_data is unavailable.
    """
    task_results = state.get("task_results") or []
    completed_count = sum(1 for r in task_results if r.get("status") == "completed")
    total_count = sum(
        len(section.get("tasks", []))
        for section in (state.get("plan_data") or {}).get("sections", [])
    )
    return f"{completed_count}/{total_count}" if total_count else str(completed_count)


def retry_check(state: TaskState) -> str:
    """Conditional edge routing from validate_task.

    Decision tree:
    - last_validation_verdict is not FAIL → ROUTE_PASS (back to find_next_task)
    - validation failed + attempts exhausted → ROUTE_FAIL (back to find_next_task)
    - validation failed + retries remain → ROUTE_RETRY (to escalate node)

    The max attempt limit is read from plan_data.meta.max_attempts_default,
    falling back to DEFAULT_MAX_ATTEMPTS when not configured.

    Emits pipeline_decision trace metadata with the routing rationale.

    Args:
        state: Current TaskState after validate_task has run.

    Returns:
        One of ROUTE_PASS, ROUTE_FAIL, or ROUTE_RETRY.
    """
    verdict = state.get("last_validation_verdict")
    task_attempt = state.get("task_attempt") or 0
    max_attempts = (
        (state.get("plan_data") or {})
        .get("meta", {})
        .get("max_attempts_default", DEFAULT_MAX_ATTEMPTS)
    )
    tasks_completed = _tasks_completed_str(state)

    if verdict != "FAIL":
        add_trace_metadata({
            "decision": "pass",
            "reason": "validator_passed",
            "cycle_number": task_attempt,
            "tasks_completed": tasks_completed,
        })
        return ROUTE_PASS

    if task_attempt >= max_attempts:
        add_trace_metadata({
            "decision": "fail",
            "reason": "max_attempts_reached",
            "cycle_number": task_attempt,
            "tasks_completed": tasks_completed,
        })
        return ROUTE_FAIL

    add_trace_metadata({
        "decision": "retry",
        "reason": "validator_failed_retry_available",
        "cycle_number": task_attempt,
        "tasks_completed": tasks_completed,
    })
    return ROUTE_RETRY
