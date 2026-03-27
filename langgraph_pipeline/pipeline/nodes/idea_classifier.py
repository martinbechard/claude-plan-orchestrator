# langgraph_pipeline/pipeline/nodes/idea_classifier.py
# Ideas intake: classify raw idea files into formatted backlog items.
# Design: docs/plans/2026-03-24-ideas-intake-pipeline-design.md

"""Scan docs/ideas/ for unprocessed markdown files and classify each one into
properly formatted backlog items by spawning a Claude session.

Public API:
  scan_ideas()      -> list[str]  — find unprocessed idea files
  classify_idea()   -> bool       — classify a single idea via Claude
  process_ideas()   -> int        — process all pending ideas; return count
"""

import json
import logging
import os
import subprocess
from pathlib import Path

from langgraph_pipeline.shared.langsmith import add_trace_metadata
from langgraph_pipeline.shared.paths import (
    DEFECT_DIR,
    FEATURE_DIR,
    IDEAS_DIR,
    IDEAS_PROCESSED_DIR,
)

# ─── Constants ────────────────────────────────────────────────────────────────

IDEA_INTAKE_TIMEOUT_SECONDS = 300

IDEA_INTAKE_PROMPT = (
    "You are processing a raw idea file and converting it into one or more "
    "properly formatted backlog items.\n\n"
    "Raw idea file: {idea_path}\n"
    "Feature backlog directory: {feature_dir}\n"
    "Defect backlog directory: {defect_dir}\n"
    "Processed ideas directory: {processed_dir}\n\n"
    "Your tasks:\n"
    "1. Read the raw idea file at {idea_path}.\n"
    "2. Classify it as a feature request, a defect report, or multiple items "
    "(create one backlog file per distinct item).\n"
    "3. Assess priority (critical / high / medium / low) based on impact and urgency.\n"
    "4. Write one formatted .md file per backlog item into the appropriate directory "
    "({feature_dir} for features, {defect_dir} for defects). Use a short kebab-case "
    "filename that summarises the item.\n"
    "   Each file must contain these standard headers in order:\n"
    "   ## Status: Open\n"
    "   (Use '## Status: Needs Clarification' instead when the idea is too vague "
    "to act on without follow-up.)\n"
    "   ## Priority: <critical|high|medium|low>\n"
    "   ## Summary:\n"
    "   <one-paragraph description>\n"
    "   ## Scope:\n"
    "   <brief description of what is in/out of scope>\n"
    "   ## Files Affected:\n"
    "   <list of likely files or directories, or 'Unknown' if not determinable>\n"
    "5. Move the original idea file to {processed_dir}/ (create the directory if it "
    "does not exist).\n"
    "6. Run: git add -A && git commit -m 'intake: classify idea {idea_path}'\n\n"
    "Do not ask for confirmation. Complete all steps autonomously."
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


def scan_ideas() -> list[str]:
    """Return paths of unprocessed idea files in IDEAS_DIR.

    Skips dotfiles, empty files, and files whose basename already exists in
    IDEAS_PROCESSED_DIR. Returns an empty list when IDEAS_DIR does not exist.
    """
    ideas_path = Path(IDEAS_DIR)
    if not ideas_path.exists():
        return []

    processed_names: set[str] = set()
    processed_path = Path(IDEAS_PROCESSED_DIR)
    if processed_path.exists():
        processed_names = {f.name for f in processed_path.glob("*.md")}

    results: list[str] = []
    for candidate in sorted(ideas_path.glob("*.md")):
        if candidate.name.startswith("."):
            continue
        if os.path.getsize(candidate) == 0:
            continue
        if candidate.name in processed_names:
            continue
        results.append(str(candidate))

    return results


def classify_idea(idea_path: str, dry_run: bool = False) -> bool:
    """Classify a single idea file by spawning a Claude session.

    In dry_run mode, logs the action and returns True without invoking Claude.
    Returns True on success (original file moved to IDEAS_PROCESSED_DIR).
    Returns False on subprocess failure or when the file was not moved.
    """
    if dry_run:
        logger.info("[idea_classifier] dry-run: would classify %s", idea_path)
        return True

    prompt = IDEA_INTAKE_PROMPT.format(
        idea_path=idea_path,
        feature_dir=FEATURE_DIR,
        defect_dir=DEFECT_DIR,
        processed_dir=IDEAS_PROCESSED_DIR,
    )

    try:
        result = subprocess.run(
            [
                "claude",
                "--dangerously-skip-permissions",
                "--permission-mode", "acceptEdits",
                "--output-format", "json",
                "--print", prompt,
            ],
            capture_output=True,
            text=True,
            timeout=IDEA_INTAKE_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            logger.warning(
                "[idea_classifier] Claude exited with code %d for %s",
                result.returncode,
                idea_path,
            )
            return False
    except (subprocess.TimeoutExpired, OSError, subprocess.SubprocessError) as exc:
        logger.warning("[idea_classifier] subprocess error for %s: %s", idea_path, exc)
        return False

    cost_usd = 0.0
    try:
        data = json.loads(result.stdout)
        cost_usd = float(data.get("total_cost_usd", 0.0))
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    add_trace_metadata({
        "node_name": "classify_idea",
        "idea_path": idea_path,
        "total_cost_usd": cost_usd,
    })

    # Verify that the original file was moved to the processed directory.
    basename = Path(idea_path).name
    processed_file = Path(IDEAS_PROCESSED_DIR) / basename
    if not processed_file.exists():
        logger.warning(
            "[idea_classifier] original not found in processed dir after classifying %s",
            idea_path,
        )
        return False

    return True


# ─── Public entry point ───────────────────────────────────────────────────────


def process_ideas(dry_run: bool = False) -> int:
    """Classify all pending idea files and return the count of successes.

    Processes ideas sequentially. On failure, logs a warning and continues so
    the remaining ideas are still attempted in this cycle.
    """
    pending = scan_ideas()
    if not pending:
        return 0

    success_count = 0
    for idea_path in pending:
        ok = classify_idea(idea_path, dry_run=dry_run)
        if ok:
            logger.info("[idea_classifier] classified: %s", idea_path)
            success_count += 1
        else:
            logger.warning("[idea_classifier] failed to classify: %s", idea_path)

    return success_count
