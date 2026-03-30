# langgraph_pipeline/pipeline/nodes/archival.py
# archive LangGraph node: move completed work items to the completed-backlog.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md
# Design: docs/plans/2026-03-30-78-item-archived-as-success-with-pending-tasks-design.md

"""archive node for the pipeline StateGraph.

Moves a processed backlog item to the appropriate completed-backlog
subdirectory, removes the plan YAML from tmp/plans/, and sends
a Slack notification summarising the outcome.

The archive node handles three outcome types:
  - Feature / analysis item: always a successful completion.
  - Defect with PASS verification: successful fix.
  - Defect with FAIL verification and exhausted cycles: marked as exhausted.
"""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.langsmith import (
    LANGSMITH_TRACE_PATTERN,
    add_trace_metadata,
    finalize_root_run,
)
from langgraph_pipeline.shared.paths import COMPLETED_DIRS, WORKER_OUTPUT_DIR
from langgraph_pipeline.slack.notifier import SlackNotifier

# ─── Constants ────────────────────────────────────────────────────────────────

SLACK_LEVEL_SUCCESS = "success"
SLACK_LEVEL_WARNING = "warning"
SLACK_LEVEL_ERROR = "error"

ARCHIVE_OUTCOME_SUCCESS = "completed"
ARCHIVE_OUTCOME_EXHAUSTED = "exhausted"
ARCHIVE_OUTCOME_INCOMPLETE = "incomplete"

ARCHIVE_TERMINAL_STATUSES = frozenset({"verified", "failed", "skipped"})

ARCHIVE_WARNINGS_FILENAME = "archive-warnings.txt"

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _find_non_terminal_tasks(plan_path: Optional[str]) -> list[tuple[str, str, str]]:
    """Read the plan YAML and return tasks that have not reached a terminal status.

    Returns a list of (task_id, task_name, task_status) tuples for every task
    whose status is not in ARCHIVE_TERMINAL_STATUSES.  Returns an empty list
    when plan_path is None, the file does not exist, or the file cannot be parsed.
    """
    if not plan_path:
        return []
    path = Path(plan_path)
    if not path.exists():
        return []
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        non_terminal: list[tuple[str, str, str]] = []
        for section in data.get("sections", []):
            for task in section.get("tasks", []):
                status = task.get("status", "")
                if status not in ARCHIVE_TERMINAL_STATUSES:
                    non_terminal.append((
                        task.get("id", ""),
                        task.get("name", ""),
                        status,
                    ))
        return non_terminal
    except (OSError, yaml.YAMLError) as exc:
        print(f"[archive] Could not read plan YAML for task status check: {exc}")
        return []


def _last_verification_outcome(state: PipelineState) -> Optional[str]:
    """Return the outcome of the most recent VerificationRecord, or None."""
    history = state.get("verification_history") or []
    if not history:
        return None
    return history[-1].get("outcome")


def _determine_outcome(
    state: PipelineState,
    non_terminal_tasks: Optional[list[tuple[str, str, str]]] = None,
) -> str:
    """Classify the archive outcome as completed, exhausted, or incomplete.

    When non_terminal_tasks is non-empty, the outcome is ARCHIVE_OUTCOME_INCOMPLETE
    regardless of item type or verification history. This acts as a pre-commit gate
    that prevents any item from being silently archived as success while tasks remain
    pending or blocked.

    When all tasks are terminal, features and analyses are always completed
    successfully (no verification step). For defects, the last verification outcome
    determines success. When the last outcome is FAIL (cycles exhausted caused routing
    to archive), the item is marked as exhausted rather than completed.
    """
    if non_terminal_tasks:
        return ARCHIVE_OUTCOME_INCOMPLETE

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


def _preserve_plan_yaml(plan_path: Optional[str], slug: str) -> None:
    """Copy the plan YAML to permanent locations before cleanup.

    Preserves the plan in the per-item workspace and worker-output directory
    so it remains accessible as documentation after the working copy in
    tmp/plans/ is removed.
    """
    if not plan_path or not slug:
        return
    path = Path(plan_path)
    if not path.exists():
        return

    import shutil
    from langgraph_pipeline.shared.paths import WORKER_OUTPUT_DIR, workspace_path

    # Copy to workspace
    ws = workspace_path(slug)
    if ws.exists():
        try:
            shutil.copy2(str(path), ws / "plan.yaml")
        except OSError:
            pass

    # Copy to worker-output (permanent, survives workspace cleanup)
    output_dir = WORKER_OUTPUT_DIR / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(str(path), output_dir / "plan.yaml")
    except OSError:
        pass


def _remove_plan_yaml(plan_path: Optional[str]) -> None:
    """Delete the plan YAML file from tmp/plans/ if it exists."""
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
    item_name: str,
    item_type: str,
    outcome: str,
    non_terminal_tasks: Optional[list[tuple[str, str, str]]] = None,
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

    if outcome == ARCHIVE_OUTCOME_INCOMPLETE:
        task_lines = "\n".join(
            f"  • {task_id}: {task_name!r} (status={task_status})"
            for task_id, task_name, task_status in (non_terminal_tasks or [])
        )
        msg = (
            f":warning: *{type_label} archived incomplete* — {item_name}\n"
            f"Non-terminal tasks at archive time:\n{task_lines}"
        )
        return msg, SLACK_LEVEL_WARNING

    msg = f":white_check_mark: *{type_label} completed* — {item_name}"
    return msg, SLACK_LEVEL_SUCCESS


def _write_archive_warnings(slug: str, non_terminal_tasks: list[tuple[str, str, str]]) -> None:
    """Persist the list of non-terminal tasks to archive-warnings.txt in worker-output.

    Written to docs/reports/worker-output/{slug}/archive-warnings.txt so the
    evidence survives workspace cleanup and is visible to pipeline operators.
    """
    output_dir = WORKER_OUTPUT_DIR / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    lines = ["Non-terminal tasks at archive time:\n"]
    for task_id, task_name, task_status in non_terminal_tasks:
        lines.append(f"  {task_id}: {task_name!r} (status={task_status})\n")
    try:
        (output_dir / ARCHIVE_WARNINGS_FILENAME).write_text("".join(lines))
    except OSError as exc:
        print(f"[archive] Failed to write archive-warnings.txt: {exc}")


def _strip_trace_id_line(item_path: str) -> None:
    """Remove the LangSmith trace ID marker line from an item file before archiving.

    Completed item files in completed-backlog should not carry ephemeral trace
    metadata. Normalizes trailing newlines after removal. No-op when the file
    contains no trace line or cannot be read.

    Args:
        item_path: Path to the item markdown file to modify in-place.
    """
    try:
        with open(item_path) as f:
            content = f.read()
        stripped = LANGSMITH_TRACE_PATTERN.sub("", content)
        stripped = stripped.rstrip("\n") + "\n"
        with open(item_path, "w") as f:
            f.write(stripped)
    except OSError as exc:
        logger.debug("_strip_trace_id_line failed (non-fatal): %s", exc)


def _git_commit_archival(item_slug: str, item_type: str, outcome: str) -> None:
    """Stage and commit archival changes (moved/deleted files) to git.

    Stages the completed-backlog destination, deleted backlog source, and
    deleted plan YAML. If there are no staged changes, no commit is created.
    """
    try:
        # Stage all archival-related paths
        subprocess.run(
            ["git", "add", "-A",
             "docs/completed-backlog/", "docs/defect-backlog/",
             "docs/feature-backlog/", "tmp/plans/"],
            capture_output=True, timeout=10,
        )
        # Check if there's anything staged
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            return  # Nothing staged

        message = f"chore: archive {item_type} {item_slug} ({outcome})"
        subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True, timeout=10,
        )
        logger.info("Committed archival: %s", message)
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("Git commit for archival failed (non-fatal): %s", exc)


# ─── Node ─────────────────────────────────────────────────────────────────────


def archive(state: PipelineState) -> dict:
    """LangGraph node: archive a completed or exhausted work item.

    Steps:
    1. Enumerate non-terminal tasks from the plan YAML (pre-archive validation gate).
    2. Determine outcome (completed, exhausted, or incomplete based on task state and history).
    3. Finalize the LangSmith root trace and strip the trace ID line from the item file.
    4. Move the item file from the active backlog to the completed-backlog.
    5. Preserve plan YAML to permanent locations, then remove working copy from tmp/plans/.
    6. Write archive-warnings.txt when non-terminal tasks were found.
    7. Send a Slack notification with the outcome summary.
    8. Commit archival changes to git.

    Returns an empty dict — the pipeline is done processing this item and no
    further state mutations are needed.
    """
    item_path: str = state.get("item_path", "")
    item_slug: str = state.get("item_slug", "")
    item_type: str = state.get("item_type", "feature")
    item_name: str = state.get("item_name", item_slug)
    plan_path: Optional[str] = state.get("plan_path")
    langsmith_root_run_id: Optional[str] = state.get("langsmith_root_run_id")

    # Step 0: Pre-archive validation gate — detect non-terminal tasks.
    non_terminal_tasks = _find_non_terminal_tasks(plan_path)
    if non_terminal_tasks:
        print(f"[archive] WARNING: {len(non_terminal_tasks)} non-terminal task(s) found:")
        for task_id, task_name, task_status in non_terminal_tasks:
            print(f"  - {task_id}: {task_name!r} (status={task_status})")

    outcome = _determine_outcome(state, non_terminal_tasks)

    print(f"[archive] Archiving {item_slug} as {outcome}")

    # Step 1: Finalize the root LangSmith trace and strip the trace ID line.
    finalize_root_run(langsmith_root_run_id, {"item_slug": item_slug, "outcome": outcome}, item_slug=item_slug)
    if item_path:
        _strip_trace_id_line(item_path)

    # Step 2: Move item to completed-backlog.
    if item_path:
        dest = _move_item_to_completed(item_path, item_type)
        if dest:
            print(f"[archive] Moved {item_path} -> {dest}")

    # Step 3: Preserve plan YAML to permanent locations, then remove working copy.
    _preserve_plan_yaml(plan_path, item_slug)
    _remove_plan_yaml(plan_path)
    if plan_path:
        print(f"[archive] Preserved and removed plan YAML: {plan_path}")

    # Step 4: Write archive-warnings.txt when non-terminal tasks were detected.
    if non_terminal_tasks:
        _write_archive_warnings(item_slug, non_terminal_tasks)

    # Step 5: Slack notification.
    message, level = _build_slack_message(item_name, item_type, outcome, non_terminal_tasks)
    notifier = SlackNotifier()
    notifier.send_status(message, level=level)

    # Step 6: Commit archival changes to git.
    _git_commit_archival(item_slug, item_type, outcome)

    add_trace_metadata({
        "node_name": "archive",
        "graph_level": "pipeline",
        "item_slug": item_slug,
        "item_type": item_type,
        "outcome": outcome,
    })

    return {}
