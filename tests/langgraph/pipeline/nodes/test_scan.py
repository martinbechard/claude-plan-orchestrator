# tests/langgraph/pipeline/nodes/test_scan.py
# Unit tests for the scan_backlog node.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Tests for langgraph_pipeline.pipeline.nodes.scan."""

import textwrap

import pytest
import yaml

from langgraph_pipeline.pipeline.nodes.scan import (
    BACKLOG_SCAN_ORDER,
    SAMPLE_PLAN_FILENAME,
    _find_in_progress_plans,
    _is_item_completed,
    _item_type_from_path,
    _scan_directory,
    _source_item_for_plan,
    claim_item,
    scan_backlog,
    unclaim_item,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _write_md(path, content: str = "# Title\n\n## Status: Open\n") -> None:
    """Write a minimal backlog .md file."""
    path.write_text(content)


def _write_plan(path, *, source_item: str = "", status: str = "pending", has_completed: bool = False) -> None:
    """Write a minimal YAML plan file."""
    tasks = [{"id": "1.1", "name": "Task 1", "status": "completed" if has_completed else "pending"}]
    if has_completed:
        tasks.append({"id": "1.2", "name": "Task 2", "status": "pending"})
    plan = {
        "meta": {
            "name": "Test Plan",
            "source_item": source_item,
            "status": status,
        },
        "sections": [
            {"id": "s1", "name": "Section 1", "tasks": tasks}
        ],
    }
    path.write_text(yaml.dump(plan))


def _make_state(**overrides) -> dict:
    """Build a minimal PipelineState dict."""
    base = {
        "item_path": "",
        "item_slug": "",
        "item_type": "feature",
        "item_name": "",
        "plan_path": None,
        "design_doc_path": None,
        "verification_cycle": 0,
        "verification_history": [],
        "should_stop": False,
        "rate_limited": False,
        "rate_limit_reset": None,
        "session_cost_usd": 0.0,
        "session_input_tokens": 0,
        "session_output_tokens": 0,
        "intake_count_defects": 0,
        "intake_count_features": 0,
    }
    base.update(overrides)
    return base


# ─── _is_item_completed ───────────────────────────────────────────────────────


class TestIsItemCompleted:
    def test_returns_false_for_open_item(self, tmp_path):
        f = tmp_path / "01-bug.md"
        _write_md(f, "## Status: Open\n")
        assert _is_item_completed(str(f)) is False

    def test_returns_true_for_fixed_status(self, tmp_path):
        f = tmp_path / "01-bug.md"
        _write_md(f, "## Status: Fixed\n")
        assert _is_item_completed(str(f)) is True

    def test_returns_true_for_completed_status(self, tmp_path):
        f = tmp_path / "01-feat.md"
        _write_md(f, "## Status: Completed\n")
        assert _is_item_completed(str(f)) is True

    def test_returns_false_for_missing_file(self):
        assert _is_item_completed("/nonexistent/path.md") is False

    def test_case_insensitive_match(self, tmp_path):
        f = tmp_path / "01-bug.md"
        _write_md(f, "## Status: fixed\n")
        assert _is_item_completed(str(f)) is True


# ─── _scan_directory ──────────────────────────────────────────────────────────


class TestScanDirectory:
    def test_returns_empty_for_nonexistent_directory(self, tmp_path):
        result = _scan_directory(str(tmp_path / "missing"), "defect")
        assert result == []

    def test_finds_md_files_matching_slug_pattern(self, tmp_path):
        _write_md(tmp_path / "01-my-bug.md")
        result = _scan_directory(str(tmp_path), "defect")
        assert len(result) == 1
        filepath, slug, item_type = result[0]
        assert slug == "01-my-bug"
        assert item_type == "defect"

    def test_skips_hidden_files(self, tmp_path):
        _write_md(tmp_path / ".hidden.md")
        result = _scan_directory(str(tmp_path), "defect")
        assert result == []

    def test_accepts_prose_slugs_without_number_prefix(self, tmp_path):
        _write_md(tmp_path / "cost-analysis.md")
        result = _scan_directory(str(tmp_path), "defect")
        assert len(result) == 1
        assert result[0][1] == "cost-analysis"

    def test_accepts_single_digit_prefix(self, tmp_path):
        _write_md(tmp_path / "9-my-bug.md")
        result = _scan_directory(str(tmp_path), "defect")
        assert len(result) == 1
        assert result[0][1] == "9-my-bug"

    def test_skips_and_warns_for_slug_with_spaces(self, tmp_path, caplog):
        import logging
        # Create the file via Path.touch since filenames with spaces are valid on the FS.
        bad_file = tmp_path / "has spaces.md"
        bad_file.write_text("# Bad\n\n## Status: Open\n")
        with caplog.at_level(logging.WARNING):
            result = _scan_directory(str(tmp_path), "defect")
        assert result == []
        assert any("has spaces" in r.message for r in caplog.records)

    def test_skips_completed_items(self, tmp_path):
        _write_md(tmp_path / "01-done.md", "## Status: Fixed\n")
        result = _scan_directory(str(tmp_path), "defect")
        assert result == []

    def test_returns_items_sorted_by_filename(self, tmp_path):
        _write_md(tmp_path / "03-third.md")
        _write_md(tmp_path / "01-first.md")
        _write_md(tmp_path / "02-second.md")
        result = _scan_directory(str(tmp_path), "feature")
        slugs = [r[1] for r in result]
        assert slugs == ["01-first", "02-second", "03-third"]


# ─── _find_in_progress_plans ─────────────────────────────────────────────────


class TestFindInProgressPlans:
    def test_returns_empty_when_plans_dir_missing(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path / "missing"))
        result = _find_in_progress_plans()
        assert result == []

    def test_excludes_sample_plan(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path))
        sample = tmp_path / SAMPLE_PLAN_FILENAME
        _write_plan(sample, has_completed=True)
        result = _find_in_progress_plans()
        assert result == []

    def test_detects_in_progress_plan(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path))
        plan = tmp_path / "01-my-feature.yaml"
        _write_plan(plan, has_completed=True)
        result = _find_in_progress_plans()
        assert str(plan) in result

    def test_excludes_all_pending_plan(self, tmp_path, monkeypatch):
        """A plan with only pending tasks is not yet started."""
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path))
        plan = tmp_path / "01-my-feature.yaml"
        _write_plan(plan, has_completed=False)
        result = _find_in_progress_plans()
        assert result == []

    def test_excludes_failed_plan(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path))
        plan = tmp_path / "01-my-feature.yaml"
        _write_plan(plan, status="failed", has_completed=True)
        result = _find_in_progress_plans()
        assert result == []

    def test_detects_plan_with_verified_and_pending_tasks(self, tmp_path, monkeypatch):
        """A plan with verified + pending tasks is in progress."""
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path))
        plan = tmp_path / "01-my-feature.yaml"
        plan_data = {
            "meta": {"name": "Test Plan", "source_item": "", "status": "pending"},
            "sections": [{
                "id": "s1",
                "name": "Section 1",
                "tasks": [
                    {"id": "1.1", "name": "Task 1", "status": "verified"},
                    {"id": "1.2", "name": "Task 2", "status": "pending"},
                ],
            }],
        }
        plan.write_text(yaml.dump(plan_data))
        result = _find_in_progress_plans()
        assert str(plan) in result

    def test_excludes_all_verified_plan(self, tmp_path, monkeypatch):
        """A plan where all tasks are verified (none pending) is fully done."""
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path))
        plan = tmp_path / "01-my-feature.yaml"
        plan_data = {
            "meta": {"name": "Test Plan", "source_item": "", "status": "pending"},
            "sections": [{
                "id": "s1",
                "name": "Section 1",
                "tasks": [
                    {"id": "1.1", "name": "Task 1", "status": "verified"},
                    {"id": "1.2", "name": "Task 2", "status": "verified"},
                ],
            }],
        }
        plan.write_text(yaml.dump(plan_data))
        result = _find_in_progress_plans()
        assert result == []


# ─── _source_item_for_plan ────────────────────────────────────────────────────


class TestSourceItemForPlan:
    def test_returns_source_item_path_when_file_exists(self, tmp_path):
        """Returns the stored source_item path when the file exists on disk."""
        source_file = tmp_path / "01-bug.md"
        _write_md(source_file)
        plan = tmp_path / "my-plan.yaml"
        _write_plan(plan, source_item=str(source_file))
        assert _source_item_for_plan(str(plan)) == str(source_file)

    def test_falls_back_to_backlog_search_when_stored_path_stale(self, tmp_path, monkeypatch):
        """When source_item path is stale (crash recovery), searches backlog dirs by slug."""
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        # Stored path doesn't exist (item was unclaimed back to backlog).
        plan = tmp_path / "01-bug.yaml"
        _write_plan(plan, source_item="/stale/path/.claimed/01-bug.md")
        # Item is in a backlog dir with matching slug.
        defect_dir = tmp_path / "defects"
        defect_dir.mkdir()
        _write_md(defect_dir / "01-bug.md")
        monkeypatch.setattr(scan_mod, "BACKLOG_DIRS", {"defect": str(defect_dir)})
        result = _source_item_for_plan(str(plan))
        assert result == str(defect_dir / "01-bug.md")

    def test_returns_none_when_slug_not_in_any_backlog(self, tmp_path, monkeypatch):
        """Returns None when source_item is stale and slug not found in any backlog dir."""
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        plan = tmp_path / "01-bug.yaml"
        _write_plan(plan, source_item="/stale/path/01-bug.md")
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.setattr(scan_mod, "BACKLOG_DIRS", {"defect": str(empty_dir)})
        assert _source_item_for_plan(str(plan)) is None

    def test_returns_none_for_missing_source_item(self, tmp_path):
        plan = tmp_path / "my-plan.yaml"
        _write_plan(plan)
        assert _source_item_for_plan(str(plan)) is None

    def test_returns_none_for_missing_file(self):
        assert _source_item_for_plan("/nonexistent.yaml") is None


# ─── claim_item / unclaim_item ────────────────────────────────────────────────


class TestClaimItem:
    def test_moves_file_to_claimed_dir_and_returns_true(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        claimed_dir = tmp_path / ".claimed"
        monkeypatch.setattr(scan_mod, "CLAIMED_DIR", str(claimed_dir))
        item = tmp_path / "01-my-bug.md"
        item.write_text("# Bug\n")
        result = claim_item(str(item))
        assert result is True
        assert not item.exists()
        assert (claimed_dir / "01-my-bug.md").exists()

    def test_creates_claimed_dir_when_absent(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        claimed_dir = tmp_path / ".claimed"
        monkeypatch.setattr(scan_mod, "CLAIMED_DIR", str(claimed_dir))
        item = tmp_path / "01-feat.md"
        item.write_text("# Feat\n")
        assert not claimed_dir.exists()
        claim_item(str(item))
        assert claimed_dir.exists()

    def test_returns_false_when_file_already_gone(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        claimed_dir = tmp_path / ".claimed"
        monkeypatch.setattr(scan_mod, "CLAIMED_DIR", str(claimed_dir))
        result = claim_item(str(tmp_path / "nonexistent.md"))
        assert result is False


class TestUnclaimItem:
    def test_moves_file_back_to_backlog_directory(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        claimed_dir = tmp_path / ".claimed"
        claimed_dir.mkdir()
        defect_dir = tmp_path / "defects"
        defect_dir.mkdir()
        monkeypatch.setattr(scan_mod, "CLAIMED_DIR", str(claimed_dir))
        monkeypatch.setattr(scan_mod, "BACKLOG_DIRS", {"defect": str(defect_dir)})
        claimed_file = claimed_dir / "01-my-bug.md"
        claimed_file.write_text("# Bug\n")
        unclaim_item(str(claimed_file), "defect")
        assert not claimed_file.exists()
        assert (defect_dir / "01-my-bug.md").exists()

    def test_raises_key_error_for_unknown_item_type(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        claimed_dir = tmp_path / ".claimed"
        claimed_dir.mkdir()
        monkeypatch.setattr(scan_mod, "CLAIMED_DIR", str(claimed_dir))
        monkeypatch.setattr(scan_mod, "BACKLOG_DIRS", {"defect": "docs/defect-backlog"})
        with pytest.raises(KeyError):
            unclaim_item(str(claimed_dir / "01-item.md"), "unknown")


# ─── _item_type_from_path ─────────────────────────────────────────────────────


class TestItemTypeFromPath:
    def test_defect_path(self):
        assert _item_type_from_path("docs/defect-backlog/01-bug.md") == "defect"

    def test_feature_path(self):
        assert _item_type_from_path("docs/feature-backlog/01-feat.md") == "feature"

    def test_analysis_path(self):
        assert _item_type_from_path("docs/analysis-backlog/01-analysis.md") == "analysis"

    def test_unknown_defaults_to_analysis(self):
        assert _item_type_from_path("docs/other/01-item.md") == "analysis"


# ─── scan_backlog (node) ──────────────────────────────────────────────────────


class TestScanBacklog:
    def test_short_circuits_when_item_path_pre_populated(self, tmp_path, monkeypatch):
        """When item_path is already set (pre-scanned by CLI), scan_backlog returns empty dict."""
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        # Create a defect that would normally be found.
        defect_dir = tmp_path / "defects"
        defect_dir.mkdir()
        _write_md(defect_dir / "01-bug.md")
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path / "plans"))
        monkeypatch.setattr(
            scan_mod, "BACKLOG_SCAN_ORDER",
            [("defect", str(defect_dir))],
        )
        # Pre-populated item_path should cause short-circuit.
        result = scan_backlog(_make_state(item_path="/pre/scanned/item.md"))
        assert result == {}

    def test_returns_empty_path_when_backlog_empty(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path / "plans"))
        monkeypatch.setattr(
            scan_mod, "BACKLOG_SCAN_ORDER",
            [("defect", str(tmp_path / "d")), ("feature", str(tmp_path / "f"))],
        )
        result = scan_backlog(_make_state())
        assert result["item_path"] == ""

    def test_returns_first_defect_when_present(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        defect_dir = tmp_path / "defects"
        defect_dir.mkdir()
        _write_md(defect_dir / "01-my-bug.md")
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path / "plans"))
        monkeypatch.setattr(
            scan_mod, "BACKLOG_SCAN_ORDER",
            [("defect", str(defect_dir)), ("feature", str(tmp_path / "f"))],
        )
        result = scan_backlog(_make_state())
        assert result["item_slug"] == "01-my-bug"
        assert result["item_type"] == "defect"
        assert result["plan_path"] is None

    def test_prioritizes_defects_over_features(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        defect_dir = tmp_path / "defects"
        feature_dir = tmp_path / "features"
        defect_dir.mkdir()
        feature_dir.mkdir()
        _write_md(defect_dir / "01-bug.md")
        _write_md(feature_dir / "01-feat.md")
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path / "plans"))
        monkeypatch.setattr(
            scan_mod, "BACKLOG_SCAN_ORDER",
            [("defect", str(defect_dir)), ("feature", str(feature_dir))],
        )
        result = scan_backlog(_make_state())
        assert result["item_type"] == "defect"

    def test_in_progress_plan_takes_priority(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod

        # Create plans directory with an in-progress plan.
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        # Create the backlog item referenced by the plan.
        defect_dir = tmp_path / "defects"
        defect_dir.mkdir()
        item_file = defect_dir / "01-old-bug.md"
        _write_md(item_file)
        plan_file = plans_dir / "01-old-bug.yaml"
        _write_plan(plan_file, source_item=str(item_file), has_completed=True)

        # Also add a new defect so we can confirm the in-progress plan wins.
        _write_md(defect_dir / "02-new-bug.md")

        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(plans_dir))
        monkeypatch.setattr(
            scan_mod, "BACKLOG_SCAN_ORDER",
            [("defect", str(defect_dir))],
        )
        result = scan_backlog(_make_state())
        assert result["item_slug"] == "01-old-bug"
        assert result["plan_path"] == str(plan_file)

    def test_item_name_is_title_cased_slug(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        feature_dir = tmp_path / "features"
        feature_dir.mkdir()
        _write_md(feature_dir / "03-add-dark-mode.md")
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path / "plans"))
        monkeypatch.setattr(
            scan_mod, "BACKLOG_SCAN_ORDER",
            [("feature", str(feature_dir))],
        )
        result = scan_backlog(_make_state())
        assert result["item_name"] == "03 Add Dark Mode"

    def test_langsmith_root_run_id_is_set_when_tracing_inactive(self, tmp_path, monkeypatch):
        """langsmith_root_run_id is a UUID even when tracing is off (D1: always generate UUID)."""
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        import langgraph_pipeline.shared.langsmith as ls_mod
        defect_dir = tmp_path / "defects"
        defect_dir.mkdir()
        _write_md(defect_dir / "01-bug.md")
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path / "plans"))
        monkeypatch.setattr(
            scan_mod, "BACKLOG_SCAN_ORDER",
            [("defect", str(defect_dir))],
        )
        monkeypatch.setattr(ls_mod, "_tracing_active", False)
        result = scan_backlog(_make_state())
        assert result["langsmith_root_run_id"] is not None

    def test_langsmith_root_run_id_populated_when_tracing_active(self, tmp_path, monkeypatch):
        """langsmith_root_run_id receives a UUID when create_root_run succeeds."""
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        defect_dir = tmp_path / "defects"
        defect_dir.mkdir()
        item = defect_dir / "01-bug.md"
        _write_md(item)
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path / "plans"))
        monkeypatch.setattr(
            scan_mod, "BACKLOG_SCAN_ORDER",
            [("defect", str(defect_dir))],
        )
        fake_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        monkeypatch.setattr(
            scan_mod, "create_root_run",
            lambda slug, path: (object(), fake_id),
        )
        result = scan_backlog(_make_state())
        assert result["langsmith_root_run_id"] == fake_id

    def test_empty_backlog_sets_langsmith_root_run_id_to_none(self, tmp_path, monkeypatch):
        """When the backlog is empty the sentinel dict includes langsmith_root_run_id: None."""
        import langgraph_pipeline.pipeline.nodes.scan as scan_mod
        monkeypatch.setattr(scan_mod, "PLANS_DIR", str(tmp_path / "plans"))
        monkeypatch.setattr(
            scan_mod, "BACKLOG_SCAN_ORDER",
            [("defect", str(tmp_path / "d"))],
        )
        result = scan_backlog(_make_state())
        assert result["item_path"] == ""
        assert result["langsmith_root_run_id"] is None
