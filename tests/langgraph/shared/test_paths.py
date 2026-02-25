# tests/langgraph/shared/test_paths.py
# Unit tests for the shared path constants module.
# Design: docs/plans/2026-02-25-02-extract-shared-modules-design.md

"""Unit tests for langgraph_pipeline.shared.paths."""

from pathlib import Path

from langgraph_pipeline.shared.paths import (
    ANALYSIS_DIR,
    BACKLOG_DIRS,
    COMPLETED_ANALYSES_DIR,
    COMPLETED_DEFECTS_DIR,
    COMPLETED_DIRS,
    COMPLETED_FEATURES_DIR,
    DEFECT_DIR,
    FEATURE_DIR,
    ORCHESTRATOR_CONFIG_PATH,
    PID_FILE_PATH,
    PLANS_DIR,
    STATUS_FILE_PATH,
    TASK_LOG_DIR,
)


class TestOrchestatorConfigPath:
    def test_is_string(self):
        assert isinstance(ORCHESTRATOR_CONFIG_PATH, str)

    def test_expected_value(self):
        assert ORCHESTRATOR_CONFIG_PATH == ".claude/orchestrator-config.yaml"


class TestPlansDir:
    def test_is_string(self):
        assert isinstance(PLANS_DIR, str)

    def test_expected_value(self):
        assert PLANS_DIR == ".claude/plans"


class TestStatusFilePath:
    def test_is_string(self):
        assert isinstance(STATUS_FILE_PATH, str)

    def test_under_plans_dir(self):
        assert STATUS_FILE_PATH.startswith(PLANS_DIR)

    def test_expected_value(self):
        assert STATUS_FILE_PATH == ".claude/plans/task-status.json"


class TestTaskLogDir:
    def test_is_path(self):
        assert isinstance(TASK_LOG_DIR, Path)

    def test_under_plans_dir(self):
        assert str(TASK_LOG_DIR).startswith(PLANS_DIR)

    def test_expected_value(self):
        assert TASK_LOG_DIR == Path(".claude/plans/logs")


class TestPidFilePath:
    def test_is_string(self):
        assert isinstance(PID_FILE_PATH, str)

    def test_under_plans_dir(self):
        assert PID_FILE_PATH.startswith(PLANS_DIR)

    def test_expected_value(self):
        assert PID_FILE_PATH == ".claude/plans/.pipeline.pid"


class TestBacklogDirs:
    def test_individual_constants_are_strings(self):
        assert isinstance(DEFECT_DIR, str)
        assert isinstance(FEATURE_DIR, str)
        assert isinstance(ANALYSIS_DIR, str)

    def test_individual_expected_values(self):
        assert DEFECT_DIR == "docs/defect-backlog"
        assert FEATURE_DIR == "docs/feature-backlog"
        assert ANALYSIS_DIR == "docs/analysis-backlog"

    def test_backlog_dirs_has_expected_keys(self):
        assert set(BACKLOG_DIRS.keys()) == {"defect", "feature", "analysis"}

    def test_backlog_dirs_values_match_individual_constants(self):
        assert BACKLOG_DIRS["defect"] == DEFECT_DIR
        assert BACKLOG_DIRS["feature"] == FEATURE_DIR
        assert BACKLOG_DIRS["analysis"] == ANALYSIS_DIR


class TestCompletedDirs:
    def test_individual_constants_are_strings(self):
        assert isinstance(COMPLETED_DEFECTS_DIR, str)
        assert isinstance(COMPLETED_FEATURES_DIR, str)
        assert isinstance(COMPLETED_ANALYSES_DIR, str)

    def test_individual_expected_values(self):
        assert COMPLETED_DEFECTS_DIR == "docs/completed-backlog/defects"
        assert COMPLETED_FEATURES_DIR == "docs/completed-backlog/features"
        assert COMPLETED_ANALYSES_DIR == "docs/completed-backlog/analyses"

    def test_completed_dirs_has_expected_keys(self):
        assert set(COMPLETED_DIRS.keys()) == {"defect", "feature", "analysis"}

    def test_completed_dirs_values_match_individual_constants(self):
        assert COMPLETED_DIRS["defect"] == COMPLETED_DEFECTS_DIR
        assert COMPLETED_DIRS["feature"] == COMPLETED_FEATURES_DIR
        assert COMPLETED_DIRS["analysis"] == COMPLETED_ANALYSES_DIR

    def test_completed_dirs_are_under_completed_backlog(self):
        for path in COMPLETED_DIRS.values():
            assert path.startswith("docs/completed-backlog/")
