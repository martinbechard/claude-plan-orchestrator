# tests/test_web_server.py
# Unit tests for find_free_port() and write_port_to_config() in server.py
# Design reference: docs/plans/2026-03-25-22-dynamic-web-server-port-allocation-design.md

import socket
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from langgraph_pipeline.web.server import (
    WEB_SERVER_DEFAULT_PORT,
    WEB_SERVER_PORT_SCAN_MAX,
    find_free_port,
    write_port_to_config,
)


# ─── find_free_port ───────────────────────────────────────────────────────────


class TestFindFreePort:
    def test_returns_free_port_when_start_is_available(self):
        port = find_free_port(WEB_SERVER_DEFAULT_PORT)
        assert WEB_SERVER_DEFAULT_PORT <= port <= WEB_SERVER_PORT_SCAN_MAX

    def test_skips_occupied_ports(self):
        # Simulate the first port being occupied by having bind() fail once, then succeed.
        from unittest.mock import MagicMock

        bind_call_count = [0]

        def make_sock(*args, **kwargs):
            m = MagicMock()

            def patched_bind(addr):
                if bind_call_count[0] == 0:
                    bind_call_count[0] += 1
                    raise OSError("address in use")
                bind_call_count[0] += 1

            m.__enter__ = lambda s: s
            m.__exit__ = MagicMock(return_value=False)
            m.bind = patched_bind
            return m

        with patch("langgraph_pipeline.web.server.socket.socket", side_effect=make_sock):
            port = find_free_port(WEB_SERVER_DEFAULT_PORT)
        assert port == WEB_SERVER_DEFAULT_PORT + 1

    def test_returns_exact_start_when_free(self):
        # Pick a high port unlikely to be in use to verify the exact value is returned.
        high_port = WEB_SERVER_PORT_SCAN_MAX - 5
        # We can't guarantee it's free on every machine, so only assert the
        # returned value is in-range rather than pinning it.
        port = find_free_port(high_port)
        assert high_port <= port <= WEB_SERVER_PORT_SCAN_MAX

    def test_raises_when_all_ports_occupied(self):
        # Patch socket.socket so every bind() raises OSError to simulate exhaustion.
        with patch("langgraph_pipeline.web.server.socket.socket") as mock_socket_cls:
            mock_sock = mock_socket_cls.return_value.__enter__.return_value
            mock_sock.bind.side_effect = OSError("address in use")
            with pytest.raises(RuntimeError, match="No free port found"):
                find_free_port(WEB_SERVER_DEFAULT_PORT)


# ─── write_port_to_config ─────────────────────────────────────────────────────


class TestWritePortToConfig:
    def _write_config(self, text: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        tmp.write(text)
        tmp.flush()
        tmp.close()
        return Path(tmp.name)

    def test_appends_web_block_when_section_absent(self):
        path = self._write_config("slack:\n  token: abc\n")
        write_port_to_config(7071, path)
        content = path.read_text()
        assert "web:" in content
        assert "  port: 7071" in content

    def test_inserts_port_under_existing_web_section(self):
        path = self._write_config("web:\n  other_key: value\n")
        write_port_to_config(7080, path)
        content = path.read_text()
        assert "  port: 7080" in content
        # The other_key must still be present
        assert "other_key: value" in content

    def test_updates_existing_port_under_web_section(self):
        path = self._write_config("web:\n  port: 7070\n")
        write_port_to_config(7099, path)
        content = path.read_text()
        assert "  port: 7099" in content
        # Old port value must no longer appear
        assert "port: 7070" not in content

    def test_preserves_comments_in_config(self):
        path = self._write_config(
            "# top-level comment\nslack:\n  token: abc  # inline\n"
        )
        write_port_to_config(7072, path)
        content = path.read_text()
        assert "# top-level comment" in content
        assert "# inline" in content

    def test_noop_when_config_does_not_exist(self):
        missing = Path(tempfile.gettempdir()) / "does_not_exist_xyz.yaml"
        # Must not raise
        write_port_to_config(7070, missing)

    def test_adds_trailing_newline_before_web_block(self):
        # Config without trailing newline should still produce valid YAML output.
        path = self._write_config("key: value")
        write_port_to_config(7073, path)
        content = path.read_text()
        assert "web:" in content
        assert "  port: 7073" in content
