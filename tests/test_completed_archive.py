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
scan_directory = mod.scan_directory
scan_all_backlogs = mod.scan_all_backlogs
parse_dependencies = mod.parse_dependencies
BacklogItem = mod.BacklogItem
process_item = mod.process_item
_mark_as_verification_exhausted = mod._mark_as_verification_exhausted
VERIFICATION_EXHAUSTED_STATUS = mod.VERIFICATION_EXHAUSTED_STATUS
count_verification_attempts = mod.count_verification_attempts
MAX_VERIFICATION_CYCLES = mod.MAX_VERIFICATION_CYCLES
is_item_completed = mod.is_item_completed
COMPLETED_DEFECTS_DIR = mod.COMPLETED_DEFECTS_DIR
COMPLETED_FEATURES_DIR = mod.COMPLETED_FEATURES_DIR
DEFECT_DIR = mod.DEFECT_DIR


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


# --- scan_all_backlogs lazy dependency resolution tests ---


def test_scan_all_backlogs_skips_completed_slugs_when_no_deps() -> None:
    """scan_all_backlogs() does NOT call completed_slugs() when no items have dependencies."""
    item = BacklogItem(
        path="/fake/path/01-test-item.md",
        name="Test Item",
        slug="01-test-item",
        item_type="defect",
    )

    from unittest.mock import Mock
    mock_completed_slugs = Mock()

    # scan_directory is called three times (defects, features, analysis)
    # Return [item] for defects, [] for features, [] for analysis
    with patch.object(mod, "scan_directory", side_effect=[[item], [], []]), \
         patch.object(mod, "parse_dependencies", return_value=[]), \
         patch.object(mod, "completed_slugs", mock_completed_slugs):
        result = scan_all_backlogs()

    mock_completed_slugs.assert_not_called()
    assert len(result) == 1
    assert result[0].slug == "01-test-item"


def test_scan_all_backlogs_calls_completed_slugs_when_deps_exist() -> None:
    """scan_all_backlogs() DOES call completed_slugs() when at least one item has dependencies."""
    item = BacklogItem(
        path="/fake/path/02-test-item.md",
        name="Test Item With Dep",
        slug="02-test-item",
        item_type="defect",
    )

    from unittest.mock import Mock
    mock_completed_slugs = Mock(return_value={"01-some-dep"})

    # scan_directory is called three times (defects, features, analysis)
    # Return [item] for defects, [] for features, [] for analysis
    with patch.object(mod, "scan_directory", side_effect=[[item], [], []]), \
         patch.object(mod, "parse_dependencies", return_value=["01-some-dep"]), \
         patch.object(mod, "completed_slugs", mock_completed_slugs):
        result = scan_all_backlogs()

    mock_completed_slugs.assert_called_once()
    assert len(result) == 1
    assert result[0].slug == "02-test-item"


def test_scan_all_backlogs_filters_unsatisfied_deps() -> None:
    """scan_all_backlogs() filters out items with unsatisfied dependencies."""
    item = BacklogItem(
        path="/fake/path/03-test-item.md",
        name="Test Item Blocked",
        slug="03-test-item",
        item_type="defect",
    )

    # scan_directory is called three times (defects, features, analysis)
    # Return [item] for defects, [] for features, [] for analysis
    with patch.object(mod, "scan_directory", side_effect=[[item], [], []]), \
         patch.object(mod, "parse_dependencies", return_value=["99-not-done"]), \
         patch.object(mod, "completed_slugs", return_value=set()):
        result = scan_all_backlogs()

    assert len(result) == 0


# --- _mark_as_verification_exhausted tests ---


def test_mark_as_verification_exhausted_updates_status(tmp_path: Path) -> None:
    """_mark_as_verification_exhausted() replaces Status: Open with VERIFICATION_EXHAUSTED_STATUS."""
    temp_file = tmp_path / "test-defect.md"
    temp_file.write_text(
        "# Test Defect\n\n## Status: Open\n\nSome content here.\n"
    )

    _mark_as_verification_exhausted(str(temp_file))

    content = temp_file.read_text()
    assert "## Status: Open" not in content
    assert f"## Status: {VERIFICATION_EXHAUSTED_STATUS}" in content


def test_mark_as_verification_exhausted_handles_missing_file(tmp_path: Path) -> None:
    """_mark_as_verification_exhausted() handles missing files gracefully (no exception)."""
    nonexistent = tmp_path / "nonexistent.md"
    # Should not raise an exception
    _mark_as_verification_exhausted(str(nonexistent))


def test_mark_as_verification_exhausted_no_status_line(tmp_path: Path) -> None:
    """_mark_as_verification_exhausted() leaves file unchanged if no Status: Open line exists."""
    temp_file = tmp_path / "test-defect-no-status.md"
    original_content = "# Test Defect\n\nNo status line here.\n"
    temp_file.write_text(original_content)

    _mark_as_verification_exhausted(str(temp_file))

    content = temp_file.read_text()
    assert content == original_content


def test_process_item_archives_when_max_cycles_reached(tmp_path: Path) -> None:
    """process_item() archives defect when max verification cycles already reached."""
    # Create a defect file with 3 failed verification attempts
    defect_file = tmp_path / "04-test-defect.md"
    defect_content = """# Test Defect

## Status: Open

## Verification Log

### Verification #1
**Date:** 2026-01-01
**Verdict: FAIL**
Failed due to X

### Verification #2
**Date:** 2026-01-02
**Verdict: FAIL**
Failed due to Y

### Verification #3
**Date:** 2026-01-03
**Verdict: FAIL**
Failed due to Z
"""
    defect_file.write_text(defect_content)

    item = BacklogItem(
        path=str(defect_file),
        name="Test Defect",
        slug="04-test-defect",
        item_type="defect",
    )

    # Mock SlackNotifier
    from unittest.mock import Mock
    mock_slack = Mock()
    mock_slack.send_status = Mock()

    # Mock archive_item to return True
    mock_archive = Mock(return_value=True)

    # Save the original function before patching
    original_mark_fn = mod._mark_as_verification_exhausted

    # Track calls to _mark_as_verification_exhausted
    mark_calls = []
    def track_mark(path: str) -> None:
        mark_calls.append(path)
        # Call the original function to actually update the file
        original_mark_fn(path)

    with patch.object(mod, "SlackNotifier", return_value=mock_slack), \
         patch.object(mod, "archive_item", mock_archive), \
         patch.object(mod, "_mark_as_verification_exhausted", side_effect=track_mark), \
         patch.object(mod, "PLANS_DIR", str(tmp_path / "plans")):
        result = process_item(item, dry_run=False)

    # Verify _mark_as_verification_exhausted was called
    assert len(mark_calls) == 1
    assert mark_calls[0] == str(defect_file)

    # Verify archive_item was called
    mock_archive.assert_called_once()

    # Verify process_item returned False (verification exhausted)
    assert result is False

    # Verify Slack notification was sent
    assert mock_slack.send_status.call_count >= 2  # initial + verification exhausted

    # Verify status was updated in the file
    content = defect_file.read_text()
    assert f"## Status: {VERIFICATION_EXHAUSTED_STATUS}" in content
    assert "## Status: Open" not in content


# --- scan_directory auto-archive regression tests ---


def test_scan_directory_auto_archives_completed_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """scan_directory() calls archive_item() for completed items and does not queue them."""
    defect_dir = tmp_path / "defect-backlog"
    defect_dir.mkdir()

    md = defect_dir / "my-completed-defect.md"
    md.write_text("## Status: Completed\n\nSome content.\n")

    archived: list[BacklogItem] = []

    def fake_archive(item: BacklogItem, dry_run: bool = False) -> bool:
        archived.append(item)
        return True

    monkeypatch.setattr(mod, "archive_item", fake_archive)

    result = mod.scan_directory(str(defect_dir), "defect")

    assert result == []
    assert len(archived) == 1
    assert archived[0].slug == "my-completed-defect"
    assert archived[0].item_type == "defect"


def test_scan_directory_warns_on_archive_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """scan_directory() logs a WARNING when archive_item() returns False."""
    defect_dir = tmp_path / "defect-backlog"
    defect_dir.mkdir()

    md = defect_dir / "my-completed-defect.md"
    md.write_text("## Status: Completed\n\nSome content.\n")

    monkeypatch.setattr(mod, "archive_item", lambda item, dry_run=False: False)

    result = mod.scan_directory(str(defect_dir), "defect")

    captured = capsys.readouterr()
    assert result == []
    assert "WARNING" in captured.out


def test_scan_directory_includes_incomplete_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """scan_directory() returns non-completed items normally and never calls archive_item()."""
    defect_dir = tmp_path / "defect-backlog"
    defect_dir.mkdir()

    md = defect_dir / "my-open-defect.md"
    md.write_text("## Status: Open\n\nContent.\n")

    archive_calls: list[BacklogItem] = []

    def fake_archive(item: BacklogItem, dry_run: bool = False) -> bool:
        archive_calls.append(item)
        return True

    monkeypatch.setattr(mod, "archive_item", fake_archive)

    result = mod.scan_directory(str(defect_dir), "defect")

    assert len(result) == 1
    assert result[0].slug == "my-open-defect"
    assert archive_calls == []
