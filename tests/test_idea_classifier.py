# tests/test_idea_classifier.py
# Unit tests for the idea_classifier module.
# Design: docs/plans/2026-03-24-ideas-intake-pipeline-design.md

"""Tests for scan_ideas(), classify_idea(), and process_ideas() in idea_classifier."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import langgraph_pipeline.pipeline.nodes.idea_classifier as ic


# ─── scan_ideas ───────────────────────────────────────────────────────────────


def test_scan_ideas_returns_md_files(tmp_path, monkeypatch):
    """Two .md files in IDEAS_DIR are both returned."""
    monkeypatch.setattr(ic, "IDEAS_DIR", str(tmp_path))
    monkeypatch.setattr(ic, "IDEAS_PROCESSED_DIR", str(tmp_path / "processed"))

    (tmp_path / "alpha.md").write_text("content a")
    (tmp_path / "beta.md").write_text("content b")

    result = ic.scan_ideas()

    assert sorted(result) == sorted(
        [str(tmp_path / "alpha.md"), str(tmp_path / "beta.md")]
    )


def test_scan_ideas_skips_empty_files(tmp_path, monkeypatch):
    """Empty .md files are excluded; non-empty files are returned."""
    monkeypatch.setattr(ic, "IDEAS_DIR", str(tmp_path))
    monkeypatch.setattr(ic, "IDEAS_PROCESSED_DIR", str(tmp_path / "processed"))

    (tmp_path / "empty.md").write_text("")
    (tmp_path / "nonempty.md").write_text("some idea")

    result = ic.scan_ideas()

    assert result == [str(tmp_path / "nonempty.md")]


def test_scan_ideas_skips_already_processed(tmp_path, monkeypatch):
    """Files whose basename exists in IDEAS_PROCESSED_DIR are skipped."""
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    monkeypatch.setattr(ic, "IDEAS_DIR", str(tmp_path))
    monkeypatch.setattr(ic, "IDEAS_PROCESSED_DIR", str(processed_dir))

    (tmp_path / "done.md").write_text("already processed")
    (tmp_path / "fresh.md").write_text("new idea")
    (processed_dir / "done.md").write_text("processed copy")

    result = ic.scan_ideas()

    assert result == [str(tmp_path / "fresh.md")]


def test_scan_ideas_returns_empty_when_dir_missing(tmp_path, monkeypatch):
    """Returns [] when IDEAS_DIR does not exist."""
    missing_dir = tmp_path / "nonexistent"
    monkeypatch.setattr(ic, "IDEAS_DIR", str(missing_dir))
    monkeypatch.setattr(ic, "IDEAS_PROCESSED_DIR", str(missing_dir / "processed"))

    result = ic.scan_ideas()

    assert result == []


def test_scan_ideas_skips_dotfiles(tmp_path, monkeypatch):
    """Dotfiles like .hidden.md are skipped; normal files are returned."""
    monkeypatch.setattr(ic, "IDEAS_DIR", str(tmp_path))
    monkeypatch.setattr(ic, "IDEAS_PROCESSED_DIR", str(tmp_path / "processed"))

    (tmp_path / ".hidden.md").write_text("hidden content")
    (tmp_path / "normal.md").write_text("visible content")

    result = ic.scan_ideas()

    assert result == [str(tmp_path / "normal.md")]


# ─── classify_idea ────────────────────────────────────────────────────────────


def test_classify_idea_dry_run():
    """dry_run=True returns True without spawning a subprocess."""
    result = ic.classify_idea("/some/path/idea.md", dry_run=True)
    assert result is True


def test_classify_idea_success(tmp_path, monkeypatch):
    """Returns True when subprocess succeeds and file appears in processed dir."""
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    monkeypatch.setattr(ic, "IDEAS_PROCESSED_DIR", str(processed_dir))

    idea_file = tmp_path / "my-idea.md"
    idea_file.write_text("raw idea")

    # Simulate Claude moving the file to processed/, returning JSON with cost data
    def fake_run(cmd, **kwargs):
        (processed_dir / idea_file.name).write_text("processed")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "done", "total_cost_usd": 0.0234})
        return mock_result

    monkeypatch.setattr(subprocess, "run", fake_run)

    with patch.object(ic, "add_trace_metadata") as mock_trace:
        result = ic.classify_idea(str(idea_file), dry_run=False)

    assert result is True
    mock_trace.assert_called_once()
    call_kwargs = mock_trace.call_args[0][0]
    assert call_kwargs["node_name"] == "classify_idea"
    assert call_kwargs["total_cost_usd"] == pytest.approx(0.0234)


def test_classify_idea_uses_json_output_format(tmp_path, monkeypatch):
    """classify_idea passes --output-format json to the subprocess command."""
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    monkeypatch.setattr(ic, "IDEAS_PROCESSED_DIR", str(processed_dir))

    idea_file = tmp_path / "test-idea.md"
    idea_file.write_text("test idea content")

    captured_cmd: list = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        (processed_dir / idea_file.name).write_text("processed")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "done", "total_cost_usd": 0.0})
        return mock_result

    monkeypatch.setattr(subprocess, "run", fake_run)

    with patch.object(ic, "add_trace_metadata"):
        ic.classify_idea(str(idea_file), dry_run=False)

    assert "--output-format" in captured_cmd
    assert "json" in captured_cmd


def test_classify_idea_handles_invalid_json(tmp_path, monkeypatch):
    """Cost defaults to 0.0 when subprocess output is not valid JSON."""
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    monkeypatch.setattr(ic, "IDEAS_PROCESSED_DIR", str(processed_dir))

    idea_file = tmp_path / "edge-case.md"
    idea_file.write_text("some idea")

    def fake_run(cmd, **kwargs):
        (processed_dir / idea_file.name).write_text("processed")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json at all"
        return mock_result

    monkeypatch.setattr(subprocess, "run", fake_run)

    with patch.object(ic, "add_trace_metadata") as mock_trace:
        result = ic.classify_idea(str(idea_file), dry_run=False)

    assert result is True
    call_kwargs = mock_trace.call_args[0][0]
    assert call_kwargs["total_cost_usd"] == 0.0


def test_classify_idea_subprocess_failure(tmp_path, monkeypatch):
    """Returns False when subprocess exits with non-zero code."""
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    monkeypatch.setattr(ic, "IDEAS_PROCESSED_DIR", str(processed_dir))

    idea_file = tmp_path / "bad-idea.md"
    idea_file.write_text("some idea")

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)

    result = ic.classify_idea(str(idea_file), dry_run=False)

    assert result is False


def test_classify_idea_file_not_moved(tmp_path, monkeypatch):
    """Returns False when subprocess succeeds but file was not moved to processed/."""
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    monkeypatch.setattr(ic, "IDEAS_PROCESSED_DIR", str(processed_dir))

    idea_file = tmp_path / "orphan.md"
    idea_file.write_text("some idea")

    # Subprocess succeeds but does NOT move the file
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps({"result": "done", "total_cost_usd": 0.0})
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)

    with patch.object(ic, "add_trace_metadata"):
        result = ic.classify_idea(str(idea_file), dry_run=False)

    assert result is False


# ─── process_ideas ────────────────────────────────────────────────────────────


def test_process_ideas_no_ideas(monkeypatch):
    """Returns 0 when scan_ideas returns an empty list."""
    monkeypatch.setattr(ic, "scan_ideas", lambda: [])

    result = ic.process_ideas()

    assert result == 0


def test_process_ideas_all_succeed(monkeypatch):
    """Returns 2 when scan finds 2 ideas and classify_idea returns True for both."""
    monkeypatch.setattr(ic, "scan_ideas", lambda: ["/a/idea1.md", "/b/idea2.md"])
    monkeypatch.setattr(ic, "classify_idea", lambda path, dry_run=False: True)

    result = ic.process_ideas()

    assert result == 2


def test_process_ideas_partial_failure(monkeypatch):
    """Returns 1 when classify_idea returns True then False for two ideas."""
    monkeypatch.setattr(ic, "scan_ideas", lambda: ["/a/idea1.md", "/b/idea2.md"])

    call_results = iter([True, False])
    monkeypatch.setattr(
        ic, "classify_idea", lambda path, dry_run=False: next(call_results)
    )

    result = ic.process_ideas()

    assert result == 1
