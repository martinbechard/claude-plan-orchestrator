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
    scan_backlog,
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

    def test_skips_files_without_slug_pattern(self, tmp_path):
        _write_md(tmp_path / "no-number-prefix.md")
        result = _scan_directory(str(tmp_path), "defect")
        assert result == []

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


# ─── _source_item_for_plan ────────────────────────────────────────────────────


class TestSourceItemForPlan:
    def test_returns_source_item_path(self, tmp_path):
        plan = tmp_path / "my-plan.yaml"
        _write_plan(plan, source_item="docs/defect-backlog/01-bug.md")
        assert _source_item_for_plan(str(plan)) == "docs/defect-backlog/01-bug.md"

    def test_returns_none_for_missing_source_item(self, tmp_path):
        plan = tmp_path / "my-plan.yaml"
        _write_plan(plan)
        assert _source_item_for_plan(str(plan)) is None

    def test_returns_none_for_missing_file(self):
        assert _source_item_for_plan("/nonexistent.yaml") is None


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
