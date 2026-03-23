# tests/langgraph/shared/test_dotenv.py
# Unit tests for the minimal .env file loader.

"""Unit tests for langgraph_pipeline.shared.dotenv."""

import os

import pytest

from langgraph_pipeline.shared.dotenv import load_dotenv


class TestLoadDotenv:
    def test_returns_zero_when_file_missing(self, tmp_path):
        result = load_dotenv(str(tmp_path / "nonexistent"))
        assert result == 0

    def test_loads_simple_key_value(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_DOTENV_KEY=hello\n")
        monkeypatch.delenv("TEST_DOTENV_KEY", raising=False)
        result = load_dotenv(str(env_file))
        assert result == 1
        assert os.environ["TEST_DOTENV_KEY"] == "hello"
        monkeypatch.delenv("TEST_DOTENV_KEY")

    def test_loads_double_quoted_value(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text('TEST_DOTENV_Q="with spaces"\n')
        monkeypatch.delenv("TEST_DOTENV_Q", raising=False)
        load_dotenv(str(env_file))
        assert os.environ["TEST_DOTENV_Q"] == "with spaces"
        monkeypatch.delenv("TEST_DOTENV_Q")

    def test_loads_single_quoted_value(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_DOTENV_SQ='single quoted'\n")
        monkeypatch.delenv("TEST_DOTENV_SQ", raising=False)
        load_dotenv(str(env_file))
        assert os.environ["TEST_DOTENV_SQ"] == "single quoted"
        monkeypatch.delenv("TEST_DOTENV_SQ")

    def test_skips_comments_and_blank_lines(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nTEST_DOTENV_C=val\n  # indented comment\n")
        monkeypatch.delenv("TEST_DOTENV_C", raising=False)
        result = load_dotenv(str(env_file))
        assert result == 1
        assert os.environ["TEST_DOTENV_C"] == "val"
        monkeypatch.delenv("TEST_DOTENV_C")

    def test_does_not_overwrite_existing_env(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_DOTENV_EX=from_file\n")
        monkeypatch.setenv("TEST_DOTENV_EX", "from_env")
        result = load_dotenv(str(env_file))
        assert result == 0
        assert os.environ["TEST_DOTENV_EX"] == "from_env"

    def test_handles_export_prefix(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("export TEST_DOTENV_EXP=exported\n")
        monkeypatch.delenv("TEST_DOTENV_EXP", raising=False)
        load_dotenv(str(env_file))
        assert os.environ["TEST_DOTENV_EXP"] == "exported"
        monkeypatch.delenv("TEST_DOTENV_EXP")

    def test_strips_trailing_whitespace_from_unquoted_values(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_DOTENV_WS=value   \n")
        monkeypatch.delenv("TEST_DOTENV_WS", raising=False)
        load_dotenv(str(env_file))
        assert os.environ["TEST_DOTENV_WS"] == "value"
        monkeypatch.delenv("TEST_DOTENV_WS")

    def test_loads_multiple_keys(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_A=1\nTEST_B=2\nTEST_C=3\n")
        for k in ("TEST_A", "TEST_B", "TEST_C"):
            monkeypatch.delenv(k, raising=False)
        result = load_dotenv(str(env_file))
        assert result == 3
        for k in ("TEST_A", "TEST_B", "TEST_C"):
            monkeypatch.delenv(k)
