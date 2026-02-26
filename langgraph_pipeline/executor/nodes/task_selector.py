# langgraph_pipeline/executor/nodes/task_selector.py
# find_next_task LangGraph node: selects the next eligible pending task.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""find_next_task node for the executor StateGraph.

Loads the plan YAML (caching it in state after the first load), then finds
the next pending task whose dependencies are all satisfied.  Before scanning,
applies the circuit breaker and budget guard as fast-fail checks.

Deadlock detection: if pending tasks exist but none have all dependencies
satisfied, execution cannot proceed and current_task_id is set to None.

Returns a partial state dict with plan_data and current_task_id.
"""

import yaml

from langgraph_pipeline.executor.circuit_breaker import is_circuit_open
from langgraph_pipeline.executor.state import TaskState
from langgraph_pipeline.shared.langsmith import add_trace_metadata

# ─── Constants ────────────────────────────────────────────────────────────────

PENDING_STATUS = "pending"
TERMINAL_STATUSES = frozenset({"completed", "failed", "skipped"})

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _load_plan_yaml(plan_path: str) -> dict:
    """Load and parse YAML plan from disk.

    Args:
        plan_path: Absolute or relative path to the YAML plan file.

    Returns:
        Parsed plan dict; empty dict if file is empty.

    Raises:
        IOError: If the file cannot be read.
        yaml.YAMLError: If the file is not valid YAML.
    """
    with open(plan_path, "r") as f:
        return yaml.safe_load(f) or {}


def _collect_tasks(plan_data: dict) -> list[dict]:
    """Extract all task dicts from all sections of the plan.

    Args:
        plan_data: Parsed YAML plan dict.

    Returns:
        Flat list of all task dicts in declaration order.
    """
    tasks: list[dict] = []
    for section in plan_data.get("sections", []):
        tasks.extend(section.get("tasks", []))
    return tasks


def _completed_task_ids(all_tasks: list[dict]) -> set[str]:
    """Return the set of task IDs whose status is terminal.

    Args:
        all_tasks: All task dicts from the plan.

    Returns:
        Set of task IDs with completed, failed, or skipped status.
    """
    return {t["id"] for t in all_tasks if t.get("status") in TERMINAL_STATUSES}


def _is_budget_exceeded(state: TaskState, plan_data: dict) -> bool:
    """Return True if the accumulated plan cost has reached the budget limit.

    If the plan has no budget_limit_usd in meta, the guard is disabled.

    Args:
        state: Current TaskState with plan_cost_usd.
        plan_data: Parsed plan dict that may contain meta.budget_limit_usd.

    Returns:
        True if cost >= limit; False if no limit is configured or not exceeded.
    """
    limit = plan_data.get("meta", {}).get("budget_limit_usd")
    if limit is None:
        return False
    return (state.get("plan_cost_usd") or 0.0) >= float(limit)


def _find_eligible_task(
    pending_tasks: list[dict], completed_ids: set[str]
) -> dict | None:
    """Return the first pending task whose dependencies are all completed.

    Args:
        pending_tasks: Subset of tasks with status "pending".
        completed_ids: Set of task IDs that have reached a terminal status.

    Returns:
        The first eligible task dict, or None if none are eligible.
    """
    for task in pending_tasks:
        deps: list[str] = task.get("dependencies") or []
        if all(dep in completed_ids for dep in deps):
            return task
    return None


# ─── Node ─────────────────────────────────────────────────────────────────────


def find_next_task(state: TaskState) -> dict:
    """LangGraph node: resolve the next eligible pending task from the plan.

    Sequence of checks:
    1. Load plan YAML (from cache in state, or from disk on first call).
    2. Circuit breaker: stop if consecutive failures >= threshold.
    3. Budget guard: stop if accumulated cost >= plan budget limit.
    4. Scan pending tasks for first one with all dependencies satisfied.
    5. Deadlock detection: stop if pending tasks exist but none are eligible.

    Returns:
        Partial state dict with:
          plan_data: Parsed plan (cached for subsequent nodes).
          current_task_id: Task ID to execute next, or None to stop.
    """
    plan_data: dict = state.get("plan_data") or _load_plan_yaml(state["plan_path"])

    consecutive_failures = state.get("consecutive_failures") or 0
    if is_circuit_open(consecutive_failures):
        print(
            f"[find_next_task] Circuit open after {consecutive_failures} consecutive failures"
        )
        return {"plan_data": plan_data, "current_task_id": None}

    if _is_budget_exceeded(state, plan_data):
        limit = plan_data.get("meta", {}).get("budget_limit_usd")
        cost = state.get("plan_cost_usd") or 0.0
        print(
            f"[find_next_task] Budget exceeded: cost=${cost:.4f} >= limit=${limit:.4f}"
        )
        return {"plan_data": plan_data, "current_task_id": None}

    all_tasks = _collect_tasks(plan_data)
    completed_ids = _completed_task_ids(all_tasks)
    pending_tasks = [t for t in all_tasks if t.get("status") == PENDING_STATUS]

    if not pending_tasks:
        print("[find_next_task] All tasks completed or no pending tasks remain")
        return {"plan_data": plan_data, "current_task_id": None}

    eligible = _find_eligible_task(pending_tasks, completed_ids)
    if eligible is None:
        print(
            f"[find_next_task] Deadlock: {len(pending_tasks)} pending task(s) with"
            " no eligible next step (unsatisfied dependencies)"
        )
        return {"plan_data": plan_data, "current_task_id": None}

    print(f"[find_next_task] Selected task: {eligible['id']} - {eligible.get('name', '')}")
    add_trace_metadata({
        "node_name": "find_next_task",
        "graph_level": "executor",
        "current_task_id": eligible["id"],
        "task_name": eligible.get("name", ""),
    })
    return {"plan_data": plan_data, "current_task_id": eligible["id"]}
