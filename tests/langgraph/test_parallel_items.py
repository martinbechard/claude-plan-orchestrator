# tests/langgraph/test_parallel_items.py
# Unit tests for parallel item processing: config helper, claim/unclaim, worker result, supervisor reap.
# Design: docs/plans/2026-03-24-06-parallel-item-processing-supervisor-worker-model-design.md

"""Tests for parallel item processing subsystems.

Covers:
- get_max_parallel_items: default value, explicit value, invalid type fallback.
- claim_item: atomic rename success, race-condition False return, CLAIMED_DIR creation.
- unclaim_item: moves claimed file back to original backlog directory.
- Worker result JSON schema: _write_result produces valid JSON; _read_result_file parses it.
- Supervisor reaping: _reap_one_worker and _reap_finished_workers with mocked os.waitpid.
"""

import json
import os
from unittest.mock import patch

import pytest

from langgraph_pipeline.pipeline.nodes.scan import claim_item, unclaim_item
from langgraph_pipeline.shared.config import DEFAULT_MAX_PARALLEL_ITEMS, get_max_parallel_items
from langgraph_pipeline.supervisor import (
    _read_result_file,
    _reap_finished_workers,
    _reap_one_worker,
)
from langgraph_pipeline.worker import _write_result

# ─── get_max_parallel_items ───────────────────────────────────────────────────


class TestGetMaxParallelItems:
    def test_default_is_one(self):
        assert DEFAULT_MAX_PARALLEL_ITEMS == 1

    def test_default_when_pipeline_key_absent(self):
        assert get_max_parallel_items({}) == DEFAULT_MAX_PARALLEL_ITEMS

    def test_default_when_pipeline_section_missing(self):
        assert get_max_parallel_items({"build_command": "make build"}) == DEFAULT_MAX_PARALLEL_ITEMS

    def test_returns_explicit_positive_integer(self):
        config = {"pipeline": {"max_parallel_items": 4}}
        assert get_max_parallel_items(config) == 4

    def test_falls_back_on_string_value(self):
        config = {"pipeline": {"max_parallel_items": "four"}}
        assert get_max_parallel_items(config) == DEFAULT_MAX_PARALLEL_ITEMS

    def test_falls_back_on_zero(self):
        config = {"pipeline": {"max_parallel_items": 0}}
        assert get_max_parallel_items(config) == DEFAULT_MAX_PARALLEL_ITEMS

    def test_falls_back_on_negative_integer(self):
        config = {"pipeline": {"max_parallel_items": -1}}
        assert get_max_parallel_items(config) == DEFAULT_MAX_PARALLEL_ITEMS

    def test_falls_back_on_float_value(self):
        config = {"pipeline": {"max_parallel_items": 2.5}}
        assert get_max_parallel_items(config) == DEFAULT_MAX_PARALLEL_ITEMS

    def test_returns_one_for_empty_pipeline_section(self):
        config = {"pipeline": {}}
        assert get_max_parallel_items(config) == DEFAULT_MAX_PARALLEL_ITEMS


# ─── claim_item ───────────────────────────────────────────────────────────────


class TestClaimItem:
    def test_success_renames_file_and_returns_true(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod

        claimed_dir = tmp_path / ".claimed"
        monkeypatch.setattr(scan_mod, "CLAIMED_DIR", str(claimed_dir))
        item = tmp_path / "01-bug.md"
        item.write_text("# Bug\n")

        result = claim_item(str(item))

        assert result is True
        assert not item.exists()
        assert (claimed_dir / "01-bug.md").exists()

    def test_race_returns_false_when_file_already_gone(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod

        claimed_dir = tmp_path / ".claimed"
        monkeypatch.setattr(scan_mod, "CLAIMED_DIR", str(claimed_dir))

        result = claim_item(str(tmp_path / "nonexistent.md"))

        assert result is False

    def test_creates_claimed_dir_when_absent(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod

        claimed_dir = tmp_path / ".claimed"
        monkeypatch.setattr(scan_mod, "CLAIMED_DIR", str(claimed_dir))
        item = tmp_path / "02-feat.md"
        item.write_text("# Feature\n")
        assert not claimed_dir.exists()

        claim_item(str(item))

        assert claimed_dir.exists()


# ─── unclaim_item ─────────────────────────────────────────────────────────────


class TestUnclaimItem:
    def test_renames_claimed_file_back_to_original_directory(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod

        claimed_dir = tmp_path / ".claimed"
        claimed_dir.mkdir()
        defect_dir = tmp_path / "defects"
        defect_dir.mkdir()
        monkeypatch.setattr(scan_mod, "BACKLOG_DIRS", {"defect": str(defect_dir)})
        claimed_file = claimed_dir / "01-bug.md"
        claimed_file.write_text("# Bug\n")

        unclaim_item(str(claimed_file), "defect")

        assert not claimed_file.exists()
        assert (defect_dir / "01-bug.md").exists()

    def test_raises_key_error_for_unknown_item_type(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod

        monkeypatch.setattr(scan_mod, "BACKLOG_DIRS", {"defect": "docs/defect-backlog"})
        with pytest.raises(KeyError):
            unclaim_item(str(tmp_path / "01-item.md"), "unknown_type")


# ─── Worker result JSON schema ────────────────────────────────────────────────


class TestWorkerResultJson:
    def test_write_result_produces_parseable_json(self, tmp_path):
        result_file = str(tmp_path / "worker.result.json")

        _write_result(
            result_file,
            success=True,
            item_path="docs/feature-backlog/01-feat.md",
            cost_usd=0.0012,
            input_tokens=100,
            output_tokens=50,
            duration_s=3.5,
            message="Item processed successfully",
        )

        with open(result_file, "r") as f:
            data = json.load(f)
        assert data["success"] is True
        assert data["cost_usd"] == pytest.approx(0.0012)
        assert data["input_tokens"] == 100
        assert data["output_tokens"] == 50
        assert "item_path" in data
        assert "duration_s" in data
        assert "message" in data

    def test_write_result_failure_sets_success_false(self, tmp_path):
        result_file = str(tmp_path / "worker.result.json")

        _write_result(
            result_file,
            success=False,
            item_path="docs/defect-backlog/01-bug.md",
            cost_usd=0.0,
            input_tokens=0,
            output_tokens=0,
            duration_s=1.0,
            message="Unhandled exception: something failed",
        )

        with open(result_file, "r") as f:
            data = json.load(f)
        assert data["success"] is False
        assert data["message"] == "Unhandled exception: something failed"

    def test_read_result_file_parses_valid_json(self, tmp_path):
        result_file = tmp_path / "worker.result.json"
        payload = {
            "success": True,
            "item_path": "docs/feature-backlog/01-feat.md",
            "cost_usd": 0.005,
            "input_tokens": 200,
            "output_tokens": 100,
            "duration_s": 7.2,
            "message": "done",
        }
        result_file.write_text(json.dumps(payload))

        result = _read_result_file(str(result_file))

        assert result is not None
        assert result["success"] is True
        assert result["cost_usd"] == pytest.approx(0.005)

    def test_read_result_file_returns_none_for_missing_file(self, tmp_path):
        result = _read_result_file(str(tmp_path / "no_such_file.json"))
        assert result is None

    def test_read_result_file_returns_none_for_invalid_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{")

        result = _read_result_file(str(bad_file))

        assert result is None


# ─── Supervisor reaping ───────────────────────────────────────────────────────


class TestReapOneWorker:
    """Tests for _reap_one_worker: reads result file and accumulates cost."""

    def _make_result_file(self, tmp_path, *, success: bool, cost_usd: float) -> str:
        result_file = tmp_path / "worker.result.json"
        result_file.write_text(json.dumps({
            "success": success,
            "item_path": "docs/feature-backlog/01-feat.md",
            "cost_usd": cost_usd,
            "input_tokens": 100,
            "output_tokens": 50,
            "duration_s": 2.0,
            "message": "ok" if success else "failed",
        }))
        return str(result_file)

    def test_accumulates_cost_on_success(self, tmp_path):
        result_path = self._make_result_file(tmp_path, success=True, cost_usd=0.0025)
        claimed_dir = tmp_path / ".claimed"
        claimed_dir.mkdir()
        claimed_file = claimed_dir / "01-feat.md"
        claimed_file.write_text("# Feature\n")
        record = (str(claimed_file), result_path, "feature", 0.0)
        cumulative = [0.0]

        budget_exceeded = _reap_one_worker(1234, record, cumulative, None, None)

        assert budget_exceeded is False
        assert cumulative[0] == pytest.approx(0.0025)

    def test_unclaimsitem_on_crash_no_result_file(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod

        claimed_dir = tmp_path / ".claimed"
        claimed_dir.mkdir()
        defect_dir = tmp_path / "defects"
        defect_dir.mkdir()
        monkeypatch.setattr(scan_mod, "BACKLOG_DIRS", {"defect": str(defect_dir)})
        claimed_file = claimed_dir / "01-bug.md"
        claimed_file.write_text("# Bug\n")
        missing_result = str(tmp_path / "missing.json")
        record = (str(claimed_file), missing_result, "defect", 0.0)
        cumulative = [0.0]

        _reap_one_worker(999, record, cumulative, None, None)

        assert not claimed_file.exists()
        assert (defect_dir / "01-bug.md").exists()

    def test_detects_budget_exceeded_after_cost_added(self, tmp_path):
        result_path = self._make_result_file(tmp_path, success=True, cost_usd=5.0)
        claimed_dir = tmp_path / ".claimed"
        claimed_dir.mkdir()
        claimed_file = claimed_dir / "01-feat.md"
        claimed_file.write_text("# Feature\n")
        record = (str(claimed_file), result_path, "feature", 0.0)
        cumulative = [0.0]

        budget_exceeded = _reap_one_worker(1234, record, cumulative, 3.0, None)

        assert budget_exceeded is True
        assert cumulative[0] == pytest.approx(5.0)

    def test_no_budget_exceeded_when_cap_is_none(self, tmp_path):
        result_path = self._make_result_file(tmp_path, success=True, cost_usd=999.0)
        claimed_dir = tmp_path / ".claimed"
        claimed_dir.mkdir()
        claimed_file = claimed_dir / "01-feat.md"
        claimed_file.write_text("# Feature\n")
        record = (str(claimed_file), result_path, "feature", 0.0)
        cumulative = [0.0]

        budget_exceeded = _reap_one_worker(1234, record, cumulative, None, None)

        assert budget_exceeded is False


class TestReapFinishedWorkers:
    """Tests for _reap_finished_workers: non-blocking reap via mocked os.waitpid."""

    def test_reaps_finished_worker_and_accumulates_cost(self, tmp_path):
        result_file = tmp_path / "worker.result.json"
        result_file.write_text(json.dumps({
            "success": True,
            "item_path": "docs/feature-backlog/01-feat.md",
            "cost_usd": 0.01,
            "input_tokens": 200,
            "output_tokens": 100,
            "duration_s": 5.0,
            "message": "done",
        }))
        claimed_dir = tmp_path / ".claimed"
        claimed_dir.mkdir()
        claimed_file = claimed_dir / "01-feat.md"
        claimed_file.write_text("# Feature\n")
        fake_pid = 4242
        active_workers = {
            fake_pid: (str(claimed_file), str(result_file), "feature", 0.0),
        }
        cumulative = [0.0]

        with patch("langgraph_pipeline.supervisor.os.waitpid", return_value=(fake_pid, 0)):
            budget_exceeded = _reap_finished_workers(active_workers, cumulative, None, None)

        assert budget_exceeded is False
        assert cumulative[0] == pytest.approx(0.01)
        assert fake_pid not in active_workers

    def test_worker_still_running_stays_in_active_dict(self, tmp_path):
        fake_pid = 9999
        record = (".claimed/01-feat.md", str(tmp_path / "result.json"), "feature", 0.0)
        active_workers = {fake_pid: record}
        cumulative = [0.0]

        # WNOHANG returns (0, 0) when the process is still running.
        with patch("langgraph_pipeline.supervisor.os.waitpid", return_value=(0, 0)):
            budget_exceeded = _reap_finished_workers(active_workers, cumulative, None, None)

        assert budget_exceeded is False
        assert fake_pid in active_workers
        assert cumulative[0] == 0.0

    def test_already_reaped_pid_is_silently_removed(self, tmp_path):
        fake_pid = 7777
        record = (".claimed/01-feat.md", str(tmp_path / "result.json"), "feature", 0.0)
        active_workers = {fake_pid: record}
        cumulative = [0.0]

        with patch(
            "langgraph_pipeline.supervisor.os.waitpid",
            side_effect=ChildProcessError("already reaped"),
        ):
            budget_exceeded = _reap_finished_workers(active_workers, cumulative, None, None)

        assert budget_exceeded is False
        assert fake_pid not in active_workers
