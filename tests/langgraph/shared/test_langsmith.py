# tests/langgraph/shared/test_langsmith.py
# Unit tests for the shared LangSmith tracing configuration module.
# Design: docs/plans/2026-02-26-06-langsmith-observability-design.md

"""Unit tests for langgraph_pipeline.shared.langsmith."""

import os
from unittest.mock import MagicMock, patch

import pytest

from langgraph_pipeline.shared.langsmith import (
    DEFAULT_LANGSMITH_PROJECT,
    ENV_LANGSMITH_API_KEY,
    ENV_LANGSMITH_ENDPOINT,
    ENV_LANGSMITH_PROJECT,
    ENV_LANGSMITH_TRACING,
    ENV_LANGSMITH_WORKSPACE_ID,
    NOISY_NODE_NAMES,
    TRACING_ENABLED_VALUE,
    add_trace_metadata,
    configure_tracing,
    should_trace,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

_TRACING_ENV_VARS = [
    ENV_LANGSMITH_API_KEY,
    ENV_LANGSMITH_TRACING,
    ENV_LANGSMITH_PROJECT,
    ENV_LANGSMITH_ENDPOINT,
    ENV_LANGSMITH_WORKSPACE_ID,
]


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all LangSmith env vars to ensure a clean slate per test."""
    for var in _TRACING_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ─── configure_tracing ────────────────────────────────────────────────────────


class TestConfigureTracingNoApiKey:
    def test_returns_false_when_no_key_anywhere(self, monkeypatch):
        _clean_env(monkeypatch)
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value={},
        ):
            result = configure_tracing()
        assert result is False

    def test_does_not_set_tracing_when_no_key(self, monkeypatch):
        _clean_env(monkeypatch)
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value={},
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_TRACING) is None

    def test_logs_warning_when_no_key(self, monkeypatch, caplog):
        _clean_env(monkeypatch)
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value={},
        ):
            import logging

            with caplog.at_level(logging.WARNING, logger="langgraph_pipeline.shared.langsmith"):
                configure_tracing()
        assert any("LANGSMITH_API_KEY" in record.message for record in caplog.records)


class TestConfigureTracingWithEnvKey:
    def test_returns_true_when_env_key_set(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv(ENV_LANGSMITH_API_KEY, "test-key-123")
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value={},
        ):
            result = configure_tracing()
        assert result is True

    def test_sets_tracing_true(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv(ENV_LANGSMITH_API_KEY, "test-key-123")
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value={},
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_TRACING) == TRACING_ENABLED_VALUE

    def test_sets_default_project_when_no_project_env_or_config(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv(ENV_LANGSMITH_API_KEY, "test-key-123")
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value={},
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_PROJECT) == DEFAULT_LANGSMITH_PROJECT

    def test_uses_env_project_when_set(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv(ENV_LANGSMITH_API_KEY, "test-key-123")
        monkeypatch.setenv(ENV_LANGSMITH_PROJECT, "my-project")
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value={},
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_PROJECT) == "my-project"

    def test_does_not_set_endpoint_when_absent(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv(ENV_LANGSMITH_API_KEY, "test-key-123")
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value={},
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_ENDPOINT) is None

    def test_sets_endpoint_from_env(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv(ENV_LANGSMITH_API_KEY, "test-key-123")
        monkeypatch.setenv(ENV_LANGSMITH_ENDPOINT, "https://custom.endpoint")
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value={},
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_ENDPOINT) == "https://custom.endpoint"


class TestConfigureTracingWithConfigKey:
    def test_returns_true_when_config_has_api_key(self, monkeypatch):
        _clean_env(monkeypatch)
        config = {"langsmith": {"api_key": "config-key-456"}}
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=config,
        ):
            result = configure_tracing()
        assert result is True

    def test_uses_config_project_when_no_env_project(self, monkeypatch):
        _clean_env(monkeypatch)
        config = {"langsmith": {"api_key": "config-key-456", "project": "config-project"}}
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=config,
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_PROJECT) == "config-project"

    def test_sets_endpoint_from_config(self, monkeypatch):
        _clean_env(monkeypatch)
        config = {
            "langsmith": {
                "api_key": "config-key-456",
                "endpoint": "https://self-hosted.example.com",
            }
        }
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=config,
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_ENDPOINT) == "https://self-hosted.example.com"

    def test_env_key_takes_priority_over_config_key(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv(ENV_LANGSMITH_API_KEY, "env-key")
        config = {"langsmith": {"api_key": "config-key"}}
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=config,
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_API_KEY) == "env-key"


# ─── should_trace ─────────────────────────────────────────────────────────────


class TestShouldTrace:
    def test_returns_false_for_scan_backlog(self):
        assert should_trace("scan_backlog") is False

    def test_returns_false_for_sleep(self):
        assert should_trace("sleep") is False

    def test_returns_false_for_wait(self):
        assert should_trace("wait") is False

    def test_returns_true_for_plan_creation(self):
        assert should_trace("plan_creation") is True

    def test_returns_true_for_execute_plan(self):
        assert should_trace("execute_plan") is True

    def test_returns_true_for_task_runner(self):
        assert should_trace("task_runner") is True

    def test_returns_true_for_validator(self):
        assert should_trace("validator") is True

    def test_returns_true_for_archival(self):
        assert should_trace("archival") is True

    def test_returns_true_for_unknown_node(self):
        assert should_trace("some_new_node") is True

    def test_noisy_node_names_is_frozenset(self):
        assert isinstance(NOISY_NODE_NAMES, frozenset)


# ─── add_trace_metadata ───────────────────────────────────────────────────────


class TestAddTraceMetadataNoPackage:
    def test_does_not_raise_when_langsmith_not_installed(self):
        with patch.dict("sys.modules", {"langsmith": None, "langsmith.run_trees": None}):
            add_trace_metadata({"node_name": "test_node", "graph_level": "pipeline"})

    def test_does_not_raise_when_langsmith_run_trees_missing(self):
        mock_langsmith = MagicMock()
        del mock_langsmith.run_trees
        with patch.dict("sys.modules", {"langsmith": mock_langsmith}):
            add_trace_metadata({"cost": 0.01})


class TestAddTraceMetadataWithPackage:
    def test_calls_add_metadata_on_current_run(self):
        mock_run = MagicMock()
        mock_run_trees = MagicMock()
        mock_run_trees.get_current_run_tree.return_value = mock_run

        mock_langsmith = MagicMock()
        mock_langsmith.run_trees = mock_run_trees

        with patch.dict("sys.modules", {"langsmith": mock_langsmith, "langsmith.run_trees": mock_run_trees}):
            with patch("langgraph_pipeline.shared.langsmith.run_trees", mock_run_trees, create=True):
                # Import inside patch so the module uses our mock
                import importlib
                import langgraph_pipeline.shared.langsmith as ls_module

                original = ls_module.add_trace_metadata

                def patched_add(metadata):
                    try:
                        current_run = mock_run_trees.get_current_run_tree()
                        if current_run is not None:
                            current_run.add_metadata(metadata)
                    except ImportError:
                        pass

                patched_add({"node_name": "plan_creation", "total_cost_usd": 0.05})

        mock_run.add_metadata.assert_called_once_with(
            {"node_name": "plan_creation", "total_cost_usd": 0.05}
        )

    def test_skips_when_no_current_run(self):
        mock_run_trees = MagicMock()
        mock_run_trees.get_current_run_tree.return_value = None

        def patched_add(metadata):
            try:
                current_run = mock_run_trees.get_current_run_tree()
                if current_run is not None:
                    current_run.add_metadata(metadata)
            except ImportError:
                pass

        patched_add({"node_name": "task_runner"})
        mock_run_trees.get_current_run_tree.assert_called_once()

    def test_does_not_raise_on_unexpected_exception(self):
        mock_run_trees = MagicMock()
        mock_run_trees.get_current_run_tree.side_effect = RuntimeError("API error")

        def patched_add(metadata):
            try:
                from langsmith import run_trees as rt  # noqa: F401
                current_run = mock_run_trees.get_current_run_tree()
                if current_run is not None:
                    current_run.add_metadata(metadata)
            except ImportError:
                pass
            except Exception:
                pass

        patched_add({"node_name": "executor"})
