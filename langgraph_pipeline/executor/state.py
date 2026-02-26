# langgraph_pipeline/executor/state.py
# TaskState TypedDict schema for the task execution subgraph.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""State schema for the executor StateGraph.

TaskState is threaded through every node in the task execution subgraph.
The task_results field uses Annotated with operator.add so LangGraph merges
parallel branch results by appending rather than replacing.

Parent pipeline and child subgraph share plan_path and cost accumulator keys.
"""

import operator
from typing import Annotated, Literal, Optional

from typing_extensions import TypedDict

# ─── Domain literal types ─────────────────────────────────────────────────────

ModelTier = Literal["haiku", "sonnet", "opus"]
TaskStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]


class TaskResult(TypedDict):
    """Result record for a single task execution, accumulated in task_results."""

    task_id: str
    status: TaskStatus
    model: ModelTier
    cost_usd: float
    input_tokens: int
    output_tokens: int
    message: str  # brief summary or error description


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

    # ── Cost accumulators (shared with parent pipeline) ───────────────────────
    plan_cost_usd: float
    plan_input_tokens: int
    plan_output_tokens: int
