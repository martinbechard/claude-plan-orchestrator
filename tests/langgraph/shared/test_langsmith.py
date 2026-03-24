# tests/langgraph/shared/test_langsmith.py
# Unit tests for the shared LangSmith tracing configuration module.
# Design: docs/plans/2026-02-26-06-langsmith-observability-design.md

"""Unit tests for langgraph_pipeline.shared.langsmith."""

import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, call, patch

import pytest

from langgraph_pipeline.shared.claude_cli import ToolCallRecord
from langgraph_pipeline.shared.langsmith import (
    DEFAULT_LANGSMITH_PROJECT,
    ENV_LANGSMITH_API_KEY,
    ENV_LANGSMITH_ENDPOINT,
    ENV_LANGSMITH_PROJECT,
    ENV_LANGSMITH_TRACING,
    ENV_LANGSMITH_WORKSPACE_ID,
    LANGSMITH_TRACE_LINE_PREFIX,
    LANGSMITH_TRACE_PATTERN,
    NOISY_NODE_NAMES,
    TRACING_DISABLED_VALUE,
    TRACING_ENABLED_VALUE,
    add_trace_metadata,
    configure_tracing,
    create_root_run,
    emit_tool_call_traces,
    finalize_root_run,
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


# ─── emit_tool_call_traces ───────────────────────────────────────────────────


def _make_tool_call(
    record_type: str = "tool_use",
    tool_name: str = "Read",
    tool_input: dict | None = None,
    timestamp: str = "12:00:00",
    start_time: datetime | None = None,
    duration_s: float | None = None,
) -> ToolCallRecord:
    record = ToolCallRecord(
        type=record_type,  # type: ignore[arg-type]
        tool_name=tool_name,
        tool_input=tool_input or {"file_path": "/a.py"},
        timestamp=timestamp,
    )
    if start_time is not None:
        record["start_time"] = start_time
    if duration_s is not None:
        record["duration_s"] = duration_s
    return record


class TestEmitToolCallTracesWhenInactive:
    def test_does_not_raise_when_tracing_inactive(self, monkeypatch):
        _clean_env(monkeypatch)
        with patch("langgraph_pipeline.shared.langsmith.load_orchestrator_config", return_value={}):
            configure_tracing()  # _tracing_active = False
        emit_tool_call_traces([_make_tool_call()], "task:1.1", {"task_id": "1.1"})

    def test_does_nothing_when_tool_calls_empty(self, monkeypatch):
        _clean_env(monkeypatch)
        with patch("langgraph_pipeline.shared.langsmith.load_orchestrator_config", return_value=_VALID_CONFIG):
            configure_tracing()
        emit_tool_call_traces([], "task:1.1", {"task_id": "1.1"})


class TestEmitToolCallTracesWithMockedLangSmith:
    def _set_tracing_active(self, monkeypatch):
        """Force _tracing_active to True without needing valid credentials."""
        import langgraph_pipeline.shared.langsmith as ls_mod
        monkeypatch.setattr(ls_mod, "_tracing_active", True)
        monkeypatch.setattr(ls_mod, "_tracing_configured", True)

    def test_creates_child_run_for_each_tool_call(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        mock_child = MagicMock()
        mock_parent = MagicMock(spec=["create_child", "end", "post"])
        mock_parent.create_child.return_value = mock_child

        records = [
            _make_tool_call("tool_use", "Bash", {"command": "ls"}),
            _make_tool_call("tool_use", "Read", {"file_path": "/x.py"}),
        ]
        with patch("langsmith.RunTree", return_value=mock_parent):
            emit_tool_call_traces(records, "task:1.1", {"task_id": "1.1"})

        assert mock_parent.create_child.call_count == 2
        assert mock_child.end.call_count == 2
        assert mock_child.post.call_count == 2
        mock_parent.end.assert_called_once()
        mock_parent.post.assert_called_once()

    def test_tool_use_run_type_is_tool(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        mock_child = MagicMock()
        mock_parent = MagicMock(spec=["create_child", "end", "post"])
        mock_parent.create_child.return_value = mock_child

        records = [_make_tool_call("tool_use", "Bash", {"command": "ls"})]
        with patch("langsmith.RunTree", return_value=mock_parent):
            emit_tool_call_traces(records, "task:1.1", {})

        call_kwargs = mock_parent.create_child.call_args.kwargs
        assert call_kwargs["run_type"] == "tool"
        assert call_kwargs["name"] == "Bash"

    def test_text_record_run_type_is_llm(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        mock_child = MagicMock()
        mock_parent = MagicMock(spec=["create_child", "end", "post"])
        mock_parent.create_child.return_value = mock_child

        records = [_make_tool_call("text", "", {"text": "Hello"})]
        with patch("langsmith.RunTree", return_value=mock_parent):
            emit_tool_call_traces(records, "task:1.1", {})

        call_kwargs = mock_parent.create_child.call_args.kwargs
        assert call_kwargs["run_type"] == "llm"
        assert call_kwargs["name"] == "assistant_text"

    def test_metadata_attached_to_each_child_extra(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        mock_child = MagicMock()
        mock_parent = MagicMock(spec=["create_child", "end", "post"])
        mock_parent.create_child.return_value = mock_child

        records = [_make_tool_call("tool_use", "Glob", {"pattern": "*.py"}, "13:00:00")]
        with patch("langsmith.RunTree", return_value=mock_parent):
            emit_tool_call_traces(records, "task:1.1", {"task_id": "1.1", "model": "sonnet"})

        extra = mock_parent.create_child.call_args.kwargs["extra"]
        assert extra["metadata"]["task_id"] == "1.1"
        assert extra["metadata"]["model"] == "sonnet"
        assert extra["metadata"]["timestamp"] == "13:00:00"

    def test_does_not_raise_when_langsmith_import_fails(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        import sys
        prev = sys.modules.get("langsmith")
        sys.modules["langsmith"] = None  # type: ignore[assignment]
        try:
            emit_tool_call_traces([_make_tool_call()], "task:1.1", {})
        finally:
            if prev is None:
                sys.modules.pop("langsmith", None)
            else:
                sys.modules["langsmith"] = prev

    def test_parent_run_name_and_type(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        mock_parent = MagicMock(spec=["create_child", "end", "post"])
        mock_parent.create_child.return_value = MagicMock()

        records = [_make_tool_call()]
        with patch("langsmith.RunTree", return_value=mock_parent) as mock_cls:
            emit_tool_call_traces(records, "task:1.1", {"task_id": "1.1"})

        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["name"] == "task:1.1"
        assert call_kwargs["run_type"] == "chain"

    def test_end_time_passed_when_duration_s_set(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        mock_child = MagicMock()
        mock_parent = MagicMock(spec=["create_child", "end", "post"])
        mock_parent.create_child.return_value = mock_child

        fixed_start = datetime(2026, 3, 24, 12, 0, 0)
        records = [_make_tool_call("tool_use", "Bash", {"command": "ls"}, start_time=fixed_start, duration_s=5.0)]
        with patch("langsmith.RunTree", return_value=mock_parent):
            emit_tool_call_traces(records, "task:2.1", {})

        expected_end = fixed_start + timedelta(seconds=5.0)
        mock_child.end.assert_called_once_with(outputs={"command": "ls"}, end_time=expected_end)

    def test_end_time_absent_when_duration_s_not_set(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        mock_child = MagicMock()
        mock_parent = MagicMock(spec=["create_child", "end", "post"])
        mock_parent.create_child.return_value = mock_child

        records = [_make_tool_call("tool_use", "Read", {"file_path": "/x.py"})]
        with patch("langsmith.RunTree", return_value=mock_parent):
            emit_tool_call_traces(records, "task:2.1", {})

        mock_child.end.assert_called_once_with(outputs={"file_path": "/x.py"})

    def test_end_time_absent_when_start_time_missing(self, monkeypatch):
        """duration_s present but start_time missing: fall back to no end_time."""
        self._set_tracing_active(monkeypatch)
        mock_child = MagicMock()
        mock_parent = MagicMock(spec=["create_child", "end", "post"])
        mock_parent.create_child.return_value = mock_child

        record = ToolCallRecord(
            type="tool_use",  # type: ignore[arg-type]
            tool_name="Glob",
            tool_input={"pattern": "*.py"},
            timestamp="12:00:00",
            duration_s=3.0,
        )
        with patch("langsmith.RunTree", return_value=mock_parent):
            emit_tool_call_traces([record], "task:2.1", {})

        mock_child.end.assert_called_once_with(outputs={"pattern": "*.py"})


class TestAddTraceMetadataNoPackage:
    def test_does_not_raise_when_langsmith_not_installed(self):
        with patch.dict("sys.modules", {"langsmith": None, "langsmith.run_helpers": None}):
            add_trace_metadata({"node_name": "test_node", "graph_level": "pipeline"})

    def test_does_not_raise_when_run_helpers_missing(self):
        mock_langsmith = MagicMock()
        del mock_langsmith.run_helpers
        with patch.dict("sys.modules", {"langsmith": mock_langsmith}):
            add_trace_metadata({"cost": 0.01})


class TestAddTraceMetadataWithPackage:
    def test_calls_add_metadata_on_current_run(self):
        mock_run = MagicMock()
        mock_run_helpers = MagicMock()
        mock_run_helpers.get_current_run_tree.return_value = mock_run

        with patch.dict("sys.modules", {"langsmith.run_helpers": mock_run_helpers}):
            add_trace_metadata({"node_name": "plan_creation", "total_cost_usd": 0.05})

        mock_run.add_metadata.assert_called_once_with(
            {"node_name": "plan_creation", "total_cost_usd": 0.05}
        )

    def test_skips_when_no_current_run(self):
        mock_run_helpers = MagicMock()
        mock_run_helpers.get_current_run_tree.return_value = None

        with patch.dict("sys.modules", {"langsmith.run_helpers": mock_run_helpers}):
            add_trace_metadata({"node_name": "task_runner"})

        mock_run_helpers.get_current_run_tree.assert_called_once()

    def test_does_not_raise_on_unexpected_exception(self):
        add_trace_metadata({"node_name": "executor"})  # No langsmith installed -- should not raise


# ─── emit_tool_call_traces: parent_run_id forwarding ─────────────────────────


class TestEmitToolCallTracesParentRunId:
    def _set_tracing_active(self, monkeypatch):
        import langgraph_pipeline.shared.langsmith as ls_mod
        monkeypatch.setattr(ls_mod, "_tracing_active", True)
        monkeypatch.setattr(ls_mod, "_tracing_configured", True)

    def test_passes_parent_run_id_to_run_tree(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        mock_parent = MagicMock(spec=["create_child", "end", "post"])
        mock_parent.create_child.return_value = MagicMock()

        records = [_make_tool_call()]
        with patch("langsmith.RunTree", return_value=mock_parent) as mock_cls:
            emit_tool_call_traces(records, "task:1.1", {"task_id": "1.1"}, parent_run_id="test-uuid-123")

        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["parent_run_id"] == "test-uuid-123"

    def test_omits_parent_run_id_when_none(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        mock_parent = MagicMock(spec=["create_child", "end", "post"])
        mock_parent.create_child.return_value = MagicMock()

        records = [_make_tool_call()]
        with patch("langsmith.RunTree", return_value=mock_parent) as mock_cls:
            emit_tool_call_traces(records, "task:1.1", {"task_id": "1.1"})

        call_kwargs = mock_cls.call_args.kwargs
        assert "parent_run_id" not in call_kwargs

    def test_omits_parent_run_id_when_explicitly_none(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        mock_parent = MagicMock(spec=["create_child", "end", "post"])
        mock_parent.create_child.return_value = MagicMock()

        records = [_make_tool_call()]
        with patch("langsmith.RunTree", return_value=mock_parent) as mock_cls:
            emit_tool_call_traces(records, "task:1.1", {}, parent_run_id=None)

        call_kwargs = mock_cls.call_args.kwargs
        assert "parent_run_id" not in call_kwargs


# ─── create_root_run ──────────────────────────────────────────────────────────


class TestCreateRootRun:
    def _set_tracing_active(self, monkeypatch):
        import langgraph_pipeline.shared.langsmith as ls_mod
        monkeypatch.setattr(ls_mod, "_tracing_active", True)
        monkeypatch.setattr(ls_mod, "_tracing_configured", True)

    def test_returns_none_none_when_tracing_inactive(self, tmp_path):
        item_file = tmp_path / "item.md"
        item_file.write_text("# My Feature\n")
        run_tree, run_id = create_root_run("my-feature", str(item_file))
        assert run_tree is None
        assert run_id is None

    def test_returns_none_none_when_langsmith_not_installed(self, monkeypatch, tmp_path):
        self._set_tracing_active(monkeypatch)
        item_file = tmp_path / "item.md"
        item_file.write_text("# My Feature\n")
        with patch.dict("sys.modules", {"langsmith": None}):
            run_tree, run_id = create_root_run("my-feature", str(item_file))
        assert run_tree is None
        assert run_id is None

    def test_fresh_creation_writes_uuid_to_file(self, monkeypatch, tmp_path):
        self._set_tracing_active(monkeypatch)
        item_file = tmp_path / "item.md"
        item_file.write_text("# My Feature\n")
        mock_run = MagicMock()

        with patch("langsmith.RunTree", return_value=mock_run) as mock_cls:
            run_tree, run_id = create_root_run("my-feature", str(item_file))

        assert run_tree is mock_run
        assert run_id is not None
        content = item_file.read_text()
        assert f"{LANGSMITH_TRACE_LINE_PREFIX}{run_id}" in content
        # Verify UUID passed to RunTree constructor
        assert mock_cls.call_args.kwargs["id"] == run_id

    def test_fresh_creation_uuid_matches_pattern(self, monkeypatch, tmp_path):
        self._set_tracing_active(monkeypatch)
        item_file = tmp_path / "item.md"
        item_file.write_text("# My Feature\n")
        mock_run = MagicMock()

        with patch("langsmith.RunTree", return_value=mock_run):
            _, run_id = create_root_run("my-feature", str(item_file))

        assert LANGSMITH_TRACE_PATTERN.search(f"## LangSmith Trace: {run_id}") is not None

    def test_recovery_reads_existing_uuid_from_file(self, monkeypatch, tmp_path):
        self._set_tracing_active(monkeypatch)
        existing_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        item_file = tmp_path / "item.md"
        item_file.write_text(f"# My Feature\n\n## LangSmith Trace: {existing_uuid}\n")
        mock_run = MagicMock()

        with patch("langsmith.RunTree", return_value=mock_run) as mock_cls:
            run_tree, run_id = create_root_run("my-feature", str(item_file))

        assert run_id == existing_uuid
        assert mock_cls.call_args.kwargs["id"] == existing_uuid
        # File should still have the same UUID (not overwritten)
        assert existing_uuid in item_file.read_text()

    def test_recovery_does_not_rewrite_file(self, monkeypatch, tmp_path):
        self._set_tracing_active(monkeypatch)
        existing_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        original_content = f"# My Feature\n\n## LangSmith Trace: {existing_uuid}\n"
        item_file = tmp_path / "item.md"
        item_file.write_text(original_content)
        mock_run = MagicMock()

        with patch("langsmith.RunTree", return_value=mock_run):
            create_root_run("my-feature", str(item_file))

        assert item_file.read_text() == original_content

    def test_run_name_is_item_slug(self, monkeypatch, tmp_path):
        self._set_tracing_active(monkeypatch)
        item_file = tmp_path / "item.md"
        item_file.write_text("# My Feature\n")
        mock_run = MagicMock()

        with patch("langsmith.RunTree", return_value=mock_run) as mock_cls:
            create_root_run("my-feature-slug", str(item_file))

        assert mock_cls.call_args.kwargs["name"] == "my-feature-slug"

    def test_degrades_silently_on_exception(self, monkeypatch, tmp_path):
        self._set_tracing_active(monkeypatch)
        item_file = tmp_path / "item.md"
        item_file.write_text("# My Feature\n")

        with patch("langsmith.RunTree", side_effect=RuntimeError("LangSmith error")):
            run_tree, run_id = create_root_run("my-feature", str(item_file))

        assert run_tree is None
        assert run_id is None


# ─── finalize_root_run ────────────────────────────────────────────────────────


class TestFinalizeRootRun:
    def _set_tracing_active(self, monkeypatch):
        import langgraph_pipeline.shared.langsmith as ls_mod
        monkeypatch.setattr(ls_mod, "_tracing_active", True)
        monkeypatch.setattr(ls_mod, "_tracing_configured", True)

    def test_does_nothing_when_tracing_inactive(self):
        # Should not raise even without langsmith installed
        finalize_root_run("some-uuid", {"outcome": "PASS"})

    def test_does_nothing_when_root_run_id_is_none(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        with patch("langsmith.RunTree") as mock_cls:
            finalize_root_run(None, {"outcome": "PASS"})
        mock_cls.assert_not_called()

    def test_does_nothing_when_langsmith_not_installed(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        with patch.dict("sys.modules", {"langsmith": None}):
            finalize_root_run("some-uuid", {"outcome": "PASS"})  # Should not raise

    def test_reconstructs_run_by_id(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        mock_run = MagicMock()

        with patch("langsmith.RunTree", return_value=mock_run) as mock_cls:
            finalize_root_run("test-uuid-456", {"outcome": "PASS", "item_slug": "my-item"})

        assert mock_cls.call_args.kwargs["id"] == "test-uuid-456"

    def test_calls_end_with_outputs(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        mock_run = MagicMock()
        outputs = {"outcome": "PASS", "item_slug": "my-item"}

        with patch("langsmith.RunTree", return_value=mock_run):
            finalize_root_run("test-uuid-456", outputs)

        mock_run.end.assert_called_once_with(outputs=outputs)

    def test_calls_post(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        mock_run = MagicMock()

        with patch("langsmith.RunTree", return_value=mock_run):
            finalize_root_run("test-uuid-456", {"outcome": "FAIL"})

        mock_run.post.assert_called_once()

    def test_degrades_silently_on_exception(self, monkeypatch):
        self._set_tracing_active(monkeypatch)
        with patch("langsmith.RunTree", side_effect=RuntimeError("LangSmith error")):
            finalize_root_run("test-uuid-456", {"outcome": "PASS"})  # Should not raise
