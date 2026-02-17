# tests/test_auto_pipeline.py
# Unit tests for auto-pipeline.py helper functions.
# Design ref: docs/plans/2026-02-17-03-noisy-log-output-from-long-plan-filenames-design.md
# Design ref: docs/plans/2026-02-17-6-new-feature-when-modifying-the-code-for-the-auto-pipeline-you-need-to-have-som-design.md

import importlib.util
import tempfile
import os
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
_compute_file_hash = mod._compute_file_hash
snapshot_source_hashes = mod.snapshot_source_hashes
check_code_changed = mod.check_code_changed


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
