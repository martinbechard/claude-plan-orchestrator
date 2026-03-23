# langgraph_pipeline/shared/suspension.py
# Suspension marker helpers shared by plan-orchestrator.py and auto-pipeline.py.
# Design: docs/plans/2026-02-26-03-extract-slack-modules-design.md

"""Suspension marker file management for human-in-the-loop question flows.

Work items that need human input are suspended by writing a JSON marker file
to SUSPENDED_DIR. The pipeline checks these files to resume items once
answered.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

# ── Constants ─────────────────────────────────────────────────────────────────

SUSPENDED_DIR = ".claude/suspended"
SUSPENSION_TIMEOUT_MINUTES = 1440  # 24 hours default


# ── Marker file operations ────────────────────────────────────────────────────


def create_suspension_marker(
    slug: str,
    item_type: str,
    item_path: str,
    plan_path: str,
    task_id: str,
    question: str,
    question_context: str,
) -> str:
    """Create a suspension marker file for a work item.

    Writes a JSON file to SUSPENDED_DIR/<slug>.json containing all state
    needed to reinstate the item after a human answers the question via Slack.

    Returns the path to the marker file.
    """
    marker = {
        "slug": slug,
        "item_type": item_type,
        "item_path": item_path,
        "plan_path": plan_path,
        "task_id": task_id,
        "question": question,
        "question_context": question_context,
        "suspended_at": datetime.now(tz=ZoneInfo("UTC")).isoformat(),
        "timeout_minutes": SUSPENSION_TIMEOUT_MINUTES,
        "slack_thread_ts": "",
        "slack_channel_id": "",
        "answer": "",
    }
    os.makedirs(SUSPENDED_DIR, exist_ok=True)
    marker_path = os.path.join(SUSPENDED_DIR, f"{slug}.json")
    with open(marker_path, "w") as f:
        json.dump(marker, f, indent=2)
    return marker_path


def read_suspension_marker(slug: str) -> Optional[dict]:
    """Read a suspension marker file. Returns None if not found."""
    marker_path = os.path.join(SUSPENDED_DIR, f"{slug}.json")
    if not os.path.isfile(marker_path):
        return None
    try:
        with open(marker_path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def clear_suspension_marker(slug: str) -> bool:
    """Remove a suspension marker file. Returns True if removed."""
    marker_path = os.path.join(SUSPENDED_DIR, f"{slug}.json")
    if not os.path.isfile(marker_path):
        return False
    os.remove(marker_path)
    return True


def is_item_suspended(slug: str) -> bool:
    """Check if an item has an active suspension marker.

    Returns False if:
    - No marker file exists
    - The marker has timed out (suspended_at + timeout_minutes has passed)
    The marker is cleared automatically on timeout.
    """
    marker = read_suspension_marker(slug)
    if marker is None:
        return False

    try:
        suspended_at = datetime.fromisoformat(marker["suspended_at"])
        timeout = timedelta(minutes=marker.get("timeout_minutes", SUSPENSION_TIMEOUT_MINUTES))
        if datetime.now(tz=ZoneInfo("UTC")) >= suspended_at + timeout:
            clear_suspension_marker(slug)
            return False
    except (KeyError, ValueError):
        return True

    return True


def get_suspension_answer(slug: str) -> Optional[str]:
    """Get the human's answer from a suspension marker, if available.

    Returns the answer string if non-empty, otherwise None.
    """
    marker = read_suspension_marker(slug)
    if marker is None:
        return None
    answer = marker.get("answer")
    if isinstance(answer, str) and answer.strip():
        return answer
    return None
