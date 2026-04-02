# tests/langgraph/shared/test_artifact_cache.py
# Unit tests for the artifact_cache module.

"""Tests for langgraph_pipeline.shared.artifact_cache."""

import json
from pathlib import Path

import pytest

from langgraph_pipeline.shared.artifact_cache import (
    SIDECAR_FILENAME,
    is_artifact_fresh,
    record_artifact,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _sidecar(workspace: Path) -> dict:
    sidecar_path = workspace / SIDECAR_FILENAME
    return json.loads(sidecar_path.read_text())


# ─── record_artifact ─────────────────────────────────────────────────────────


class TestRecordArtifact:
    def test_creates_sidecar_with_hash(self, tmp_path):
        """Should write a sidecar entry with a SHA-256 hash for the input."""
        input_file = tmp_path / "item.md"
        _write(input_file, "hello world")

        record_artifact(tmp_path, "clauses.md", [input_file])

        sidecar = _sidecar(tmp_path)
        assert "clauses.md" in sidecar
        entry = sidecar["clauses.md"]
        assert str(input_file) in entry
        stored_hash = entry[str(input_file)]
        assert len(stored_hash) == 64  # SHA-256 hex digest length
        assert "timestamp" in entry

    def test_records_multiple_inputs(self, tmp_path):
        """Should store a hash for every input file."""
        input_a = tmp_path / "a.md"
        input_b = tmp_path / "b.md"
        _write(input_a, "content A")
        _write(input_b, "content B")

        record_artifact(tmp_path, "requirements.md", [input_a, input_b])

        entry = _sidecar(tmp_path)["requirements.md"]
        assert str(input_a) in entry
        assert str(input_b) in entry
        assert entry[str(input_a)] != entry[str(input_b)]

    def test_updates_existing_entry(self, tmp_path):
        """Re-recording the same output should update the stored hash."""
        input_file = tmp_path / "item.md"
        _write(input_file, "version one")
        record_artifact(tmp_path, "clauses.md", [input_file])
        first_hash = _sidecar(tmp_path)["clauses.md"][str(input_file)]

        _write(input_file, "version two")
        record_artifact(tmp_path, "clauses.md", [input_file])
        second_hash = _sidecar(tmp_path)["clauses.md"][str(input_file)]

        assert first_hash != second_hash

    def test_preserves_other_entries_on_update(self, tmp_path):
        """Re-recording one output should leave other outputs intact."""
        inp_a = tmp_path / "a.md"
        inp_b = tmp_path / "b.md"
        _write(inp_a, "A")
        _write(inp_b, "B")

        record_artifact(tmp_path, "clauses.md", [inp_a])
        record_artifact(tmp_path, "five-whys.md", [inp_b])

        sidecar = _sidecar(tmp_path)
        assert "clauses.md" in sidecar
        assert "five-whys.md" in sidecar

    def test_skips_missing_input_with_warning(self, tmp_path, caplog):
        """A missing input file should be skipped without raising."""
        import logging

        missing = tmp_path / "ghost.md"
        with caplog.at_level(logging.WARNING, logger="langgraph_pipeline.shared.artifact_cache"):
            record_artifact(tmp_path, "clauses.md", [missing])

        assert "does not exist" in caplog.text
        # Entry should still be created but without the missing path
        entry = _sidecar(tmp_path)["clauses.md"]
        assert str(missing) not in entry

    def test_creates_workspace_dir_if_needed(self, tmp_path):
        """Should create missing parent directories for the sidecar."""
        nested_ws = tmp_path / "deep" / "workspace"
        input_file = tmp_path / "item.md"
        _write(input_file, "data")

        record_artifact(nested_ws, "clauses.md", [input_file])

        assert (nested_ws / SIDECAR_FILENAME).exists()


# ─── is_artifact_fresh ────────────────────────────────────────────────────────


class TestIsArtifactFresh:
    def test_fresh_artifact_returns_true(self, tmp_path):
        """Should return True when output exists and input hash matches."""
        input_file = tmp_path / "item.md"
        _write(input_file, "unchanged content")
        output_file = tmp_path / "clauses.md"
        _write(output_file, "clauses output")

        record_artifact(tmp_path, "clauses.md", [input_file])

        assert is_artifact_fresh(tmp_path, "clauses.md", [input_file]) is True

    def test_stale_artifact_returns_false_when_input_changed(self, tmp_path):
        """Should return False when the input file content has changed."""
        input_file = tmp_path / "item.md"
        _write(input_file, "original")
        output_file = tmp_path / "clauses.md"
        _write(output_file, "clauses")

        record_artifact(tmp_path, "clauses.md", [input_file])
        _write(input_file, "modified — staleness detected")

        assert is_artifact_fresh(tmp_path, "clauses.md", [input_file]) is False

    def test_missing_output_returns_false(self, tmp_path):
        """Should return False when the output file does not exist."""
        input_file = tmp_path / "item.md"
        _write(input_file, "content")

        record_artifact(tmp_path, "clauses.md", [input_file])
        # Deliberately do NOT create the output file

        assert is_artifact_fresh(tmp_path, "clauses.md", [input_file]) is False

    def test_missing_sidecar_returns_false(self, tmp_path):
        """Should return False when no sidecar file exists."""
        input_file = tmp_path / "item.md"
        _write(input_file, "content")
        output_file = tmp_path / "clauses.md"
        _write(output_file, "output")

        # No record_artifact call -> no sidecar
        assert is_artifact_fresh(tmp_path, "clauses.md", [input_file]) is False

    def test_missing_sidecar_entry_returns_false(self, tmp_path):
        """Should return False when the sidecar exists but lacks the entry."""
        input_file = tmp_path / "item.md"
        _write(input_file, "content")
        output_file = tmp_path / "clauses.md"
        _write(output_file, "output")

        # Record a *different* output
        record_artifact(tmp_path, "other.md", [input_file])

        assert is_artifact_fresh(tmp_path, "clauses.md", [input_file]) is False

    def test_fresh_with_multiple_inputs(self, tmp_path):
        """Should return True when all multiple inputs match stored hashes."""
        inp_a = tmp_path / "clauses.md"
        inp_b = tmp_path / "five-whys.md"
        _write(inp_a, "clauses content")
        _write(inp_b, "five whys content")
        output_file = tmp_path / "requirements.md"
        _write(output_file, "requirements output")

        record_artifact(tmp_path, "requirements.md", [inp_a, inp_b])

        assert is_artifact_fresh(tmp_path, "requirements.md", [inp_a, inp_b]) is True

    def test_stale_when_one_of_multiple_inputs_changes(self, tmp_path):
        """Should return False when any one of multiple inputs has changed."""
        inp_a = tmp_path / "clauses.md"
        inp_b = tmp_path / "five-whys.md"
        _write(inp_a, "clauses")
        _write(inp_b, "five whys")
        output_file = tmp_path / "requirements.md"
        _write(output_file, "requirements")

        record_artifact(tmp_path, "requirements.md", [inp_a, inp_b])
        _write(inp_b, "five whys — modified")

        assert is_artifact_fresh(tmp_path, "requirements.md", [inp_a, inp_b]) is False

    def test_missing_input_file_returns_false(self, tmp_path):
        """Should return False when a previously recorded input no longer exists."""
        input_file = tmp_path / "item.md"
        _write(input_file, "content")
        output_file = tmp_path / "clauses.md"
        _write(output_file, "output")

        record_artifact(tmp_path, "clauses.md", [input_file])
        input_file.unlink()

        assert is_artifact_fresh(tmp_path, "clauses.md", [input_file]) is False

    def test_re_record_updates_hash_and_restores_freshness(self, tmp_path):
        """After changing an input and re-recording, freshness should return True again."""
        input_file = tmp_path / "item.md"
        _write(input_file, "v1")
        output_file = tmp_path / "clauses.md"
        _write(output_file, "clauses v1")

        record_artifact(tmp_path, "clauses.md", [input_file])
        _write(input_file, "v2")
        _write(output_file, "clauses v2")
        record_artifact(tmp_path, "clauses.md", [input_file])

        assert is_artifact_fresh(tmp_path, "clauses.md", [input_file]) is True

    def test_input_not_in_sidecar_entry_returns_false(self, tmp_path):
        """Should return False when the sidecar entry exists but lacks a specific input."""
        inp_a = tmp_path / "a.md"
        inp_b = tmp_path / "b.md"
        _write(inp_a, "A content")
        _write(inp_b, "B content")
        output_file = tmp_path / "out.md"
        _write(output_file, "output")

        # Record with only inp_a
        record_artifact(tmp_path, "out.md", [inp_a])

        # Check freshness with both — inp_b is not in the entry
        assert is_artifact_fresh(tmp_path, "out.md", [inp_a, inp_b]) is False
