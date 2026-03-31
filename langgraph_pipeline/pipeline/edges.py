# langgraph_pipeline/pipeline/edges.py
# Conditional edge routing functions for the pipeline StateGraph.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Pure routing functions that read PipelineState and return destination node names.

Each function is a LangGraph conditional edge: it takes the current state and
returns a string identifying the next node, or END to terminate the graph.
Keeping routing logic here (separate from node implementations) makes it easy
to test edge decisions without executing any node side effects.
"""

import logging

from langgraph.graph import END

from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.langsmith import add_trace_metadata

logger = logging.getLogger(__name__)

# ─── Routing policy constants ─────────────────────────────────────────────────

MAX_VERIFICATION_CYCLES = 3

# ─── Destination node name constants ─────────────────────────────────────────
# These must match the node names used when assembling the StateGraph in graph.py.

NODE_INTAKE_ANALYZE = "intake_analyze"
NODE_STRUCTURE_REQS = "structure_requirements"
NODE_CREATE_PLAN = "create_plan"
NODE_EXECUTE_PLAN = "execute_plan"
NODE_VERIFY_FIX = "verify_fix"
NODE_ARCHIVE = "archive"
NODE_RUN_INVESTIGATION = "run_investigation"
NODE_PROCESS_INVESTIGATION = "process_investigation"


# ─── Edge routing functions ───────────────────────────────────────────────────


def route_after_intake(state: PipelineState) -> str:
    """Route from intake_analyze: END on quota exhaustion, else branch by item type.

    Investigation items diverge to run_investigation.  All other item types
    continue to structure_requirements.
    """
    if state.get("quota_exhausted"):
        return END
    if state.get("item_type") == "investigation":
        return NODE_RUN_INVESTIGATION
    if not state.get("clause_register_path"):
        logger.warning("route_after_intake: no clause_register_path — traceability chain incomplete")
    return NODE_STRUCTURE_REQS


def route_after_investigation(state: PipelineState) -> str:
    """Route from run_investigation to process_investigation."""
    return NODE_PROCESS_INVESTIGATION


def route_after_process_investigation(state: PipelineState) -> str:
    """Route from process_investigation: END when should_stop is True, else archive.

    should_stop is set True when the investigation is awaiting a Slack reply
    (the pipeline suspends and resumes on the next cycle).  Once the reply is
    received and proposals are filed, should_stop is False and the item is
    moved to the completed-backlog via the archive node.
    """
    if state.get("should_stop"):
        return END
    return NODE_ARCHIVE


def route_after_requirements(state: PipelineState) -> str:
    """Route from structure_requirements: END on quota/failure, else create_plan."""
    if state.get("quota_exhausted"):
        return END
    if not state.get("requirements_path"):
        logger.warning("route_after_requirements: no requirements_path — ending pipeline run")
        return END
    return NODE_CREATE_PLAN


def route_after_plan(state: PipelineState) -> str:
    """Route from create_plan: END on quota/plan failure, else execute_plan."""
    if state.get("quota_exhausted"):
        return END
    if not state.get("plan_path"):
        logger.warning("route_after_plan: no plan_path — ending pipeline run")
        return END
    return NODE_EXECUTE_PLAN


def route_after_execution(state: PipelineState) -> str:
    """Route from execute_plan based on the item type.

    Quota exhaustion takes priority: return END so the item remains on disk
    for re-discovery after quota restores.  Executor deadlock routes directly
    to archive (skips verification — there is nothing to verify when tasks
    never ran).  Otherwise, defects go to verification and all other item
    types go to archival.
    """
    if state.get("quota_exhausted"):
        return END
    if state.get("executor_deadlock"):
        details = state.get("executor_deadlock_details") or []
        blocked_ids = ", ".join(d.get("task_id", "?") for d in details)
        logger.warning(
            "route_after_execution: executor deadlock — routing to archive "
            "(blocked tasks: %s)",
            blocked_ids,
        )
        return NODE_ARCHIVE
    if state.get("item_type") == "defect":
        return NODE_VERIFY_FIX
    return NODE_ARCHIVE


def cycles_exhausted(state: PipelineState) -> bool:
    """Return True if the verification cycle count has reached the maximum.

    This predicate is used by verify_result to decide whether a failed
    verification should trigger a retry or force archival as exhausted.
    """
    return (state.get("verification_cycle") or 0) >= MAX_VERIFICATION_CYCLES


def verify_result(state: PipelineState) -> str:
    """Route from verify_fix based on the last outcome and remaining cycles.

    Decision tree:
    - No history yet            → NODE_ARCHIVE   (safety fallback)
    - Last outcome is PASS      → NODE_ARCHIVE   (done)
    - Last outcome is FAIL
        - cycles not exhausted  → NODE_CREATE_PLAN  (retry with new plan)
        - cycles exhausted      → NODE_ARCHIVE   (mark exhausted)

    Emits pipeline_decision trace metadata with the routing rationale.
    """
    history = state.get("verification_history") or []
    cycle_number = state.get("verification_cycle") or 0
    cycles_done_str = f"{cycle_number}/{MAX_VERIFICATION_CYCLES}"

    if not history:
        add_trace_metadata({
            "decision": "archive",
            "reason": "no_verification_history",
            "cycle_number": cycle_number,
            "tasks_completed": cycles_done_str,
        })
        return NODE_ARCHIVE

    last_outcome = history[-1].get("outcome")
    if last_outcome == "PASS":
        add_trace_metadata({
            "decision": "archive",
            "reason": "validator_passed",
            "cycle_number": cycle_number,
            "tasks_completed": cycles_done_str,
        })
        return NODE_ARCHIVE

    if cycles_exhausted(state):
        add_trace_metadata({
            "decision": "archive",
            "reason": "max_verification_cycles_reached",
            "cycle_number": cycle_number,
            "tasks_completed": cycles_done_str,
        })
        return NODE_ARCHIVE

    add_trace_metadata({
        "decision": "retry",
        "reason": "validator_failed_retrying",
        "cycle_number": cycle_number,
        "tasks_completed": cycles_done_str,
    })
    return NODE_CREATE_PLAN
