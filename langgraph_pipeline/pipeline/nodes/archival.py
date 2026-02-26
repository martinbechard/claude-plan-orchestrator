# langgraph_pipeline/pipeline/nodes/archival.py
# archive LangGraph node: move completed work items to the completed-backlog.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""archive node for the pipeline StateGraph.

Moves a processed backlog item to the appropriate completed-backlog
subdirectory, removes the plan YAML from .claude/plans/, and sends
a Slack notification summarising the outcome.

The archive node handles three outcome types:
  - Feature / analysis item: always a successful completion.
  - Defect with PASS verification: successful fix.
  - Defect with FAIL verification and exhausted cycles: marked as exhausted.
"""

import shutil
from pathlib import Path
from typing import Optional

from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.langsmith import add_trace_metadata
from langgraph_pipeline.shared.paths import COMPLETED_DIRS
from langgraph_pipeline.slack.notifier import SlackNotifier

# ─── Constants ────────────────────────────────────────────────────────────────

SLACK_LEVEL_SUCCESS = "success"
SLACK_LEVEL_ERROR = "error"

ARCHIVE_OUTCOME_SUCCESS = "completed"
ARCHIVE_OUTCOME_EXHAUSTED = "exhausted"

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _last_verification_outcome(state: PipelineState) -> Optional[str]:
    """Return the outcome of the most recent VerificationRecord, or None."""
    history = state.get("verification_history") or []
    if not history:
        return None
    return history[-1].get("outcome")


def _determine_outcome(state: PipelineState) -> str:
    """Classify the archive outcome as completed or exhausted.

    Features and analyses are always completed successfully (no verification
    step).  For defects, the last verification outcome determines success.
    When the last outcome is FAIL (cycles exhausted caused routing to archive),
    the item is marked as exhausted rather than completed.
    """
    item_type: str = state.get("item_type", "feature")
    if item_type != "defect":
        return ARCHIVE_OUTCOME_SUCCESS

    last_outcome = _last_verification_outcome(state)
    if last_outcome == "PASS":
        return ARCHIVE_OUTCOME_SUCCESS
    if last_outcome == "FAIL":
        return ARCHIVE_OUTCOME_EXHAUSTED

    # No verification history for a defect: treat as success (plan ran without verify).
    return ARCHIVE_OUTCOME_SUCCESS


def _move_item_to_completed(item_path: str, item_type: str) -> Optional[str]:
    """Move the backlog item file to the matching completed-backlog directory.

    Creates the destination directory when it does not already exist.
    Returns the destination path on success, or None on failure.
    """
    dest_dir = COMPLETED_DIRS.get(item_type, COMPLETED_DIRS.get("feature", "docs/completed-backlog/features"))
    src = Path(item_path)
    if not src.exists():
        print(f"[archive] Source item not found, skipping move: {item_path}")
        return None

    dest = Path(dest_dir) / src.name
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        return str(dest)
    except (OSError, shutil.Error) as exc:
        print(f"[archive] Failed to move {item_path} to {dest_dir}: {exc}")
        return None


def _remove_plan_yaml(plan_path: Optional[str]) -> None:
    """Delete the plan YAML file from .claude/plans/ if it exists."""
    if not plan_path:
        return
    path = Path(plan_path)
    if not path.exists():
        return
    try:
        path.unlink()
    except OSError as exc:
        print(f"[archive] Failed to remove plan YAML {plan_path}: {exc}")


def _build_slack_message(
    item_name: str, item_type: str, outcome: str
) -> tuple[str, str]:
    """Build a (message, level) pair for the archive Slack notification.

    Returns (message_text, slack_level).
    """
    type_label = item_type.capitalize()
    if outcome == ARCHIVE_OUTCOME_EXHAUSTED:
        msg = (
            f":no_entry: *{type_label} exhausted* — {item_name}\n"
            "Verification cycles exhausted without a passing result. "
            "Moved to completed-backlog as unresolved."
        )
        return msg, SLACK_LEVEL_ERROR

    msg = f":white_check_mark: *{type_label} completed* — {item_name}"
    return msg, SLACK_LEVEL_SUCCESS


# ─── Node ─────────────────────────────────────────────────────────────────────


def archive(state: PipelineState) -> dict:
    """LangGraph node: archive a completed or exhausted work item.

    Steps:
    1. Determine outcome (completed vs exhausted based on verification history).
    2. Move the item file from the active backlog to the completed-backlog.
    3. Remove the plan YAML file from .claude/plans/.
    4. Send a Slack notification with the outcome summary.

    Returns an empty dict — the pipeline is done processing this item and no
    further state mutations are needed.
    """
    item_path: str = state.get("item_path", "")
    item_slug: str = state.get("item_slug", "")
    item_type: str = state.get("item_type", "feature")
    item_name: str = state.get("item_name", item_slug)
    plan_path: Optional[str] = state.get("plan_path")

    outcome = _determine_outcome(state)

    print(f"[archive] Archiving {item_slug} as {outcome}")

    # Step 1: Move item to completed-backlog.
    if item_path:
        dest = _move_item_to_completed(item_path, item_type)
        if dest:
            print(f"[archive] Moved {item_path} -> {dest}")

    # Step 2: Remove plan YAML.
    _remove_plan_yaml(plan_path)
    if plan_path:
        print(f"[archive] Removed plan YAML: {plan_path}")

    # Step 3: Slack notification.
    message, level = _build_slack_message(item_name, item_type, outcome)
    notifier = SlackNotifier()
    notifier.send_status(message, level=level)

    add_trace_metadata({
        "node_name": "archive",
        "graph_level": "pipeline",
        "item_slug": item_slug,
        "item_type": item_type,
        "outcome": outcome,
    })

    return {}
