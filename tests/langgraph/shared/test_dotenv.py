# tests/langgraph/shared/test_dotenv.py
# Unit tests for the minimal .env file loader.

"""Unit tests for langgraph_pipeline.shared.dotenv."""

import os

import pytest

from langgraph_pipeline.shared.dotenv import _load_single_file, load_dotenv_files


class TestLoadSingleFile:
    def test_returns_zero_when_file_missing(self, tmp_path):
        result = _load_single_file(str(tmp_path / "nonexistent"))
        assert result == 0

    def test_loads_simple_key_value(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_DOTENV_KEY=hello\n")
        monkeypatch.delenv("TEST_DOTENV_KEY", raising=False)
        result = _load_single_file(str(env_file))
        assert result == 1
        assert os.environ["TEST_DOTENV_KEY"] == "hello"
        monkeypatch.delenv("TEST_DOTENV_KEY")

    def test_loads_double_quoted_value(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text('TEST_DOTENV_Q="with spaces"\n')
        monkeypatch.delenv("TEST_DOTENV_Q", raising=False)
        _load_single_file(str(env_file))
        assert os.environ["TEST_DOTENV_Q"] == "with spaces"
        monkeypatch.delenv("TEST_DOTENV_Q")

    def test_loads_single_quoted_value(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_DOTENV_SQ='single quoted'\n")
        monkeypatch.delenv("TEST_DOTENV_SQ", raising=False)
        _load_single_file(str(env_file))
        assert os.environ["TEST_DOTENV_SQ"] == "single quoted"
        monkeypatch.delenv("TEST_DOTENV_SQ")

    def test_skips_comments_and_blank_lines(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nTEST_DOTENV_C=val\n  # indented comment\n")
        monkeypatch.delenv("TEST_DOTENV_C", raising=False)
        result = _load_single_file(str(env_file))
        assert result == 1
        assert os.environ["TEST_DOTENV_C"] == "val"
        monkeypatch.delenv("TEST_DOTENV_C")

    def test_does_not_overwrite_existing_env(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_DOTENV_EX=from_file\n")
        monkeypatch.setenv("TEST_DOTENV_EX", "from_env")
        result = _load_single_file(str(env_file))
        assert result == 0
        assert os.environ["TEST_DOTENV_EX"] == "from_env"

    def test_handles_export_prefix(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("export TEST_DOTENV_EXP=exported\n")
        monkeypatch.delenv("TEST_DOTENV_EXP", raising=False)
        _load_single_file(str(env_file))
        assert os.environ["TEST_DOTENV_EXP"] == "exported"
        monkeypatch.delenv("TEST_DOTENV_EXP")

    def test_strips_trailing_whitespace_from_unquoted_values(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_DOTENV_WS=value   \n")
        monkeypatch.delenv("TEST_DOTENV_WS", raising=False)
        _load_single_file(str(env_file))
        assert os.environ["TEST_DOTENV_WS"] == "value"
        monkeypatch.delenv("TEST_DOTENV_WS")

    def test_loads_multiple_keys(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_A=1\nTEST_B=2\nTEST_C=3\n")
        for k in ("TEST_A", "TEST_B", "TEST_C"):
            monkeypatch.delenv(k, raising=False)
        result = _load_single_file(str(env_file))
        assert result == 3
        for k in ("TEST_A", "TEST_B", "TEST_C"):
            monkeypatch.delenv(k)


class TestLoadDotenvFiles:
    def test_env_local_wins_over_env(self, tmp_path, monkeypatch):
        """Values in .env.local take precedence over .env."""
        (tmp_path / ".env.local").write_text("TEST_PRIO=from_local\n")
        (tmp_path / ".env").write_text("TEST_PRIO=from_env\n")
        monkeypatch.delenv("TEST_PRIO", raising=False)
        monkeypatch.chdir(tmp_path)

        from langgraph_pipeline.shared import dotenv
        original_files = dotenv.DOTENV_FILES
        dotenv.DOTENV_FILES = (".env.local", ".env")
        try:
            load_dotenv_files()
        finally:
            dotenv.DOTENV_FILES = original_files

        assert os.environ["TEST_PRIO"] == "from_local"
        monkeypatch.delenv("TEST_PRIO")

    def test_falls_back_to_env_when_no_local(self, tmp_path, monkeypatch):
        """When .env.local is missing, .env values are loaded."""
        (tmp_path / ".env").write_text("TEST_FB=from_env\n")
        monkeypatch.delenv("TEST_FB", raising=False)
        monkeypatch.chdir(tmp_path)

        from langgraph_pipeline.shared import dotenv
        original_files = dotenv.DOTENV_FILES
        dotenv.DOTENV_FILES = (".env.local", ".env")
        try:
            load_dotenv_files()
        finally:
            dotenv.DOTENV_FILES = original_files

        assert os.environ["TEST_FB"] == "from_env"
        monkeypatch.delenv("TEST_FB")

    def test_real_env_wins_over_both_files(self, tmp_path, monkeypatch):
        """Real environment variables are never overwritten."""
        (tmp_path / ".env.local").write_text("TEST_REAL=from_local\n")
        (tmp_path / ".env").write_text("TEST_REAL=from_env\n")
        monkeypatch.setenv("TEST_REAL", "from_shell")
        monkeypatch.chdir(tmp_path)

        from langgraph_pipeline.shared import dotenv
        original_files = dotenv.DOTENV_FILES
        dotenv.DOTENV_FILES = (".env.local", ".env")
        try:
            load_dotenv_files()
        finally:
            dotenv.DOTENV_FILES = original_files

        assert os.environ["TEST_REAL"] == "from_shell"

    def test_merges_keys_from_both_files(self, tmp_path, monkeypatch):
        """.env.local and .env can define different keys; both are loaded."""
        (tmp_path / ".env.local").write_text("TEST_LOCAL_ONLY=local\n")
        (tmp_path / ".env").write_text("TEST_ENV_ONLY=env\n")
        monkeypatch.delenv("TEST_LOCAL_ONLY", raising=False)
        monkeypatch.delenv("TEST_ENV_ONLY", raising=False)
        monkeypatch.chdir(tmp_path)

        from langgraph_pipeline.shared import dotenv
        original_files = dotenv.DOTENV_FILES
        dotenv.DOTENV_FILES = (".env.local", ".env")
        try:
            result = load_dotenv_files()
        finally:
            dotenv.DOTENV_FILES = original_files

        assert result == 2
        assert os.environ["TEST_LOCAL_ONLY"] == "local"
        assert os.environ["TEST_ENV_ONLY"] == "env"
        monkeypatch.delenv("TEST_LOCAL_ONLY")
        monkeypatch.delenv("TEST_ENV_ONLY")
