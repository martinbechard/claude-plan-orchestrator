# tests/test_hot_reload.py
# Unit tests for langgraph_pipeline/shared/hot_reload.py.
# Design: docs/plans/2026-03-24-07-hot-reload-on-code-change-detection-design.md

import os
import tempfile
import time

import langgraph_pipeline.shared.hot_reload as hot_reload_mod
from langgraph_pipeline.shared.hot_reload import (
    CODE_CHANGE_POLL_INTERVAL_SECONDS,
    CodeChangeMonitor,
    _compute_file_hash,
    check_code_changed,
    snapshot_source_hashes,
)

# ─── _compute_file_hash tests ─────────────────────────────────────────────────


def test_compute_file_hash_returns_consistent_hash():
    """Verify _compute_file_hash returns the same SHA-256 digest on repeated calls."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
        temp_path = f.name
        f.write("# Test file content\nprint('hello')\n")

    try:
        hash1 = _compute_file_hash(temp_path)
        hash2 = _compute_file_hash(temp_path)

        assert hash1 == hash2
        assert hash1 != ""
        assert len(hash1) == 64
        assert all(c in "0123456789abcdef" for c in hash1)
    finally:
        os.unlink(temp_path)


def test_compute_file_hash_missing_file():
    """Verify _compute_file_hash returns empty string for a missing file."""
    result = _compute_file_hash("/nonexistent/path/file.py")
    assert result == ""


# ─── snapshot_source_hashes tests ─────────────────────────────────────────────


def test_snapshot_source_hashes_captures_existing_files():
    """Verify snapshot_source_hashes returns a hash dict for a known file list."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f1:
        temp_file1 = f1.name
        f1.write("# File 1 content\n")

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f2:
        temp_file2 = f2.name
        f2.write("# File 2 content\n")

    original_watched = hot_reload_mod.HOT_RELOAD_WATCHED_FILES
    hot_reload_mod.HOT_RELOAD_WATCHED_FILES = [temp_file1, temp_file2]

    try:
        hashes = snapshot_source_hashes()

        assert len(hashes) == 2
        assert temp_file1 in hashes
        assert temp_file2 in hashes
        assert len(hashes[temp_file1]) == 64
        assert len(hashes[temp_file2]) == 64
    finally:
        hot_reload_mod.HOT_RELOAD_WATCHED_FILES = original_watched
        os.unlink(temp_file1)
        os.unlink(temp_file2)


# ─── check_code_changed tests ─────────────────────────────────────────────────


def test_check_code_changed_returns_false_when_unchanged():
    """Verify check_code_changed returns False when files are unchanged."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
        temp_file = f.name
        f.write("# Unchanged content\n")

    original_watched = hot_reload_mod.HOT_RELOAD_WATCHED_FILES
    hot_reload_mod.HOT_RELOAD_WATCHED_FILES = [temp_file]

    try:
        baseline = snapshot_source_hashes()
        result = check_code_changed(baseline)
        assert result is False
    finally:
        hot_reload_mod.HOT_RELOAD_WATCHED_FILES = original_watched
        os.unlink(temp_file)


def test_check_code_changed_returns_true_after_modification():
    """Verify check_code_changed returns True after a watched file is modified."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
        temp_file = f.name
        f.write("# Initial content\n")

    original_watched = hot_reload_mod.HOT_RELOAD_WATCHED_FILES
    hot_reload_mod.HOT_RELOAD_WATCHED_FILES = [temp_file]

    try:
        baseline = snapshot_source_hashes()

        with open(temp_file, "w") as f:
            f.write("# Modified content\n")

        result = check_code_changed(baseline)
        assert result is True
    finally:
        hot_reload_mod.HOT_RELOAD_WATCHED_FILES = original_watched
        os.unlink(temp_file)


# ─── CodeChangeMonitor tests ──────────────────────────────────────────────────


def test_code_change_monitor_starts_and_stops_cleanly():
    """Verify CodeChangeMonitor starts as a daemon thread and stops on demand."""
    monitor = CodeChangeMonitor(poll_interval=0.1)

    monitor.start()
    assert monitor.is_alive()
    assert monitor.daemon is True

    monitor.stop()
    monitor.join(timeout=1.0)
    assert not monitor.is_alive()


def test_code_change_monitor_detects_file_modification():
    """Verify CodeChangeMonitor sets restart_pending when a watched file changes."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
        temp_file = f.name
        f.write("# Initial content\n")

    original_watched = hot_reload_mod.HOT_RELOAD_WATCHED_FILES
    hot_reload_mod.HOT_RELOAD_WATCHED_FILES = [temp_file]

    try:
        monitor = CodeChangeMonitor(poll_interval=0.1)
        monitor.start()

        # Let one poll cycle complete before modifying
        time.sleep(0.2)
        with open(temp_file, "w") as f:
            f.write("# Modified content\n")

        detected = monitor.restart_pending.wait(timeout=2.0)

        assert detected is True
        assert monitor.restart_pending.is_set()

        monitor.stop()
    finally:
        hot_reload_mod.HOT_RELOAD_WATCHED_FILES = original_watched
        os.unlink(temp_file)


def test_code_change_monitor_no_change_leaves_restart_pending_clear():
    """Verify CodeChangeMonitor does not set restart_pending when files are unchanged."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
        temp_file = f.name
        f.write("# Unchanged content\n")

    original_watched = hot_reload_mod.HOT_RELOAD_WATCHED_FILES
    hot_reload_mod.HOT_RELOAD_WATCHED_FILES = [temp_file]

    try:
        monitor = CodeChangeMonitor(poll_interval=0.1)
        monitor.start()

        # Several poll cycles with no file changes
        time.sleep(0.5)

        assert monitor.restart_pending.is_set() is False

        monitor.stop()
        monitor.join(timeout=1.0)
    finally:
        hot_reload_mod.HOT_RELOAD_WATCHED_FILES = original_watched
        os.unlink(temp_file)


def test_code_change_monitor_uses_default_poll_interval():
    """Verify CodeChangeMonitor defaults poll_interval to CODE_CHANGE_POLL_INTERVAL_SECONDS."""
    monitor = CodeChangeMonitor()
    assert monitor.poll_interval == CODE_CHANGE_POLL_INTERVAL_SECONDS
