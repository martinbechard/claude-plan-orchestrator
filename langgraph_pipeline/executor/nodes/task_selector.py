# langgraph_pipeline/executor/nodes/task_selector.py
# find_next_task LangGraph node: selects the next eligible pending task.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md
# Design: docs/plans/2026-03-30-80-executor-silent-deadlock-on-blocked-tasks-design.md

"""find_next_task node for the executor StateGraph.

Loads the plan YAML (caching it in state after the first load), then finds
the next pending task whose dependencies are all satisfied.  Before scanning,
applies the circuit breaker and budget guard as fast-fail checks.

Deadlock detection: if pending tasks exist but none have all dependencies
satisfied, execution cannot proceed and current_task_id is set to None.

Returns a partial state dict with plan_data and current_task_id.
"""

import logging
import os
import re

import yaml

from langgraph_pipeline.executor.circuit_breaker import is_circuit_open
from langgraph_pipeline.executor.escalation import MODEL_TIER_PROGRESSION
from langgraph_pipeline.executor.state import ModelTier, TaskState, effective_status
from langgraph_pipeline.shared.config import load_orchestrator_config
from langgraph_pipeline.shared.langsmith import add_trace_metadata

# ─── Module logger ────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

PENDING_STATUS = "pending"
# "completed" is intentionally excluded: it is an intermediate state (awaiting
# validation).  Legacy completed tasks are promoted to "verified" at read time
# via effective_status(), so they still satisfy dependencies.
TERMINAL_STATUSES = frozenset({"verified", "failed", "skipped"})

# Pattern to extract model from agent frontmatter (e.g. "model: sonnet")
_AGENT_MODEL_PATTERN = re.compile(r"^model:\s*(\S+)", re.MULTILINE)

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


def _completed_task_ids(all_tasks: list[dict], validation_meta: dict) -> set[str]:
    """Return the set of task IDs whose effective status is terminal.

    Uses effective_status() so that legacy "completed" tasks (where validation
    was not configured or already ran) are promoted to "verified" and still
    satisfy dependencies, while genuinely awaiting-validation tasks remain
    blocked.

    Args:
        all_tasks: All task dicts from the plan.
        validation_meta: The plan's meta.validation config dict.

    Returns:
        Set of task IDs with verified, failed, or skipped effective status.
    """
    return {
        t["id"] for t in all_tasks
        if effective_status(t, validation_meta) in TERMINAL_STATUSES
    }


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


def _find_validation_pending_task(
    all_tasks: list[dict], validation_meta: dict
) -> dict | None:
    """Return the first completed task that requires validation but has not been validated yet.

    Scans all_tasks for tasks where:
    - status is "completed" (execution succeeded, awaiting validation)
    - agent is in the validation run_after list
    - validation_attempts is 0 (validation has not run yet)

    This scan runs before the pending-task scan in find_next_task to ensure that
    parallel-group tasks receive validation before any new work is selected, preventing
    a permanent deadlock where dependents wait on an unvalidated prerequisite.

    Args:
        all_tasks: All task dicts from the plan.
        validation_meta: The plan's meta.validation config dict.

    Returns:
        The first task needing validation, or None if no such task exists.
    """
    if not validation_meta.get("enabled", False):
        return None
    run_after = validation_meta.get("run_after", [])
    if not run_after:
        return None
    for task in all_tasks:
        if task.get("status") != "completed":
            continue
        if task.get("agent", "coder") not in run_after:
            continue
        if (task.get("validation_attempts") or 0) > 0:
            continue
        return task
    return None


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


def _resolve_agent_model(task: dict) -> ModelTier:
    """Read the model tier from the agent definition file for this task.

    Looks up the agent name from the task dict, finds the agent markdown
    file in the configured agents directory, and extracts the model
    from YAML frontmatter. Falls back to "sonnet" if the agent file
    is missing or has no model field.

    Args:
        task: Task dict from the plan YAML.

    Returns:
        The model tier declared in the agent definition.
    """
    agent_name = task.get("agent", "coder")
    config = load_orchestrator_config()
    agents_dir = config.get("agents_dir", ".claude/agents")
    agent_path = os.path.join(agents_dir, f"{agent_name}.md")

    try:
        with open(agent_path, "r") as f:
            content = f.read(500)  # Frontmatter is near the top
        match = _AGENT_MODEL_PATTERN.search(content)
        if match:
            model = match.group(1).lower()
            if model in MODEL_TIER_PROGRESSION:
                return model  # type: ignore[return-value]
    except (IOError, OSError) as exc:
        logger.warning("Could not read agent file %s: %s — defaulting to sonnet", agent_path, exc)

    return "sonnet"  # Safe default — never silently use haiku for real work


def _effective_model_for_task(task: dict, current_model: ModelTier) -> ModelTier:
    """Return the effective model: the higher of the agent's model and the current escalation.

    The agent's declared model acts as a floor — escalation can go higher
    but never below what the agent specifies.

    Args:
        task: Task dict from the plan YAML.
        current_model: Current model from escalation state.

    Returns:
        The model tier to use for this task.
    """
    agent_model = _resolve_agent_model(task)
    agent_index = MODEL_TIER_PROGRESSION.index(agent_model)
    current_index = MODEL_TIER_PROGRESSION.index(current_model)
    return MODEL_TIER_PROGRESSION[max(agent_index, current_index)]


def _build_deadlock_details(
    pending_tasks: list[dict], completed_ids: set[str]
) -> list[dict]:
    """Build a structured list describing each blocked pending task.

    For each pending task, computes the subset of its declared dependencies
    that are not in the completed set — these are the unsatisfied deps causing
    the deadlock.

    Args:
        pending_tasks: Tasks whose status is "pending".
        completed_ids: Set of task IDs that have reached a terminal status.

    Returns:
        List of dicts with task_id, task_name, and unsatisfied_deps for each task.
    """
    details = []
    for task in pending_tasks:
        deps: list[str] = task.get("dependencies") or []
        unsatisfied = [dep for dep in deps if dep not in completed_ids]
        details.append({
            "task_id": task["id"],
            "task_name": task.get("name", ""),
            "unsatisfied_deps": unsatisfied,
        })
    return details


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
    all_tasks = _collect_tasks(plan_data)
    validation_meta = plan_data.get("meta", {}).get("validation", {})
    completed_ids = _completed_task_ids(all_tasks, validation_meta)
    completed_count = len(completed_ids)
    total_count = len(all_tasks)
    tasks_completed_str = f"{completed_count}/{total_count}"
    cycle_number = state.get("task_attempt") or 1

    if state.get("quota_exhausted"):
        print("[find_next_task] Quota exhausted — stopping task selection")
        add_trace_metadata({
            "node_name": "find_next_task",
            "decision": "stop",
            "reason": "quota_exhausted",
            "cycle_number": cycle_number,
            "tasks_completed": tasks_completed_str,
        })
        return {"plan_data": plan_data, "current_task_id": None, "deadlock_detected": False}

    consecutive_failures = state.get("consecutive_failures") or 0
    if is_circuit_open(consecutive_failures):
        print(
            f"[find_next_task] Circuit open after {consecutive_failures} consecutive failures"
        )
        add_trace_metadata({
            "node_name": "find_next_task",
            "decision": "stop",
            "reason": "circuit_open",
            "cycle_number": cycle_number,
            "tasks_completed": tasks_completed_str,
        })
        return {"plan_data": plan_data, "current_task_id": None, "deadlock_detected": False}

    if _is_budget_exceeded(state, plan_data):
        limit = plan_data.get("meta", {}).get("budget_limit_usd")
        cost = state.get("plan_cost_usd") or 0.0
        print(
            f"[find_next_task] Budget exceeded: cost=${cost:.4f} >= limit=${limit:.4f}"
        )
        add_trace_metadata({
            "node_name": "find_next_task",
            "decision": "stop",
            "reason": "budget_exceeded",
            "cycle_number": cycle_number,
            "tasks_completed": tasks_completed_str,
        })
        return {"plan_data": plan_data, "current_task_id": None, "deadlock_detected": False}

    # Validation-pending scan: select tasks that completed execution (e.g., as part of a
    # parallel group) but have not yet been validated.  This runs before the pending-task
    # scan so that parallel-group validation is scheduled before any new work is started,
    # preventing a permanent deadlock where dependents wait on an unvalidated prerequisite.
    validation_pending = _find_validation_pending_task(all_tasks, validation_meta)
    if validation_pending is not None:
        task_id = validation_pending["id"]
        agent_name = validation_pending.get("agent", "coder")
        print(
            f"[find_next_task] Validation-pending task: {task_id} - "
            f"{validation_pending.get('name', '')} (agent={agent_name})"
        )
        add_trace_metadata({
            "node_name": "find_next_task",
            "graph_level": "executor",
            "current_task_id": task_id,
            "task_name": validation_pending.get("name", ""),
            "agent": agent_name,
            "decision": "needs_validation",
            "completed_count": completed_count,
            "total_count": total_count,
        })
        return {
            "plan_data": plan_data,
            "current_task_id": task_id,
            "deadlock_detected": False,
        }

    pending_tasks = [t for t in all_tasks if t.get("status") == PENDING_STATUS]

    if not pending_tasks:
        print("[find_next_task] All tasks completed or no pending tasks remain")
        add_trace_metadata({
            "node_name": "find_next_task",
            "decision": "stop",
            "reason": "no_pending_tasks",
            "cycle_number": cycle_number,
            "tasks_completed": tasks_completed_str,
        })
        return {"plan_data": plan_data, "current_task_id": None, "deadlock_detected": False}

    eligible = _find_eligible_task(pending_tasks, completed_ids)
    if eligible is None:
        deadlock_details = _build_deadlock_details(pending_tasks, completed_ids)
        blocked_summary = "; ".join(
            f"{d['task_id']} (unsatisfied: {d['unsatisfied_deps']})"
            for d in deadlock_details
        )
        logger.warning(
            "Deadlock: %d pending task(s) with no eligible next step — %s",
            len(pending_tasks),
            blocked_summary,
        )
        add_trace_metadata({
            "node_name": "find_next_task",
            "decision": "stop",
            "reason": "deadlock",
            "cycle_number": cycle_number,
            "tasks_completed": tasks_completed_str,
            "deadlock_details": deadlock_details,
        })
        return {
            "plan_data": plan_data,
            "current_task_id": None,
            "deadlock_detected": True,
            "deadlock_details": deadlock_details,
        }

    current_model: ModelTier = state.get("effective_model") or "haiku"
    effective = _effective_model_for_task(eligible, current_model)

    agent_name = eligible.get("agent", "coder")
    print(
        f"[find_next_task] Selected task: {eligible['id']} - {eligible.get('name', '')} "
        f"(agent={agent_name}, model={effective})"
    )
    add_trace_metadata({
        "node_name": "find_next_task",
        "graph_level": "executor",
        "current_task_id": eligible["id"],
        "task_name": eligible.get("name", ""),
        "agent": agent_name,
        "effective_model": effective,
        "completed_count": completed_count,
        "total_count": total_count,
    })
    return {
        "plan_data": plan_data,
        "current_task_id": eligible["id"],
        "effective_model": effective,
        "deadlock_detected": False,
    }
