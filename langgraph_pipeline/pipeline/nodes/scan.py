# langgraph_pipeline/pipeline/nodes/scan.py
# scan_backlog LangGraph node: scans backlog directories and selects the next work item.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""scan_backlog node for the pipeline StateGraph.

Scans the backlog directories in priority order (defects, then features, then
analyses), checks for in-progress plans that need resuming, and populates
item_path, item_slug, item_type, and item_name in PipelineState.

When no items are found, returns an empty item_path so the has_items conditional
edge routes the graph to END (sleep/wait cycle).
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

import yaml

from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.langsmith import add_trace_metadata, create_root_run
from langgraph_pipeline.shared.paths import (
    ANALYSIS_DIR,
    BACKLOG_DIRS,
    CLAIMED_DIR,
    DEFECT_DIR,
    FEATURE_DIR,
    PLANS_DIR,
)

# ─── Constants ────────────────────────────────────────────────────────────────

SAMPLE_PLAN_FILENAME = "sample-plan.yaml"

CLAIM_META_SUFFIX = ".claim-meta.json"

# Status patterns in backlog files that indicate already-processed items.
COMPLETED_STATUS_PATTERN = re.compile(
    r"^##\s*Status:\s*(Fixed|Completed)", re.IGNORECASE | re.MULTILINE
)

# Backlog slug pattern: any slug starting with a word character (letter, digit,
# or underscore) followed by word characters and hyphens. Accepts single-digit
# prefixes (e.g. 9-foo) and prose slugs (e.g. cost-analysis).
BACKLOG_SLUG_PATTERN = re.compile(r"^[\w][\w-]*$")

# Priority-ordered (item_type, directory) pairs for scanning.
BACKLOG_SCAN_ORDER = [
    ("defect", DEFECT_DIR),
    ("feature", FEATURE_DIR),
    ("analysis", ANALYSIS_DIR),
]

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _is_item_completed(filepath: str) -> bool:
    """Return True if the backlog item file has a completed or fixed status header."""
    try:
        with open(filepath, "r") as f:
            content = f.read(2000)
        return bool(COMPLETED_STATUS_PATTERN.search(content))
    except (IOError, OSError):
        return False


def _scan_directory(directory: str, item_type: str) -> list[tuple[str, str, str]]:
    """Return (filepath, slug, item_type) tuples for ready items in a backlog directory.

    Skips hidden files, slugs that don't match the NN-slug pattern, and items
    whose status headers indicate they have already been completed.
    """
    items: list[tuple[str, str, str]] = []
    dir_path = Path(directory)

    if not dir_path.exists():
        return items

    claimed_dir_resolved = Path(CLAIMED_DIR).resolve()

    for md_file in sorted(dir_path.glob("*.md")):
        if md_file.name.startswith("."):
            continue

        if md_file.resolve().parent == claimed_dir_resolved:
            continue

        slug = md_file.stem
        if not BACKLOG_SLUG_PATTERN.match(slug):
            logging.warning(
                "scan_backlog: skipping %s — slug %r does not match expected pattern",
                md_file,
                slug,
            )
            continue

        if _is_item_completed(str(md_file)):
            continue

        items.append((str(md_file), slug, item_type))

    return items


def _find_in_progress_plans() -> list[str]:
    """Return paths of YAML plans that were started but not yet finished.

    A plan is "in progress" when it has at least one completed task AND at least
    one pending or in_progress task. Excludes sample-plan.yaml and plans whose
    meta.status is "failed".
    """
    in_progress: list[str] = []
    plans_dir = Path(PLANS_DIR)

    if not plans_dir.exists():
        return in_progress

    for yaml_file in sorted(plans_dir.glob("*.yaml")):
        if yaml_file.name == SAMPLE_PLAN_FILENAME:
            continue

        try:
            with open(yaml_file, "r") as f:
                plan = yaml.safe_load(f)
        except (IOError, yaml.YAMLError):
            continue

        if not plan or "sections" not in plan:
            continue

        meta = plan.get("meta", {})
        if isinstance(meta, dict) and meta.get("status") == "failed":
            continue

        has_completed = False
        has_pending = False

        for section in plan.get("sections", []):
            for task in section.get("tasks", []):
                status = task.get("status", "pending")
                if status == "completed":
                    has_completed = True
                elif status in ("pending", "in_progress"):
                    has_pending = True

        if has_completed and has_pending:
            in_progress.append(str(yaml_file))

    return in_progress


def _source_item_for_plan(plan_path: str) -> Optional[str]:
    """Return the source_item path from a plan's meta section, or None.

    The source_item field stores the original backlog file path
    (e.g. 'docs/defect-backlog/01-some-bug.md').
    """
    try:
        with open(plan_path, "r") as f:
            plan = yaml.safe_load(f)
        return plan.get("meta", {}).get("source_item") or None
    except (IOError, yaml.YAMLError):
        return None


def _item_type_from_path(filepath: str) -> str:
    """Infer item_type from the backlog directory in the file path."""
    path_lower = filepath.lower()
    if "defect" in path_lower:
        return "defect"
    if "feature" in path_lower:
        return "feature"
    return "analysis"


# ─── Item claiming ────────────────────────────────────────────────────────────


def claim_item(item_path: str, item_type: str = "feature") -> bool:
    """Atomically claim a backlog item by moving it into CLAIMED_DIR.

    Uses os.rename(), which is atomic on POSIX: exactly one process wins the
    race; all others receive FileNotFoundError and return False.

    Returns True when the item was successfully claimed.
    Returns False when the item is already in CLAIMED_DIR (same-path guard)
    or when another process claimed it first (FileNotFoundError).
    Propagates any other OSError (permissions, cross-device move, etc.).
    """
    os.makedirs(CLAIMED_DIR, exist_ok=True)
    basename = os.path.basename(item_path)
    claimed_path = os.path.join(CLAIMED_DIR, basename)

    if os.path.abspath(item_path) == os.path.abspath(claimed_path):
        logging.warning(
            "claim_item: item %s is already in CLAIMED_DIR — skipping.", item_path
        )
        return False

    try:
        os.rename(item_path, claimed_path)
        return True
    except FileNotFoundError:
        return False


def unclaim_item(claimed_path: str, item_type: str) -> None:
    """Return a claimed item to its original backlog directory.

    Called by the supervisor when a worker crashes, so the item re-enters
    the backlog and can be picked up by a subsequent scan.

    Raises KeyError if item_type is not a recognised backlog type.
    Propagates OSError if the rename fails.
    """
    backlog_dir = BACKLOG_DIRS[item_type]
    basename = os.path.basename(claimed_path)
    original_path = os.path.join(backlog_dir, basename)
    os.rename(claimed_path, original_path)


# ─── Node ─────────────────────────────────────────────────────────────────────


def scan_backlog(state: PipelineState) -> dict:
    """LangGraph node: scan backlog directories and select the next work item.

    If item_path is already populated in state (pre-scanned by the CLI loop),
    this node short-circuits and returns the existing state unchanged. This
    avoids redundant directory scanning when the CLI has already identified
    the next work item outside the graph.

    Priority order:
    1. In-progress plans: resume work on any plan that was started but not finished.
    2. Defects: highest-priority new items.
    3. Features: medium-priority new items.
    4. Analyses: lowest-priority new items.

    Returns partial state. When an item is found, item_path, item_slug,
    item_type, item_name, and plan_path are populated. When the backlog is
    empty, item_path is set to an empty string so the has_items conditional
    edge routes to END.
    """
    # Short-circuit if the CLI already pre-scanned an item.
    if state.get("item_path"):
        return {}

    claimed_dir_resolved = Path(CLAIMED_DIR).resolve()

    # Priority 1: Resume in-progress plans.
    in_progress = _find_in_progress_plans()
    if in_progress:
        plan_path = in_progress[0]
        source_item = _source_item_for_plan(plan_path)
        if source_item and Path(source_item).exists():
            if Path(source_item).resolve().parent == claimed_dir_resolved:
                logging.warning(
                    "scan_backlog: source_item %s is already in CLAIMED_DIR — "
                    "skipping plan %s (item is already being processed).",
                    source_item,
                    plan_path,
                )
                source_item = None
        if source_item and Path(source_item).exists():
            filepath = source_item
            slug = Path(filepath).stem
            item_type = _item_type_from_path(filepath)
            _, root_run_id = create_root_run(slug, filepath)
            add_trace_metadata({
                "node_name": "scan_backlog",
                "graph_level": "pipeline",
                "item_slug": slug,
                "item_type": item_type,
            })
            return {
                "item_path": filepath,
                "item_slug": slug,
                "item_type": item_type,
                "item_name": slug.replace("-", " ").title(),
                "plan_path": plan_path,
                "langsmith_root_run_id": root_run_id,
            }

    # Priority 2–4: Scan backlog directories in declared order.
    for item_type, directory in BACKLOG_SCAN_ORDER:
        items = _scan_directory(directory, item_type)
        if items:
            filepath, slug, found_type = items[0]
            _, root_run_id = create_root_run(slug, filepath)
            add_trace_metadata({
                "node_name": "scan_backlog",
                "graph_level": "pipeline",
                "item_slug": slug,
                "item_type": found_type,
            })
            return {
                "item_path": filepath,
                "item_slug": slug,
                "item_type": found_type,
                "item_name": slug.replace("-", " ").title(),
                "plan_path": None,
                "langsmith_root_run_id": root_run_id,
            }

    # Backlog is empty — return sentinel values to trigger END routing.
    return {
        "item_path": "",
        "item_slug": "",
        "item_type": "feature",
        "item_name": "",
        "plan_path": None,
        "langsmith_root_run_id": None,
    }
