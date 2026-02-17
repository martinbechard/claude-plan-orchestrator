# tests/test_auto_pipeline.py
# Unit tests for compact_plan_label() helper function in auto-pipeline.py.
# Design ref: docs/plans/2026-02-17-03-noisy-log-output-from-long-plan-filenames-design.md

import importlib.util

# auto-pipeline.py has a hyphen in the filename, so we must use importlib
# to load it as a module under a valid Python identifier.
spec = importlib.util.spec_from_file_location(
    "auto_pipeline", "scripts/auto-pipeline.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

compact_plan_label = mod.compact_plan_label
MAX_LOG_PREFIX_LENGTH = mod.MAX_LOG_PREFIX_LENGTH


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
