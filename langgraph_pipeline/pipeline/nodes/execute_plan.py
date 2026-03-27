# langgraph_pipeline/pipeline/nodes/execute_plan.py
# execute_plan LangGraph node: invokes the executor subgraph to run a YAML plan.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""execute_plan node for the pipeline StateGraph.

Invokes the executor subgraph to execute a YAML plan, replacing the subprocess
bridge to plan-orchestrator.py.  The executor subgraph handles task selection,
Claude CLI execution, validation, parallel worktree execution, circuit breaking,
and model escalation entirely within LangGraph.

State flows between parent pipeline and child subgraph via explicit mapping:
  PipelineState.plan_path  -> TaskState.plan_path
  TaskState.plan_cost_usd  -> PipelineState.session_cost_usd
  TaskState.*_tokens       -> PipelineState.session_*_tokens
"""

from typing import Optional

from langgraph_pipeline.executor.escalation import DEFAULT_STARTING_MODEL
from langgraph_pipeline.executor.graph import build_executor_graph
from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.langsmith import add_trace_metadata

# ─── Constants ────────────────────────────────────────────────────────────────

# Initial values for TaskState fields that have no counterpart in PipelineState.
_INITIAL_TASK_ATTEMPT = 1
_INITIAL_COST = 0.0
_INITIAL_TOKENS = 0
_INITIAL_FAILURES = 0


# ─── Node ─────────────────────────────────────────────────────────────────────


def execute_plan(state: PipelineState) -> dict:
    """LangGraph node: execute a YAML plan via the executor subgraph.

    Builds an initial TaskState from PipelineState, compiles and invokes the
    executor subgraph, then maps cost and token accumulators back into
    PipelineState fields.

    Returns partial state updates:
      session_cost_usd: total API-equivalent cost accumulated by all tasks.
      session_input_tokens: total input tokens across all task executions.
      session_output_tokens: total output tokens across all task executions.
    """
    plan_path: Optional[str] = state.get("plan_path")
    item_slug: str = state.get("item_slug", "")
    item_type: str = state.get("item_type", "feature")

    if not plan_path:
        print(f"[execute_plan] No plan_path in state for {item_slug!r}; skipping.")
        return {}

    print(f"[execute_plan] Invoking executor subgraph for plan: {plan_path}")

    initial_task_state: dict = {
        "plan_path": plan_path,
        "plan_data": None,
        "current_task_id": None,
        "task_attempt": _INITIAL_TASK_ATTEMPT,
        "task_results": [],
        "effective_model": DEFAULT_STARTING_MODEL,
        "consecutive_failures": _INITIAL_FAILURES,
        "last_validation_verdict": None,
        "plan_verification_notes": None,
        "plan_cost_usd": _INITIAL_COST,
        "plan_input_tokens": _INITIAL_TOKENS,
        "plan_output_tokens": _INITIAL_TOKENS,
        "langsmith_root_run_id": state.get("langsmith_root_run_id"),
    }

    executor = build_executor_graph().compile()
    executor_config: dict | None = {"run_name": item_slug} if item_slug else None
    final_task_state = executor.invoke(initial_task_state, config=executor_config)

    cost_usd = float(final_task_state.get("plan_cost_usd") or _INITIAL_COST)
    input_tokens = int(final_task_state.get("plan_input_tokens") or _INITIAL_TOKENS)
    output_tokens = int(final_task_state.get("plan_output_tokens") or _INITIAL_TOKENS)

    task_count = len(final_task_state.get("task_results") or [])
    print(
        f"[execute_plan] Executor subgraph finished for {item_slug!r}: "
        f"{task_count} task(s), ${cost_usd:.4f}"
    )

    add_trace_metadata({
        "node_name": "execute_plan",
        "graph_level": "pipeline",
        "item_slug": item_slug,
        "item_type": item_type,
        "task_count": task_count,
        "total_cost_usd": cost_usd,
        "tags": [item_slug, item_type],
    })

    return {
        "session_cost_usd": cost_usd,
        "session_input_tokens": input_tokens,
        "session_output_tokens": output_tokens,
        "quota_exhausted": bool(final_task_state.get("quota_exhausted")),
        "last_validation_verdict": final_task_state.get("last_validation_verdict"),
        "verification_notes": final_task_state.get("plan_verification_notes"),
    }
