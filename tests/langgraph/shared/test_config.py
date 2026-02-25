# tests/langgraph/shared/test_config.py
# Unit tests for the shared config loader module.
# Design: docs/plans/2026-02-25-02-extract-shared-modules-design.md

"""Unit tests for langgraph_pipeline.shared.config."""

import textwrap
from unittest.mock import mock_open, patch

import pytest

from langgraph_pipeline.shared.config import (
    DEFAULT_AGENTS_DIR,
    DEFAULT_BUILD_COMMAND,
    DEFAULT_DEV_SERVER_COMMAND,
    DEFAULT_DEV_SERVER_PORT,
    DEFAULT_E2E_COMMAND,
    DEFAULT_TEST_COMMAND,
    load_orchestrator_config,
)


class TestDefaults:
    def test_default_dev_server_port_is_int(self):
        assert isinstance(DEFAULT_DEV_SERVER_PORT, int)

    def test_default_dev_server_port_value(self):
        assert DEFAULT_DEV_SERVER_PORT == 3000

    def test_default_build_command_is_string(self):
        assert isinstance(DEFAULT_BUILD_COMMAND, str)

    def test_default_test_command_is_string(self):
        assert isinstance(DEFAULT_TEST_COMMAND, str)

    def test_default_dev_server_command_is_string(self):
        assert isinstance(DEFAULT_DEV_SERVER_COMMAND, str)

    def test_default_agents_dir_is_string(self):
        assert isinstance(DEFAULT_AGENTS_DIR, str)

    def test_default_e2e_command_is_string(self):
        assert isinstance(DEFAULT_E2E_COMMAND, str)


class TestLoadOrchestratorConfig:
    def test_returns_dict_when_file_missing(self):
        with patch("builtins.open", side_effect=IOError("not found")):
            result = load_orchestrator_config()
        assert result == {}

    def test_returns_dict_on_yaml_error(self):
        bad_yaml = "key: [unclosed"
        with patch("builtins.open", mock_open(read_data=bad_yaml)):
            result = load_orchestrator_config()
        assert result == {}

    def test_returns_empty_dict_when_file_is_empty(self):
        with patch("builtins.open", mock_open(read_data="")):
            result = load_orchestrator_config()
        assert result == {}

    def test_returns_empty_dict_when_yaml_is_not_a_mapping(self):
        with patch("builtins.open", mock_open(read_data="- item1\n- item2\n")):
            result = load_orchestrator_config()
        assert result == {}

    def test_returns_parsed_dict_for_valid_yaml(self):
        yaml_content = textwrap.dedent("""\
            build_command: make build
            test_command: make test
            dev_server_port: 8080
        """)
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            result = load_orchestrator_config()
        assert result == {
            "build_command": "make build",
            "test_command": "make test",
            "dev_server_port": 8080,
        }

    def test_custom_values_survive_roundtrip(self):
        yaml_content = "agents_dir: .claude/custom-agents/\n"
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            result = load_orchestrator_config()
        assert result.get("agents_dir") == ".claude/custom-agents/"

    def test_default_applied_when_key_absent(self):
        with patch("builtins.open", mock_open(read_data="build_command: cargo build\n")):
            config = load_orchestrator_config()
        port = int(config.get("dev_server_port", DEFAULT_DEV_SERVER_PORT))
        assert port == DEFAULT_DEV_SERVER_PORT
