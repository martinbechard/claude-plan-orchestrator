# tests/test_auto_pipeline.py
# Unit tests for auto-pipeline.py helper functions.
# Design ref: docs/plans/2026-02-17-03-noisy-log-output-from-long-plan-filenames-design.md
# Design ref: docs/plans/2026-02-17-6-new-feature-when-modifying-the-code-for-the-auto-pipeline-you-need-to-have-som-design.md
# Design ref: docs/plans/2026-02-18-16-least-privilege-agent-sandboxing-design.md
# Design ref: docs/plans/2026-02-18-17-read-only-analysis-task-workflow-design.md

import importlib.util
import tempfile
import os
import time
from pathlib import Path

# auto-pipeline.py has a hyphen in the filename, so we must use importlib
# to load it as a module under a valid Python identifier.
spec = importlib.util.spec_from_file_location(
    "auto_pipeline", "scripts/auto-pipeline.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

compact_plan_label = mod.compact_plan_label
MAX_LOG_PREFIX_LENGTH = mod.MAX_LOG_PREFIX_LENGTH
PIPELINE_PERMISSION_PROFILES = mod.PIPELINE_PERMISSION_PROFILES
build_permission_flags = mod.build_permission_flags
_compute_file_hash = mod._compute_file_hash
snapshot_source_hashes = mod.snapshot_source_hashes
check_code_changed = mod.check_code_changed
CodeChangeMonitor = mod.CodeChangeMonitor
CODE_CHANGE_POLL_INTERVAL_SECONDS = mod.CODE_CHANGE_POLL_INTERVAL_SECONDS
_perform_restart = mod._perform_restart
_resolve_item_path = mod._resolve_item_path
archive_item = mod.archive_item
BacklogItem = mod.BacklogItem
_open_item_log = mod._open_item_log
_close_item_log = mod._close_item_log
_log_summary = mod._log_summary
LOGS_DIR = mod.LOGS_DIR
SUMMARY_LOG_FILENAME = mod.SUMMARY_LOG_FILENAME
ensure_directories = mod.ensure_directories
ProcessResult = mod.ProcessResult
ANALYSIS_DIR = mod.ANALYSIS_DIR
COMPLETED_ANALYSES_DIR = mod.COMPLETED_ANALYSES_DIR
REPORTS_DIR = mod.REPORTS_DIR
COMPLETED_DIRS = mod.COMPLETED_DIRS
ANALYSIS_TYPE_TO_AGENT = mod.ANALYSIS_TYPE_TO_AGENT
parse_analysis_metadata = mod.parse_analysis_metadata
scan_all_backlogs = mod.scan_all_backlogs


# --- compact_plan_label() tests ---


def test_compact_plan_label_short_filename():
    """Short filenames should have .yaml stripped but no truncation."""
    result = compact_plan_label("03-per-task-validation.yaml")
    assert result == "03-per-task-validation"
    # Should be well within the limit
    assert len(result) <= MAX_LOG_PREFIX_LENGTH


def test_compact_plan_label_long_filename():
    """Long filenames should be truncated to MAX_LOG_PREFIX_LENGTH with ellipsis."""
    input_name = "2-i-want-to-be-able-to-use-separate-slack-channels-depending-on-the-project-by-de.yaml"
    result = compact_plan_label(input_name)

    # Should be exactly MAX_LOG_PREFIX_LENGTH chars
    assert len(result) == MAX_LOG_PREFIX_LENGTH
    # Should end with ellipsis
    assert result.endswith("...")
    # Should start with the beginning of the stem
    assert result.startswith("2-i-want-to-be-able-to-use")


def test_compact_plan_label_exact_limit():
    """Filenames whose stem is exactly MAX_LOG_PREFIX_LENGTH should pass through unchanged."""
    # Create a stem that's exactly MAX_LOG_PREFIX_LENGTH chars (30)
    exact_stem = "a" * MAX_LOG_PREFIX_LENGTH
    input_name = f"{exact_stem}.yaml"
    result = compact_plan_label(input_name)

    # Should pass through unchanged, no truncation or ellipsis
    assert result == exact_stem
    assert len(result) == MAX_LOG_PREFIX_LENGTH
    assert not result.endswith("...")


def test_compact_plan_label_slug_no_extension():
    """Input without .yaml extension should still be truncated correctly."""
    # Use a long slug without .yaml extension
    input_name = "2-i-want-to-be-able-to-use-separate-slack-channels-depending-on-the-project-by-de"
    result = compact_plan_label(input_name)

    # Should be truncated to MAX_LOG_PREFIX_LENGTH
    assert len(result) == MAX_LOG_PREFIX_LENGTH
    assert result.endswith("...")


def test_compact_plan_label_full_path():
    """Full paths should extract basename and strip .yaml extension."""
    result = compact_plan_label(".claude/plans/03-noisy-log.yaml")

    # Should extract just the basename stem
    assert result == "03-noisy-log"
    assert len(result) <= MAX_LOG_PREFIX_LENGTH


# --- Hot-reload detection tests ---


def test_compute_file_hash_returns_consistent_hash():
    """Create a temp file with known content, hash it twice, verify consistency."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
        temp_path = f.name
        f.write("# Test file content\nprint('hello')\n")

    try:
        # Call _compute_file_hash() twice on the same file
        hash1 = _compute_file_hash(temp_path)
        hash2 = _compute_file_hash(temp_path)

        # Assert both calls return the same non-empty string
        assert hash1 == hash2
        assert hash1 != ""

        # Assert the hash is a valid 64-char hex string (SHA-256)
        assert len(hash1) == 64
        assert all(c in '0123456789abcdef' for c in hash1)
    finally:
        os.unlink(temp_path)


def test_compute_file_hash_missing_file():
    """Verify _compute_file_hash returns empty string for missing file."""
    result = _compute_file_hash("/nonexistent/path/file.py")
    assert result == ""


def test_snapshot_source_hashes_captures_existing_files():
    """Create temp files, temporarily set watched files, verify snapshot captures them."""
    # Create two temporary files
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f1:
        temp_file1 = f1.name
        f1.write("# File 1 content\n")

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f2:
        temp_file2 = f2.name
        f2.write("# File 2 content\n")

    try:
        # Temporarily set HOT_RELOAD_WATCHED_FILES to point at temp files
        original_watched = mod.HOT_RELOAD_WATCHED_FILES
        mod.HOT_RELOAD_WATCHED_FILES = [temp_file1, temp_file2]

        try:
            # Call snapshot_source_hashes()
            hashes = snapshot_source_hashes()

            # Assert the returned dict has 2 entries with non-empty hash values
            assert len(hashes) == 2
            assert temp_file1 in hashes
            assert temp_file2 in hashes
            assert hashes[temp_file1] != ""
            assert hashes[temp_file2] != ""
            assert len(hashes[temp_file1]) == 64
            assert len(hashes[temp_file2]) == 64
        finally:
            # Restore original watched files
            mod.HOT_RELOAD_WATCHED_FILES = original_watched
    finally:
        os.unlink(temp_file1)
        os.unlink(temp_file2)


def test_check_code_changed_no_change():
    """Verify check_code_changed returns False when file is unchanged."""
    # Create a temp file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
        temp_file = f.name
        f.write("# Unchanged content\n")

    try:
        # Compute its hash
        file_hash = _compute_file_hash(temp_file)

        # Set _startup_file_hashes to contain this hash
        original_hashes = mod._startup_file_hashes
        mod._startup_file_hashes = {temp_file: file_hash}

        # Temporarily set HOT_RELOAD_WATCHED_FILES to point at it
        original_watched = mod.HOT_RELOAD_WATCHED_FILES
        mod.HOT_RELOAD_WATCHED_FILES = [temp_file]

        try:
            # Call check_code_changed()
            result = check_code_changed()

            # Assert it returns False
            assert result is False
        finally:
            mod.HOT_RELOAD_WATCHED_FILES = original_watched
            mod._startup_file_hashes = original_hashes
    finally:
        os.unlink(temp_file)


def test_check_code_changed_detects_modification():
    """Verify check_code_changed returns True when file content changes."""
    # Create a temp file with initial content
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
        temp_file = f.name
        f.write("# Initial content\n")

    try:
        # Capture its hash in _startup_file_hashes
        initial_hash = _compute_file_hash(temp_file)

        original_hashes = mod._startup_file_hashes
        mod._startup_file_hashes = {temp_file: initial_hash}

        original_watched = mod.HOT_RELOAD_WATCHED_FILES
        mod.HOT_RELOAD_WATCHED_FILES = [temp_file]

        try:
            # Modify the temp file content
            with open(temp_file, 'w') as f:
                f.write("# Modified content\n")

            # Call check_code_changed()
            result = check_code_changed()

            # Assert it returns True
            assert result is True
        finally:
            mod.HOT_RELOAD_WATCHED_FILES = original_watched
            mod._startup_file_hashes = original_hashes
    finally:
        os.unlink(temp_file)


def test_check_code_changed_ignores_missing_startup_hash():
    """Verify check_code_changed returns False when no startup hashes exist."""
    # Set _startup_file_hashes to empty dict
    original_hashes = mod._startup_file_hashes
    mod._startup_file_hashes = {}

    try:
        # Call check_code_changed()
        result = check_code_changed()

        # Assert it returns False (no files to compare)
        assert result is False
    finally:
        mod._startup_file_hashes = original_hashes


# --- CodeChangeMonitor tests ---


def test_code_change_monitor_starts_and_stops():
    """Verify CodeChangeMonitor can start and stop cleanly."""
    # Create a CodeChangeMonitor with short poll interval
    monitor = CodeChangeMonitor(poll_interval=0.1)

    # Start the monitor
    monitor.start()

    # Assert thread is not None and is alive
    assert monitor._thread is not None
    assert monitor._thread.is_alive()

    # Stop the monitor
    monitor.stop()

    # Assert thread is no longer alive (or joined)
    # Give it a moment to finish
    time.sleep(0.3)
    assert not monitor._thread.is_alive()


def test_code_change_monitor_detects_change():
    """Verify CodeChangeMonitor detects file modifications."""
    # Create a temp file with initial content
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
        temp_file = f.name
        f.write("# Initial content\n")

    try:
        # Compute its hash
        file_hash = _compute_file_hash(temp_file)

        # Save original state
        original_hashes = mod._startup_file_hashes
        original_watched = mod.HOT_RELOAD_WATCHED_FILES

        # Set mod._startup_file_hashes to {temp_file: hash}
        mod._startup_file_hashes = {temp_file: file_hash}

        # Set HOT_RELOAD_WATCHED_FILES to [temp_file]
        mod.HOT_RELOAD_WATCHED_FILES = [temp_file]

        try:
            # Create CodeChangeMonitor with short poll interval
            monitor = CodeChangeMonitor(poll_interval=0.1)

            # Start the monitor
            monitor.start()

            # Modify the temp file content
            time.sleep(0.2)  # Let monitor run at least one cycle first
            with open(temp_file, 'w') as f:
                f.write("# Modified content\n")

            # Wait up to 2 seconds for restart_pending to be set
            detected = monitor.restart_pending.wait(timeout=2.0)

            # Assert restart_pending was set
            assert detected is True
            assert monitor.restart_pending.is_set()

            # Stop the monitor
            monitor.stop()
        finally:
            # Restore mod._startup_file_hashes and mod.HOT_RELOAD_WATCHED_FILES
            mod._startup_file_hashes = original_hashes
            mod.HOT_RELOAD_WATCHED_FILES = original_watched
    finally:
        # Clean up temp file
        os.unlink(temp_file)


def test_code_change_monitor_no_change():
    """Verify CodeChangeMonitor does not flag restart when file is unchanged."""
    # Create a temp file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
        temp_file = f.name
        f.write("# Unchanged content\n")

    try:
        # Compute its hash
        file_hash = _compute_file_hash(temp_file)

        # Save original state
        original_hashes = mod._startup_file_hashes
        original_watched = mod.HOT_RELOAD_WATCHED_FILES

        # Set mod._startup_file_hashes to {temp_file: hash}
        mod._startup_file_hashes = {temp_file: file_hash}

        # Set HOT_RELOAD_WATCHED_FILES
        mod.HOT_RELOAD_WATCHED_FILES = [temp_file]

        try:
            # Create CodeChangeMonitor with short poll interval
            monitor = CodeChangeMonitor(poll_interval=0.1)

            # Start the monitor
            monitor.start()

            # Wait 0.5 seconds (several poll cycles)
            time.sleep(0.5)

            # Assert restart_pending is NOT set
            assert monitor.restart_pending.is_set() is False

            # Stop the monitor
            monitor.stop()
        finally:
            # Restore globals
            mod._startup_file_hashes = original_hashes
            mod.HOT_RELOAD_WATCHED_FILES = original_watched
    finally:
        # Clean up temp file
        os.unlink(temp_file)


def test_code_change_monitor_default_interval():
    """Verify CodeChangeMonitor uses default poll interval when none specified."""
    # Create a CodeChangeMonitor with no arguments
    monitor = CodeChangeMonitor()

    # Assert poll_interval == CODE_CHANGE_POLL_INTERVAL_SECONDS
    assert monitor.poll_interval == CODE_CHANGE_POLL_INTERVAL_SECONDS


def test_perform_restart_calls_cleanup_sequence(monkeypatch):
    """Verify _perform_restart performs cleanup before os.execv."""
    from unittest.mock import MagicMock, patch

    # Create mock dependencies
    mock_slack = MagicMock()
    mock_tracker = MagicMock()
    mock_tracker.work_item_costs = []
    mock_observer = MagicMock()
    mock_monitor = MagicMock()

    # Patch os.execv to prevent actual restart
    with patch.object(mod.os, 'execv', side_effect=SystemExit(0)) as mock_execv:
        try:
            _perform_restart(
                "test reason",
                mock_slack,
                mock_tracker,
                mock_observer,
                mock_monitor,
            )
        except SystemExit:
            pass

    # Verify cleanup was called
    mock_slack.send_status.assert_called_once()
    assert "test reason" in mock_slack.send_status.call_args[0][0]
    mock_monitor.stop.assert_called_once()
    mock_slack.stop_background_polling.assert_called_once()
    mock_observer.stop.assert_called_once()
    mock_observer.join.assert_called_once()
    mock_execv.assert_called_once()


# --- _resolve_item_path() tests ---


def test_resolve_item_path_file_at_original_location(tmp_path):
    """File exists at item.path: helper returns item.path unchanged."""
    backlog_dir = tmp_path / "defect-backlog"
    backlog_dir.mkdir()
    item_file = backlog_dir / "my-item.md"
    item_file.write_text("# My Item\n")

    item = BacklogItem(
        path=str(item_file),
        item_type="defect",
        slug="my-item",
        name="My Item",
    )

    assert _resolve_item_path(item) == str(item_file)


def test_resolve_item_path_file_in_completed_subfolder(tmp_path):
    """File has been moved to completed/ subfolder: helper returns new path."""
    backlog_dir = tmp_path / "defect-backlog"
    completed_dir = backlog_dir / "completed"
    completed_dir.mkdir(parents=True)

    item_file_in_completed = completed_dir / "my-item.md"
    item_file_in_completed.write_text("# My Item\n")

    # item.path points to the root (stale path, file no longer there)
    stale_path = str(backlog_dir / "my-item.md")
    item = BacklogItem(
        path=stale_path,
        item_type="defect",
        slug="my-item",
        name="My Item",
    )

    assert _resolve_item_path(item) == str(item_file_in_completed)


def test_resolve_item_path_file_not_found(tmp_path):
    """File missing from both locations: helper returns None."""
    stale_path = str(tmp_path / "defect-backlog" / "ghost-item.md")
    item = BacklogItem(
        path=stale_path,
        item_type="defect",
        slug="ghost-item",
        name="Ghost Item",
    )

    assert _resolve_item_path(item) is None


# --- archive_item() tests ---


def test_archive_item_succeeds_when_file_in_completed_subfolder(tmp_path, monkeypatch):
    """archive_item() resolves relocated file and moves it to archive dir."""
    backlog_dir = tmp_path / "defect-backlog"
    completed_dir = backlog_dir / "completed"
    completed_dir.mkdir(parents=True)

    item_file = completed_dir / "my-item.md"
    item_file.write_text("# My Item\n")

    archive_dir = tmp_path / "completed-backlog" / "defects"
    archive_dir.mkdir(parents=True)

    monkeypatch.setattr(mod, "COMPLETED_DIRS", {"defect": str(archive_dir), "feature": str(archive_dir)})
    monkeypatch.setattr(mod.subprocess, "run", lambda *args, **kwargs: None)

    stale_path = str(backlog_dir / "my-item.md")
    item = BacklogItem(
        path=stale_path,
        item_type="defect",
        slug="my-item",
        name="My Item",
    )

    result = archive_item(item, dry_run=False)

    assert result is True
    assert (archive_dir / "my-item.md").exists()


def test_archive_item_returns_false_when_file_not_found(tmp_path, monkeypatch):
    """archive_item() returns False when file exists at neither location."""
    archive_dir = tmp_path / "completed-backlog" / "defects"
    archive_dir.mkdir(parents=True)

    monkeypatch.setattr(mod, "COMPLETED_DIRS", {"defect": str(archive_dir), "feature": str(archive_dir)})
    monkeypatch.setattr(mod.subprocess, "run", lambda *args, **kwargs: None)

    stale_path = str(tmp_path / "defect-backlog" / "ghost-item.md")
    item = BacklogItem(
        path=stale_path,
        item_type="defect",
        slug="ghost-item",
        name="Ghost Item",
    )

    result = archive_item(item, dry_run=False)

    assert result is False


def test_archive_item_dry_run_does_not_require_file(tmp_path):
    """archive_item() in dry-run mode returns True without touching disk."""
    stale_path = str(tmp_path / "defect-backlog" / "ghost-item.md")
    item = BacklogItem(
        path=stale_path,
        item_type="defect",
        slug="ghost-item",
        name="Ghost Item",
    )

    result = archive_item(item, dry_run=True)

    assert result is True


# --- archive_item() idempotency tests ---


def test_archive_item_idempotent_when_dest_exists(tmp_path, monkeypatch):
    """archive_item() returns True immediately when destination file already exists."""
    archive_dir = tmp_path / "completed-backlog" / "defects"
    archive_dir.mkdir(parents=True)

    # Simulate a previously archived item already present at the destination
    dest_file = archive_dir / "my-item.md"
    dest_file.write_text("# Already archived\n")

    monkeypatch.setattr(mod, "COMPLETED_DIRS", {"defect": str(archive_dir), "feature": str(archive_dir)})

    git_call_count = []

    def track_subprocess_run(*args, **kwargs):
        git_call_count.append(args)

    monkeypatch.setattr(mod.subprocess, "run", track_subprocess_run)

    stale_path = str(tmp_path / "defect-backlog" / "my-item.md")
    item = BacklogItem(
        path=stale_path,
        item_type="defect",
        slug="my-item",
        name="My Item",
    )

    result = archive_item(item, dry_run=False)

    assert result is True
    assert len(git_call_count) == 0, "git should not be called when item is already archived"


def test_archive_item_idempotent_does_not_overwrite(tmp_path, monkeypatch):
    """archive_item() leaves the existing destination file unchanged on re-archive."""
    archive_dir = tmp_path / "completed-backlog" / "defects"
    archive_dir.mkdir(parents=True)

    sentinel = "SENTINEL_CONTENT_UNCHANGED"
    dest_file = archive_dir / "my-item.md"
    dest_file.write_text(sentinel)

    monkeypatch.setattr(mod, "COMPLETED_DIRS", {"defect": str(archive_dir), "feature": str(archive_dir)})
    monkeypatch.setattr(mod.subprocess, "run", lambda *args, **kwargs: None)

    stale_path = str(tmp_path / "defect-backlog" / "my-item.md")
    item = BacklogItem(
        path=stale_path,
        item_type="defect",
        slug="my-item",
        name="My Item",
    )

    archive_item(item, dry_run=False)

    assert dest_file.read_text() == sentinel, "destination file content must not be modified on re-archive"


# --- _resolve_item_path() warning log test ---


def test_resolve_item_path_warning_log_for_completed_subfolder(tmp_path, capsys):
    """_resolve_item_path() emits a WARNING when file is found in the completed/ subfolder."""
    backlog_dir = tmp_path / "defect-backlog"
    completed_dir = backlog_dir / "completed"
    completed_dir.mkdir(parents=True)

    item_file = completed_dir / "item.md"
    item_file.write_text("# Item\n")

    # item.path points to the root (file is not there — it was moved prematurely)
    stale_path = str(backlog_dir / "item.md")
    item = BacklogItem(
        path=stale_path,
        item_type="defect",
        slug="item",
        name="Item",
    )

    _resolve_item_path(item)

    captured = capsys.readouterr()
    assert "WARNING" in captured.out, "Expected WARNING in log output when item is in completed/ subfolder"


# --- Logging infrastructure tests ---


def test_logs_dir_constant():
    """LOGS_DIR and SUMMARY_LOG_FILENAME constants have expected values."""
    assert mod.LOGS_DIR == "logs"
    assert mod.SUMMARY_LOG_FILENAME == "pipeline.log"


def test_open_item_log_creates_file(tmp_path, monkeypatch):
    """_open_item_log() creates the log file with a SESSION START header."""
    monkeypatch.setattr(mod, "LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(mod, "_PIPELINE_PID", 99999)
    (tmp_path / "logs").mkdir()

    _open_item_log("test-slug", "Test Feature", "feature")

    log_file = tmp_path / "logs" / "test-slug.log"
    assert log_file.exists()

    content = log_file.read_text()
    assert "SESSION START" in content
    assert "test-slug" in content
    assert "feature" in content

    _close_item_log("success")
    assert mod._item_log_file is None


def test_close_item_log_writes_footer(tmp_path, monkeypatch):
    """_close_item_log() writes SESSION END footer and releases the file handle."""
    monkeypatch.setattr(mod, "LOGS_DIR", str(tmp_path / "logs"))
    (tmp_path / "logs").mkdir()

    _open_item_log("slug2", "Item", "defect")
    _close_item_log("failed")

    content = (tmp_path / "logs" / "slug2.log").read_text()
    assert "SESSION END" in content
    assert "failed" in content
    assert mod._item_log_file is None


def test_close_item_log_noop_when_not_open():
    """_close_item_log() does not raise when no item log is currently open."""
    # Ensure state is clean (previous tests should have closed)
    assert mod._item_log_file is None
    # Must not raise
    _close_item_log("result")


def test_log_tees_to_item_log_file(tmp_path, monkeypatch):
    """log() output is written to the open item log file as well as stdout."""
    monkeypatch.setattr(mod, "LOGS_DIR", str(tmp_path / "logs"))
    (tmp_path / "logs").mkdir()

    _open_item_log("tee-slug", "Tee Test", "feature")
    mod.log("hello from log")

    content = (tmp_path / "logs" / "tee-slug.log").read_text()
    assert "hello from log" in content

    _close_item_log("success")


def test_log_summary_creates_pipeline_log(tmp_path, monkeypatch):
    """_log_summary() creates pipeline.log and writes a structured summary line."""
    monkeypatch.setattr(mod, "LOGS_DIR", str(tmp_path / "logs"))
    (tmp_path / "logs").mkdir()

    _log_summary("INFO", "STARTED", "my-slug", "type=feature")

    summary_path = tmp_path / "logs" / "pipeline.log"
    assert summary_path.exists()

    content = summary_path.read_text()
    assert "[INFO]" in content
    assert "STARTED" in content
    assert "my-slug" in content
    assert "type=feature" in content


def test_log_summary_appends(tmp_path, monkeypatch):
    """_log_summary() appends multiple entries; both are present in the file."""
    monkeypatch.setattr(mod, "LOGS_DIR", str(tmp_path / "logs"))
    (tmp_path / "logs").mkdir()

    _log_summary("INFO", "STARTED", "slug-a")
    _log_summary("INFO", "COMPLETED", "slug-a")

    content = (tmp_path / "logs" / "pipeline.log").read_text()
    lines = [l for l in content.splitlines() if l.strip()]
    assert len(lines) >= 2
    assert any("STARTED" in l for l in lines)
    assert any("COMPLETED" in l for l in lines)


def test_open_item_log_appends_on_second_run(tmp_path, monkeypatch):
    """_open_item_log() appends to an existing log file on subsequent runs."""
    monkeypatch.setattr(mod, "LOGS_DIR", str(tmp_path / "logs"))
    (tmp_path / "logs").mkdir()

    # First run
    _open_item_log("append-slug", "Item", "feature")
    mod.log("first run message")
    _close_item_log("success")

    # Second run
    _open_item_log("append-slug", "Item", "feature")
    mod.log("second run message")
    _close_item_log("success")

    content = (tmp_path / "logs" / "append-slug.log").read_text()
    assert "first run message" in content
    assert "second run message" in content
    assert content.count("SESSION START") == 2


# --- ensure_directories() tests ---


def test_ensure_directories_creates_missing_dirs(tmp_path, monkeypatch):
    """ensure_directories() creates directories that do not yet exist."""
    dir_a = str(tmp_path / "logs")
    dir_b = str(tmp_path / "docs" / "defect-backlog")
    monkeypatch.setattr(mod, "REQUIRED_DIRS", [dir_a, dir_b])

    ensure_directories()

    assert os.path.isdir(dir_a), f"Expected {dir_a} to be created"
    assert os.path.isdir(dir_b), f"Expected {dir_b} to be created"


def test_ensure_directories_logs_created_dirs(tmp_path, monkeypatch, capsys):
    """ensure_directories() prints [INIT] for each directory it creates."""
    dir_a = str(tmp_path / "logs")
    dir_b = str(tmp_path / "docs" / "defect-backlog")
    monkeypatch.setattr(mod, "REQUIRED_DIRS", [dir_a, dir_b])

    ensure_directories()

    captured = capsys.readouterr()
    assert "[INIT] Created missing directory:" in captured.out
    assert dir_a in captured.out
    assert dir_b in captured.out


def test_ensure_directories_silent_when_dirs_exist(tmp_path, monkeypatch, capsys):
    """ensure_directories() produces no output when all directories already exist."""
    dir_a = str(tmp_path / "logs")
    dir_b = str(tmp_path / "docs" / "defect-backlog")
    os.makedirs(dir_a, exist_ok=True)
    os.makedirs(dir_b, exist_ok=True)
    monkeypatch.setattr(mod, "REQUIRED_DIRS", [dir_a, dir_b])

    ensure_directories()

    captured = capsys.readouterr()
    assert "[INIT]" not in captured.out


# --- scan_ideas() tests ---


def test_scan_ideas_returns_md_files(tmp_path, monkeypatch):
    """scan_ideas() returns paths for non-empty .md files in IDEAS_DIR."""
    ideas_dir = tmp_path / "ideas"
    ideas_dir.mkdir()
    processed_dir = ideas_dir / "processed"
    processed_dir.mkdir()

    (ideas_dir / "idea-one.md").write_text("# Idea One\n")
    (ideas_dir / "idea-two.md").write_text("# Idea Two\n")

    monkeypatch.setattr(mod, "IDEAS_DIR", str(ideas_dir))
    monkeypatch.setattr(mod, "IDEAS_PROCESSED_DIR", str(processed_dir))

    result = mod.scan_ideas()

    result_names = {Path(p).name for p in result}
    assert result_names == {"idea-one.md", "idea-two.md"}


def test_scan_ideas_skips_empty_files(tmp_path, monkeypatch):
    """scan_ideas() skips zero-byte .md files and returns only non-empty ones."""
    ideas_dir = tmp_path / "ideas"
    ideas_dir.mkdir()
    processed_dir = ideas_dir / "processed"
    processed_dir.mkdir()

    (ideas_dir / "empty.md").write_text("")
    (ideas_dir / "nonempty.md").write_text("# Not empty\n")

    monkeypatch.setattr(mod, "IDEAS_DIR", str(ideas_dir))
    monkeypatch.setattr(mod, "IDEAS_PROCESSED_DIR", str(processed_dir))

    result = mod.scan_ideas()

    result_names = {Path(p).name for p in result}
    assert result_names == {"nonempty.md"}
    assert "empty.md" not in result_names


def test_scan_ideas_skips_already_processed(tmp_path, monkeypatch):
    """scan_ideas() omits files whose basename already exists in IDEAS_PROCESSED_DIR."""
    ideas_dir = tmp_path / "ideas"
    ideas_dir.mkdir()
    processed_dir = ideas_dir / "processed"
    processed_dir.mkdir()

    (ideas_dir / "done.md").write_text("# Done\n")
    (ideas_dir / "pending.md").write_text("# Pending\n")
    # Mark 'done.md' as already processed
    (processed_dir / "done.md").write_text("# Done\n")

    monkeypatch.setattr(mod, "IDEAS_DIR", str(ideas_dir))
    monkeypatch.setattr(mod, "IDEAS_PROCESSED_DIR", str(processed_dir))

    result = mod.scan_ideas()

    result_names = {Path(p).name for p in result}
    assert result_names == {"pending.md"}
    assert "done.md" not in result_names


def test_scan_ideas_returns_empty_when_dir_missing(tmp_path, monkeypatch):
    """scan_ideas() returns an empty list when IDEAS_DIR does not exist."""
    nonexistent = str(tmp_path / "does-not-exist")
    monkeypatch.setattr(mod, "IDEAS_DIR", nonexistent)
    monkeypatch.setattr(mod, "IDEAS_PROCESSED_DIR", str(tmp_path / "processed"))

    result = mod.scan_ideas()

    assert result == []


def test_scan_ideas_skips_dotfiles(tmp_path, monkeypatch):
    """scan_ideas() skips hidden (dot-prefixed) files even when they have a .md suffix."""
    ideas_dir = tmp_path / "ideas"
    ideas_dir.mkdir()
    processed_dir = ideas_dir / "processed"
    processed_dir.mkdir()

    (ideas_dir / ".hidden.md").write_text("# Hidden\n")
    (ideas_dir / "normal.md").write_text("# Normal\n")

    monkeypatch.setattr(mod, "IDEAS_DIR", str(ideas_dir))
    monkeypatch.setattr(mod, "IDEAS_PROCESSED_DIR", str(processed_dir))

    result = mod.scan_ideas()

    result_names = {Path(p).name for p in result}
    assert result_names == {"normal.md"}
    assert ".hidden.md" not in result_names


# --- process_idea() tests ---


def test_process_idea_dry_run(tmp_path, monkeypatch):
    """process_idea() in dry-run mode returns True without spawning a subprocess."""
    idea_file = tmp_path / "my-idea.md"
    idea_file.write_text("# My Idea\n")

    called = []

    def mock_run_child_process(*args, **kwargs):
        called.append(args)
        return ProcessResult(success=True, exit_code=0, stdout="", stderr="", duration_seconds=0.1)

    monkeypatch.setattr(mod, "run_child_process", mock_run_child_process)

    result = mod.process_idea(str(idea_file), dry_run=True)

    assert result is True
    assert len(called) == 0, "run_child_process must not be called in dry-run mode"
    assert idea_file.exists(), "Idea file must not be moved in dry-run mode"


def test_process_idea_success(tmp_path, monkeypatch):
    """process_idea() returns True when subprocess succeeds and file is moved to processed/."""
    ideas_dir = tmp_path / "ideas"
    ideas_dir.mkdir()
    processed_dir = ideas_dir / "processed"
    processed_dir.mkdir()

    idea_file = ideas_dir / "my-idea.md"
    idea_file.write_text("# My Idea\n")
    processed_file = processed_dir / "my-idea.md"

    def mock_run_child_process(*args, **kwargs):
        # Simulate the Claude session moving the original to processed/
        processed_file.write_text("# My Idea\n")
        return ProcessResult(success=True, exit_code=0, stdout="", stderr="", duration_seconds=1.0)

    monkeypatch.setattr(mod, "run_child_process", mock_run_child_process)
    monkeypatch.setattr(mod, "IDEAS_PROCESSED_DIR", str(processed_dir))

    result = mod.process_idea(str(idea_file))

    assert result is True


def test_process_idea_rate_limited(tmp_path, monkeypatch):
    """process_idea() returns False when subprocess reports rate limiting."""
    ideas_dir = tmp_path / "ideas"
    ideas_dir.mkdir()
    idea_file = ideas_dir / "my-idea.md"
    idea_file.write_text("# My Idea\n")

    def mock_run_child_process(*args, **kwargs):
        return ProcessResult(
            success=False, exit_code=1, stdout="", stderr="rate limited",
            duration_seconds=0.1, rate_limited=True,
        )

    monkeypatch.setattr(mod, "run_child_process", mock_run_child_process)
    monkeypatch.setattr(mod, "IDEAS_PROCESSED_DIR", str(tmp_path / "processed"))

    result = mod.process_idea(str(idea_file))

    assert result is False


# --- intake_ideas() tests ---


def test_intake_ideas_processes_all(monkeypatch):
    """intake_ideas() calls process_idea() for each idea and returns success count."""
    fake_paths = ["/fake/ideas/idea-one.md", "/fake/ideas/idea-two.md"]
    process_calls = []

    monkeypatch.setattr(mod, "scan_ideas", lambda: fake_paths)

    def mock_process_idea(path, dry_run=False):
        process_calls.append(path)
        return True

    monkeypatch.setattr(mod, "process_idea", mock_process_idea)

    result = mod.intake_ideas(dry_run=False)

    assert result == 2
    assert len(process_calls) == 2
    assert set(process_calls) == set(fake_paths)


def test_intake_ideas_returns_zero_when_no_ideas(monkeypatch):
    """intake_ideas() returns 0 when scan_ideas() finds no files."""
    monkeypatch.setattr(mod, "scan_ideas", lambda: [])

    result = mod.intake_ideas(dry_run=False)

    assert result == 0


# --- Permission profile tests ---


def test_pipeline_permission_profiles_exist():
    """PIPELINE_PERMISSION_PROFILES has planner and verifier keys with required fields."""
    assert "planner" in PIPELINE_PERMISSION_PROFILES
    assert "verifier" in PIPELINE_PERMISSION_PROFILES
    for profile in PIPELINE_PERMISSION_PROFILES.values():
        assert "tools" in profile
        assert "description" in profile


def test_pipeline_build_permission_flags_planner():
    """build_permission_flags('planner') returns allowedTools flags including Write."""
    result = build_permission_flags("planner")

    assert "--allowedTools" in result
    assert "Write" in result
    assert "--add-dir" in result
    assert "--dangerously-skip-permissions" not in result


def test_pipeline_build_permission_flags_verifier():
    """build_permission_flags('verifier') returns allowedTools flags with Bash but not Write."""
    result = build_permission_flags("verifier")

    assert "--allowedTools" in result
    assert "Bash" in result
    assert "Write" not in result
    assert "--dangerously-skip-permissions" not in result


def test_pipeline_build_permission_flags_unknown():
    """build_permission_flags with an unknown profile falls back to --dangerously-skip-permissions."""
    result = build_permission_flags("nonexistent")

    assert result == ["--dangerously-skip-permissions"]


def test_pipeline_build_permission_flags_sandbox_disabled(monkeypatch):
    """When SANDBOX_ENABLED is False, build_permission_flags returns --dangerously-skip-permissions."""
    monkeypatch.setattr(mod, "SANDBOX_ENABLED", False)

    result = build_permission_flags("planner")

    assert result == ["--dangerously-skip-permissions"]


def test_no_dangerously_skip_permissions_in_source():
    """No cmd construction in auto-pipeline uses --dangerously-skip-permissions at call sites."""
    source = Path("scripts/auto-pipeline.py").read_text()
    lines = source.splitlines()
    # Call sites construct commands using CLAUDE_CMD; none should embed the flag directly.
    call_site_violations = [
        line.strip() for line in lines
        if "CLAUDE_CMD" in line and "dangerously-skip-permissions" in line
    ]
    assert call_site_violations == [], (
        f"Found {len(call_site_violations)} call site(s) directly using "
        f"--dangerously-skip-permissions: {call_site_violations}"
    )


# --- Analysis workflow constants and metadata tests ---


def test_analysis_dir_constant_exists():
    """ANALYSIS_DIR, COMPLETED_ANALYSES_DIR, and REPORTS_DIR have expected values."""
    assert ANALYSIS_DIR == "docs/analysis-backlog"
    assert COMPLETED_ANALYSES_DIR == "docs/completed-backlog/analyses"
    assert REPORTS_DIR == "docs/reports"


def test_analysis_in_completed_dirs():
    """COMPLETED_DIRS contains the analysis key mapped to COMPLETED_ANALYSES_DIR."""
    assert "analysis" in COMPLETED_DIRS
    assert COMPLETED_DIRS["analysis"] == COMPLETED_ANALYSES_DIR


def test_analysis_type_to_agent_mapping():
    """ANALYSIS_TYPE_TO_AGENT maps each expected analysis type to the correct agent."""
    assert ANALYSIS_TYPE_TO_AGENT["code-review"] == "code-reviewer"
    assert ANALYSIS_TYPE_TO_AGENT["codebase-analysis"] == "code-explorer"
    assert ANALYSIS_TYPE_TO_AGENT["test-coverage"] == "qa-auditor"
    assert ANALYSIS_TYPE_TO_AGENT["test-results"] == "e2e-analyzer"
    assert ANALYSIS_TYPE_TO_AGENT["spec-compliance"] == "spec-verifier"


def test_parse_analysis_metadata_full(tmp_path):
    """parse_analysis_metadata() extracts all fields from a fully annotated file."""
    md_file = tmp_path / "01-review.md"
    md_file.write_text(
        "# Review\n"
        "## Analysis Type: code-review\n"
        "## Output Format: both\n"
        "## Scope\n"
        "- src/\n"
        "- tests/\n"
        "## Instructions\n"
        "Check for code quality issues.\n"
    )

    result = parse_analysis_metadata(str(md_file))

    assert result["analysis_type"] == "code-review"
    assert result["output_format"] == "both"
    assert "src/" in result["scope"]
    assert "tests/" in result["scope"]
    assert result["instructions"] == "Check for code quality issues."


def test_parse_analysis_metadata_defaults(tmp_path):
    """parse_analysis_metadata() returns defaults when no analysis fields are present."""
    md_file = tmp_path / "01-plain.md"
    md_file.write_text("# Plain File\nNo metadata here.\n")

    result = parse_analysis_metadata(str(md_file))

    assert result["analysis_type"] == ""
    assert result["output_format"] == "both"
    assert result["scope"] == []
    assert result["instructions"] == ""


def test_parse_analysis_metadata_missing_file():
    """parse_analysis_metadata() returns defaults without raising for a missing file."""
    result = parse_analysis_metadata("/nonexistent/file.md")

    assert result["analysis_type"] == ""
    assert result["output_format"] == "both"
    assert result["scope"] == []
    assert result["instructions"] == ""


def test_scan_all_backlogs_includes_analysis(tmp_path, monkeypatch):
    """scan_all_backlogs() includes items from ANALYSIS_DIR with item_type='analysis'."""
    analysis_dir = tmp_path / "analysis-backlog"
    analysis_dir.mkdir()
    defect_dir = tmp_path / "defect-backlog"
    defect_dir.mkdir()
    feature_dir = tmp_path / "feature-backlog"
    feature_dir.mkdir()

    # Create a simple analysis item without completion status
    (analysis_dir / "01-test-analysis.md").write_text(
        "# Test Analysis\n## Analysis Type: code-review\n"
    )

    monkeypatch.setattr(mod, "ANALYSIS_DIR", str(analysis_dir))
    monkeypatch.setattr(mod, "DEFECT_DIR", str(defect_dir))
    monkeypatch.setattr(mod, "FEATURE_DIR", str(feature_dir))

    result = scan_all_backlogs()

    assert len(result) == 1
    assert result[0].item_type == "analysis"
    assert result[0].slug == "01-test-analysis"
