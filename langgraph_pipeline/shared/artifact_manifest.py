# langgraph_pipeline/shared/artifact_manifest.py
# Reads and writes the per-item artifact manifest JSON file.
# Design: docs/plans/2026-03-27-57-track-and-display-item-artifacts-design.md

"""Artifact manifest: records files produced by workers and loads them for display."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from langgraph_pipeline.shared.paths import WORKER_OUTPUT_DIR

# ─── Constants ────────────────────────────────────────────────────────────────

MANIFEST_FILENAME = "artifacts.json"

logger = logging.getLogger(__name__)


# ─── Types ────────────────────────────────────────────────────────────────────


class ArtifactEntry(TypedDict):
    """A single file entry in the artifact manifest."""

    path: str
    action: str
    timestamp: str
    task_id: str


# ─── Public API ───────────────────────────────────────────────────────────────


def record_artifact(slug: str, path: str, action: str, task_id: str) -> None:
    """Append a file entry to the artifact manifest for the given work item slug.

    Creates the manifest file and parent directory if they do not exist.
    action should be "created" or "modified".
    """
    manifest_path = _manifest_path_for(slug)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    entries = _read_raw_manifest(manifest_path)
    entry: ArtifactEntry = {
        "path": path,
        "action": action,
        "timestamp": datetime.now().isoformat(),
        "task_id": task_id,
    }
    entries.append(entry)

    try:
        with open(manifest_path, "w") as f:
            json.dump(entries, f, indent=2)
    except IOError as exc:
        logger.warning(
            "Failed to write artifact manifest %s: %s", manifest_path, exc
        )


def load_manifest(slug: str) -> list[ArtifactEntry]:
    """Load the artifact manifest for the given work item slug.

    Returns an empty list when no manifest exists or the file cannot be read.
    """
    manifest_path = _manifest_path_for(slug)
    return _read_raw_manifest(manifest_path)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _manifest_path_for(slug: str) -> Path:
    """Return the artifact manifest path for the given slug."""
    return WORKER_OUTPUT_DIR / slug / MANIFEST_FILENAME


def _read_raw_manifest(manifest_path: Path) -> list[ArtifactEntry]:
    """Read the manifest JSON file, returning an empty list on any error."""
    if not manifest_path.exists():
        return []
    try:
        with open(manifest_path) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data  # type: ignore[return-value]
        logger.warning("Manifest %s is not a list; ignoring", manifest_path)
        return []
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning(
            "Failed to read artifact manifest %s: %s", manifest_path, exc
        )
        return []
