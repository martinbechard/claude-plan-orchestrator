# langgraph_pipeline/pipeline/edges.py
# Conditional edge routing functions for the pipeline StateGraph.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Pure routing functions that read PipelineState and return destination node names.

Each function is a LangGraph conditional edge: it takes the current state and
returns a string identifying the next node, or END to terminate the graph.
Keeping routing logic here (separate from node implementations) makes it easy
to test edge decisions without executing any node side effects.
"""

from langgraph.graph import END

from langgraph_pipeline.pipeline.state import PipelineState

# ─── Routing policy constants ─────────────────────────────────────────────────

MAX_VERIFICATION_CYCLES = 3

# ─── Destination node name constants ─────────────────────────────────────────
# These must match the node names used when assembling the StateGraph in graph.py.

NODE_INTAKE_ANALYZE = "intake_analyze"
NODE_CREATE_PLAN = "create_plan"
NODE_EXECUTE_PLAN = "execute_plan"
NODE_VERIFY_SYMPTOMS = "verify_symptoms"
NODE_ARCHIVE = "archive"


# ─── Edge routing functions ───────────────────────────────────────────────────


def has_items(state: PipelineState) -> str:
    """Route from scan_backlog based on whether a work item was found.

    Returns NODE_INTAKE_ANALYZE when scan_backlog populated item_path,
    or END when the backlog is empty (triggering a sleep/wait cycle).
    """
    if state.get("item_path"):
        return NODE_INTAKE_ANALYZE
    return END


def after_intake(state: PipelineState) -> str:
    """Route from intake_analyze: END on quota exhaustion, else create_plan."""
    if state.get("quota_exhausted"):
        return END
    return NODE_CREATE_PLAN


def after_create_plan(state: PipelineState) -> str:
    """Route from create_plan: END on quota exhaustion, else execute_plan."""
    if state.get("quota_exhausted"):
        return END
    return NODE_EXECUTE_PLAN


def is_defect(state: PipelineState) -> str:
    """Route from execute_plan based on the item type.

    Quota exhaustion takes priority: return END so the item remains on disk
    for re-discovery after quota restores.  Otherwise, defects go to
    verification and all other item types go to archival.
    """
    if state.get("quota_exhausted"):
        return END
    if state.get("item_type") == "defect":
        return NODE_VERIFY_SYMPTOMS
    return NODE_ARCHIVE


def cycles_exhausted(state: PipelineState) -> bool:
    """Return True if the verification cycle count has reached the maximum.

    This predicate is used by verify_result to decide whether a failed
    verification should trigger a retry or force archival as exhausted.
    """
    return (state.get("verification_cycle") or 0) >= MAX_VERIFICATION_CYCLES


def verify_result(state: PipelineState) -> str:
    """Route from verify_symptoms based on the last outcome and remaining cycles.

    Decision tree:
    - No history yet            → NODE_ARCHIVE   (safety fallback)
    - Last outcome is PASS      → NODE_ARCHIVE   (done)
    - Last outcome is FAIL
        - cycles not exhausted  → NODE_CREATE_PLAN  (retry with new plan)
        - cycles exhausted      → NODE_ARCHIVE   (mark exhausted)
    """
    history = state.get("verification_history") or []
    if not history:
        return NODE_ARCHIVE

    last_outcome = history[-1].get("outcome")
    if last_outcome == "PASS":
        return NODE_ARCHIVE

    if cycles_exhausted(state):
        return NODE_ARCHIVE

    return NODE_CREATE_PLAN
