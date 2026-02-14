# tests/test_completed_archive.py
# Unit tests for completed_slugs() and archive_item() functions.
# Design ref: docs/plans/2026-02-14-09-move-completed-outside-backlog-design.md

import importlib.util
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

# auto-pipeline.py has a hyphen in the filename, so we must use importlib
# to load it as a module under a valid Python identifier.
spec = importlib.util.spec_from_file_location(
    "auto_pipeline", "scripts/auto-pipeline.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

completed_slugs = mod.completed_slugs
archive_item = mod.archive_item
BacklogItem = mod.BacklogItem


# --- completed_slugs tests ---


def test_completed_slugs_reads_from_new_locations(tmp_path: Path) -> None:
    """completed_slugs() reads .md files from both archive directories."""
    defects_dir = tmp_path / "defects"
    features_dir = tmp_path / "features"
    defects_dir.mkdir()
    features_dir.mkdir()

    # Create sample completed item files
    (defects_dir / "01-login-crash.md").write_text("# Fixed login crash")
    (defects_dir / "02-nav-overflow.md").write_text("# Fixed nav overflow")
    (features_dir / "03-dark-mode.md").write_text("# Dark mode feature")

    with patch.object(mod, "COMPLETED_DEFECTS_DIR", str(defects_dir)), \
         patch.object(mod, "COMPLETED_FEATURES_DIR", str(features_dir)):
        slugs = completed_slugs()

    assert slugs == {"01-login-crash", "02-nav-overflow", "03-dark-mode"}


def test_completed_slugs_empty_when_dirs_missing(tmp_path: Path) -> None:
    """completed_slugs() returns an empty set when archive dirs do not exist."""
    nonexistent_defects = str(tmp_path / "no-such-defects")
    nonexistent_features = str(tmp_path / "no-such-features")

    with patch.object(mod, "COMPLETED_DEFECTS_DIR", nonexistent_defects), \
         patch.object(mod, "COMPLETED_FEATURES_DIR", nonexistent_features):
        slugs = completed_slugs()

    assert slugs == set()


# --- archive_item tests ---


def test_archive_item_defect_goes_to_defects_dir(tmp_path: Path) -> None:
    """archive_item() moves a defect file to the defects archive directory."""
    source_dir = tmp_path / "defect-backlog"
    source_dir.mkdir()
    source_file = source_dir / "05-button-bug.md"
    source_file.write_text("# Button bug")

    dest_defects = tmp_path / "completed" / "defects"
    dest_features = tmp_path / "completed" / "features"

    item = BacklogItem(
        path=str(source_file),
        name="Button Bug",
        slug="05-button-bug",
        item_type="defect",
    )

    patched_dirs = {
        "defect": str(dest_defects),
        "feature": str(dest_features),
    }

    with patch.object(mod, "COMPLETED_DIRS", patched_dirs), \
         patch("subprocess.run"):
        result = archive_item(item)

    assert result is True
    assert not source_file.exists(), "Source file should have been moved"
    assert (dest_defects / "05-button-bug.md").exists(), (
        "File should be in defects archive"
    )


def test_archive_item_feature_goes_to_features_dir(tmp_path: Path) -> None:
    """archive_item() moves a feature file to the features archive directory."""
    source_dir = tmp_path / "feature-backlog"
    source_dir.mkdir()
    source_file = source_dir / "06-search-bar.md"
    source_file.write_text("# Search bar feature")

    dest_defects = tmp_path / "completed" / "defects"
    dest_features = tmp_path / "completed" / "features"

    item = BacklogItem(
        path=str(source_file),
        name="Search Bar",
        slug="06-search-bar",
        item_type="feature",
    )

    patched_dirs = {
        "defect": str(dest_defects),
        "feature": str(dest_features),
    }

    with patch.object(mod, "COMPLETED_DIRS", patched_dirs), \
         patch("subprocess.run"):
        result = archive_item(item)

    assert result is True
    assert not source_file.exists(), "Source file should have been moved"
    assert (dest_features / "06-search-bar.md").exists(), (
        "File should be in features archive"
    )
