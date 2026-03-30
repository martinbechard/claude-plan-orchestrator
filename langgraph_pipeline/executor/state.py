# langgraph_pipeline/executor/state.py
# TaskState TypedDict schema and task lifecycle helpers for the executor subgraph.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md
# Design: docs/plans/2026-03-28-73-three-state-task-lifecycle-design.md
# Design: docs/plans/2026-03-30-80-executor-silent-deadlock-on-blocked-tasks-design.md

"""State schema and task lifecycle helpers for the executor StateGraph.

TaskState is threaded through every node in the task execution subgraph.
The task_results field uses Annotated with operator.add so LangGraph merges
parallel branch results by appending rather than replacing.

Parent pipeline and child subgraph share plan_path and cost accumulator keys.

The effective_status() helper provides backward-compatible status resolution:
legacy "completed" tasks are treated as "verified" when validation was not
configured or applicable, without mutating stored YAML values.
"""

import operator
from typing import Annotated, Literal, Optional

from typing_extensions import TypedDict

# ─── Domain literal types (continued) ────────────────────────────────────────

ValidationVerdict = Literal["PASS", "WARN", "FAIL"]

# ─── Domain literal types ─────────────────────────────────────────────────────

ModelTier = Literal["haiku", "sonnet", "opus"]
TaskStatus = Literal[
    "pending",       # not started
    "in_progress",   # currently executing
    "completed",     # execution succeeded, awaiting validation (intermediate)
    "verified",      # validation passed or not required (terminal success)
    "failed",        # execution or validation failed
    "skipped",       # deliberately skipped
]


class TaskResult(TypedDict):
    """Result record for a single task execution, accumulated in task_results."""

    task_id: str
    status: TaskStatus
    model: ModelTier
    cost_usd: float
    input_tokens: int
    output_tokens: int
    message: str  # brief summary or error description


# ─── Backward-compatible status resolution ───────────────────────────────────

# Status value for tasks that completed execution but have not yet been validated.
_STATUS_COMPLETED: TaskStatus = "completed"
# Terminal success status: validation passed or not required.
_STATUS_VERIFIED: TaskStatus = "verified"


def effective_status(task: dict, validation_meta: dict) -> TaskStatus:
    """Return the effective status of a task for dependency and progress checks.

    For tasks with status "completed", returns "verified" when backward-compatibility
    applies — i.e., validation was not configured, the task's agent is not in the
    run_after list, or the task has already been through validation. This is a pure
    read-time transformation that never mutates stored YAML values.

    For all other statuses (pending, in_progress, verified, failed, skipped), returns
    the raw status unchanged.

    Args:
        task: A plan task dict with at least a "status" key.
        validation_meta: The plan's meta.validation config dict. Expected keys:
            enabled (bool), run_after (list[str]), and optionally
            max_validation_attempts (int).

    Returns:
        The effective TaskStatus for dependency checking and progress counting.
    """
    raw_status: str = task.get("status", "pending")
    if raw_status != _STATUS_COMPLETED:
        return raw_status  # type: ignore[return-value]

    # Validation not enabled for this plan
    if not validation_meta.get("enabled", False):
        return _STATUS_VERIFIED

    # Task's agent is not in the run_after list
    run_after = validation_meta.get("run_after", [])
    agent_name = task.get("agent", "coder")
    if run_after and agent_name not in run_after:
        return _STATUS_VERIFIED

    # Task has already been through validation (validation_attempts > 0)
    if (task.get("validation_attempts") or 0) > 0:
        return _STATUS_VERIFIED

    # Genuinely awaiting validation — keep "completed"
    return _STATUS_COMPLETED


# ─── Executor subgraph state ──────────────────────────────────────────────────


class TaskState(TypedDict):
    """State threaded through the executor StateGraph.

    Fields are populated by nodes as execution progresses:
      find_next_task  → current_task_id, plan_data
      execute_task    → task_results (append), cost accumulators, consecutive_failures
      validate_task   → task_attempt (increment on FAIL)
      escalate        → effective_model (upgrade on repeated failure)
    """

    # ── Plan reference (shared with parent pipeline) ──────────────────────────
    plan_path: str
    plan_data: Optional[dict]  # parsed YAML content; None until first load

    # ── Current execution context ─────────────────────────────────────────────
    current_task_id: Optional[str]
    task_attempt: int  # retry counter for current task; reset on task change

    # ── Accumulated task results (fan-in merge via operator.add) ──────────────
    # Annotated with operator.add so parallel branches append without overwriting.
    task_results: Annotated[list[TaskResult], operator.add]

    # ── Model escalation ──────────────────────────────────────────────────────
    effective_model: ModelTier  # current model tier; escalates on failure

    # ── Circuit breaker ───────────────────────────────────────────────────────
    consecutive_failures: int  # resets to 0 on any task success

    # ── Validation tracking ───────────────────────────────────────────────────
    last_validation_verdict: Optional[ValidationVerdict]  # set by validate_task node
    plan_verification_notes: Optional[str]  # compact JSON {verdict, findings[], evidence} from validator

    # ── Quota exhaustion flag ─────────────────────────────────────────────────
    quota_exhausted: bool  # True when Claude reports exhaustion with no reset time

    # ── LangSmith root trace ──────────────────────────────────────────────────
    langsmith_root_run_id: Optional[str]  # UUID of the shared root RunTree from PipelineState

    # ── Deadlock detection ────────────────────────────────────────────────────
    # Set by find_next_task when pending tasks exist but none are eligible.
    # Propagated to PipelineState so downstream nodes can route appropriately.
    deadlock_detected: bool
    deadlock_details: Optional[list[dict]]  # [{task_id, task_name, unsatisfied_deps}]

    # ── Cost accumulators (shared with parent pipeline) ───────────────────────
    plan_cost_usd: float
    plan_input_tokens: int
    plan_output_tokens: int
