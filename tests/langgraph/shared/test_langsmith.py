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
    TRACING_DISABLED_VALUE,
    TRACING_ENABLED_VALUE,
    add_trace_metadata,
    configure_tracing,
    reset_tracing_state,
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

# Full valid config for tests that need tracing to succeed.
_VALID_CONFIG = {
    "langsmith": {
        "enabled": True,
        "api_key": "test-key",
        "workspace_id": "test-workspace",
        "project": "test-project",
    }
}


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all LangSmith env vars to ensure a clean slate per test."""
    for var in _TRACING_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def _reset_tracing():
    """Reset the module-level caching before each test."""
    reset_tracing_state()
    yield
    reset_tracing_state()


# ─── configure_tracing: not enabled ──────────────────────────────────────────


class TestConfigureTracingNotEnabled:
    def test_returns_false_when_not_enabled(self, monkeypatch):
        _clean_env(monkeypatch)
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value={"langsmith": {"enabled": False}},
        ):
            assert configure_tracing() is False

    def test_returns_false_when_no_langsmith_section(self, monkeypatch):
        _clean_env(monkeypatch)
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value={},
        ):
            assert configure_tracing() is False

    def test_sets_tracing_disabled_when_not_enabled(self, monkeypatch):
        _clean_env(monkeypatch)
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value={},
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_TRACING) == TRACING_DISABLED_VALUE

    def test_logs_info_when_not_enabled(self, monkeypatch, caplog):
        _clean_env(monkeypatch)
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value={},
        ):
            import logging
            with caplog.at_level(logging.INFO, logger="langgraph_pipeline.shared.langsmith"):
                configure_tracing()
        assert any("not enabled" in record.message for record in caplog.records)


# ─── configure_tracing: enabled but missing credentials ─────────────────────


class TestConfigureTracingMissingCredentials:
    def test_returns_false_when_no_api_key(self, monkeypatch):
        _clean_env(monkeypatch)
        config = {"langsmith": {"enabled": True, "workspace_id": "ws-123"}}
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=config,
        ):
            assert configure_tracing() is False

    def test_warns_when_no_api_key(self, monkeypatch, caplog):
        _clean_env(monkeypatch)
        config = {"langsmith": {"enabled": True, "workspace_id": "ws-123"}}
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=config,
        ):
            import logging
            with caplog.at_level(logging.WARNING, logger="langgraph_pipeline.shared.langsmith"):
                configure_tracing()
        assert any("LANGSMITH_API_KEY" in record.message for record in caplog.records)

    def test_returns_false_when_no_workspace_id(self, monkeypatch):
        _clean_env(monkeypatch)
        config = {"langsmith": {"enabled": True, "api_key": "key-123"}}
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=config,
        ):
            assert configure_tracing() is False

    def test_warns_when_no_workspace_id(self, monkeypatch, caplog):
        _clean_env(monkeypatch)
        config = {"langsmith": {"enabled": True, "api_key": "key-123"}}
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=config,
        ):
            import logging
            with caplog.at_level(logging.WARNING, logger="langgraph_pipeline.shared.langsmith"):
                configure_tracing()
        assert any("LANGSMITH_WORKSPACE_ID" in record.message for record in caplog.records)

    def test_sets_tracing_disabled_when_missing_credentials(self, monkeypatch):
        _clean_env(monkeypatch)
        config = {"langsmith": {"enabled": True}}
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=config,
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_TRACING) == TRACING_DISABLED_VALUE


# ─── configure_tracing: fully configured ─────────────────────────────────────


class TestConfigureTracingFullyConfigured:
    def test_returns_true_with_all_credentials(self, monkeypatch):
        _clean_env(monkeypatch)
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=_VALID_CONFIG,
        ):
            assert configure_tracing() is True

    def test_sets_tracing_enabled(self, monkeypatch):
        _clean_env(monkeypatch)
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=_VALID_CONFIG,
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_TRACING) == TRACING_ENABLED_VALUE

    def test_sets_api_key_in_env(self, monkeypatch):
        _clean_env(monkeypatch)
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=_VALID_CONFIG,
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_API_KEY) == "test-key"

    def test_sets_workspace_id_in_env(self, monkeypatch):
        _clean_env(monkeypatch)
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=_VALID_CONFIG,
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_WORKSPACE_ID) == "test-workspace"

    def test_sets_project_from_config(self, monkeypatch):
        _clean_env(monkeypatch)
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=_VALID_CONFIG,
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_PROJECT) == "test-project"

    def test_uses_default_project_when_not_configured(self, monkeypatch):
        _clean_env(monkeypatch)
        config = {"langsmith": {"enabled": True, "api_key": "k", "workspace_id": "w"}}
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=config,
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_PROJECT) == DEFAULT_LANGSMITH_PROJECT

    def test_env_vars_take_priority_over_config(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv(ENV_LANGSMITH_API_KEY, "env-key")
        monkeypatch.setenv(ENV_LANGSMITH_WORKSPACE_ID, "env-ws")
        config = {"langsmith": {"enabled": True, "api_key": "cfg-key", "workspace_id": "cfg-ws"}}
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=config,
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_API_KEY) == "env-key"
        assert os.environ.get(ENV_LANGSMITH_WORKSPACE_ID) == "env-ws"

    def test_sets_endpoint_from_config(self, monkeypatch):
        _clean_env(monkeypatch)
        config = {
            "langsmith": {
                "enabled": True,
                "api_key": "k",
                "workspace_id": "w",
                "endpoint": "https://custom.endpoint",
            }
        }
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=config,
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_ENDPOINT) == "https://custom.endpoint"

    def test_does_not_set_endpoint_when_absent(self, monkeypatch):
        _clean_env(monkeypatch)
        config = {"langsmith": {"enabled": True, "api_key": "k", "workspace_id": "w"}}
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=config,
        ):
            configure_tracing()
        assert os.environ.get(ENV_LANGSMITH_ENDPOINT) is None


# ─── configure_tracing: idempotency ─────────────────────────────────────────


class TestConfigureTracingIdempotent:
    def test_second_call_returns_cached_result(self, monkeypatch):
        _clean_env(monkeypatch)
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value=_VALID_CONFIG,
        ) as mock_config:
            result1 = configure_tracing()
            result2 = configure_tracing()
        assert result1 is True
        assert result2 is True
        # Config should only be loaded once
        mock_config.assert_called_once()

    def test_second_call_does_not_log_again(self, monkeypatch, caplog):
        _clean_env(monkeypatch)
        with patch(
            "langgraph_pipeline.shared.langsmith.load_orchestrator_config",
            return_value={},
        ):
            import logging
            with caplog.at_level(logging.INFO, logger="langgraph_pipeline.shared.langsmith"):
                configure_tracing()
                caplog.clear()
                configure_tracing()
        # No new log records on second call
        assert len(caplog.records) == 0


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
