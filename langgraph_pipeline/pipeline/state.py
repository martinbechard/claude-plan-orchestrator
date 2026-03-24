# langgraph_pipeline/pipeline/state.py
# PipelineState TypedDict schema for the top-level pipeline StateGraph.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Shared state schema for the pipeline LangGraph StateGraph.

PipelineState is threaded through every node and conditional edge.  List fields
that accumulate data across multiple passes use Annotated with operator.add so
LangGraph merges them by appending rather than replacing.
"""

import operator
from typing import Annotated, Literal, Optional

from typing_extensions import TypedDict

# ─── Domain literal types ─────────────────────────────────────────────────────

ItemType = Literal["defect", "feature", "analysis"]
VerificationOutcome = Literal["PASS", "FAIL"]


class VerificationRecord(TypedDict):
    """A single verification run result appended to verification_history."""

    outcome: VerificationOutcome
    timestamp: str  # ISO-8601 timestamp of when verification ran
    notes: str  # summary output from the verification step


# ─── Pipeline state ───────────────────────────────────────────────────────────


class PipelineState(TypedDict):
    """State threaded through the pipeline StateGraph.

    Fields are populated by nodes as the item progresses through the pipeline:
      scan_backlog     → item_path, item_slug, item_type, item_name
      intake_analyze   → (validates/enriches the item fields)
      create_plan      → plan_path, design_doc_path
      execute_plan     → session_cost_usd, session_input_tokens, session_output_tokens
      verify_symptoms  → verification_history (append), verification_cycle
    """

    # ── Item metadata (set by scan_backlog / intake_analyze) ──────────────────
    item_path: str
    item_slug: str
    item_type: ItemType
    item_name: str

    # ── Plan files (set by create_plan) ──────────────────────────────────────
    plan_path: Optional[str]
    design_doc_path: Optional[str]

    # ── Verification (appended by verify_symptoms) ────────────────────────────
    verification_cycle: int
    # Annotated with operator.add so each verify_symptoms call appends its record.
    verification_history: Annotated[list[VerificationRecord], operator.add]

    # ── Control flags ─────────────────────────────────────────────────────────
    should_stop: bool
    rate_limited: bool
    rate_limit_reset: Optional[str]  # ISO-8601 string when rate limit resets
    quota_exhausted: bool            # True when Claude reports exhaustion with no reset time

    # ── Budget enforcement (set by runner, checked after each graph.invoke()) ──
    budget_cap_usd: Optional[float]  # None means no cap

    # ── Cost and token tracking (updated by execute_plan) ─────────────────────
    session_cost_usd: float
    session_input_tokens: int
    session_output_tokens: int

    # ── In-graph intake counters (separate from disk-persisted throttle) ──────
    intake_count_defects: int
    intake_count_features: int

    # ── LangSmith root trace ──────────────────────────────────────────────────
    langsmith_root_run_id: Optional[str]  # UUID of the shared root RunTree for this item
