# tests/langgraph/shared/test_claude_cli.py
# Unit tests for the shared claude_cli module.
# Design: docs/plans/2026-02-25-02-extract-shared-modules-design.md

"""Unit tests for langgraph_pipeline.shared.claude_cli."""

import io
import json

import pytest

from langgraph_pipeline.shared.claude_cli import (
    OUTPUT_PREVIEW_MAX_CHARS,
    TOOL_CMD_PREVIEW_MAX_CHARS,
    OutputCollector,
    stream_json_output,
    stream_output,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def make_pipe(text: str) -> io.StringIO:
    """Create a StringIO object that behaves like a subprocess pipe."""
    return io.StringIO(text)


# ─── OutputCollector ──────────────────────────────────────────────────────────


class TestOutputCollector:
    def test_initial_state_is_empty(self):
        c = OutputCollector()
        assert c.lines == []
        assert c.bytes_received == 0
        assert c.line_count == 0

    def test_add_line_appends_to_lines(self):
        c = OutputCollector()
        c.add_line("hello\n")
        assert c.lines == ["hello\n"]

    def test_add_line_increments_line_count(self):
        c = OutputCollector()
        c.add_line("a\n")
        c.add_line("b\n")
        assert c.line_count == 2

    def test_add_line_counts_bytes(self):
        c = OutputCollector()
        line = "hello\n"
        c.add_line(line)
        assert c.bytes_received == len(line.encode("utf-8"))

    def test_add_line_accumulates_bytes_across_calls(self):
        c = OutputCollector()
        c.add_line("abc\n")
        c.add_line("def\n")
        expected = len("abc\n".encode("utf-8")) + len("def\n".encode("utf-8"))
        assert c.bytes_received == expected

    def test_add_line_counts_multibyte_utf8(self):
        c = OutputCollector()
        line = "héllo\n"
        c.add_line(line)
        assert c.bytes_received == len(line.encode("utf-8"))
        assert c.bytes_received > len(line)  # multibyte chars > char count

    def test_get_output_joins_lines(self):
        c = OutputCollector()
        c.add_line("line1\n")
        c.add_line("line2\n")
        assert c.get_output() == "line1\nline2\n"

    def test_get_output_empty_collector(self):
        c = OutputCollector()
        assert c.get_output() == ""

    def test_multiple_adds_maintain_order(self):
        c = OutputCollector()
        for i in range(5):
            c.add_line(f"line{i}\n")
        assert c.line_count == 5
        output = c.get_output()
        for i in range(5):
            assert f"line{i}" in output


# ─── stream_output ────────────────────────────────────────────────────────────


class TestStreamOutput:
    def test_collects_all_lines(self):
        pipe = make_pipe("line1\nline2\nline3\n")
        c = OutputCollector()
        stream_output(pipe, "TEST", c, show_full=False)
        assert c.line_count == 3

    def test_get_output_contains_content(self):
        pipe = make_pipe("hello world\n")
        c = OutputCollector()
        stream_output(pipe, "X", c, show_full=False)
        assert "hello world" in c.get_output()

    def test_bytes_received_is_populated(self):
        pipe = make_pipe("abc\ndef\n")
        c = OutputCollector()
        stream_output(pipe, "X", c, show_full=False)
        assert c.bytes_received > 0

    def test_show_full_false_does_not_print(self, capsys):
        pipe = make_pipe("secret\n")
        c = OutputCollector()
        stream_output(pipe, "X", c, show_full=False)
        captured = capsys.readouterr()
        assert "secret" not in captured.out

    def test_show_full_true_prints_lines(self, capsys):
        pipe = make_pipe("visible_line\n")
        c = OutputCollector()
        stream_output(pipe, "PREFIX", c, show_full=True)
        captured = capsys.readouterr()
        assert "visible_line" in captured.out

    def test_show_full_includes_prefix(self, capsys):
        pipe = make_pipe("data\n")
        c = OutputCollector()
        stream_output(pipe, "MYPREFIX", c, show_full=True)
        captured = capsys.readouterr()
        assert "MYPREFIX" in captured.out

    def test_empty_pipe_produces_empty_collector(self):
        pipe = make_pipe("")
        c = OutputCollector()
        stream_output(pipe, "X", c, show_full=False)
        assert c.line_count == 0
        assert c.get_output() == ""

    def test_handles_lines_without_newline(self):
        pipe = make_pipe("no newline at end")
        c = OutputCollector()
        stream_output(pipe, "X", c, show_full=False)
        assert c.line_count == 1
        assert "no newline at end" in c.get_output()


# ─── stream_json_output ───────────────────────────────────────────────────────


def _make_json_pipe(events: list[dict]) -> io.StringIO:
    """Serialize events as newline-delimited JSON lines."""
    lines = "\n".join(json.dumps(e) for e in events) + "\n"
    return io.StringIO(lines)


class TestStreamJsonOutput:
    def test_collects_all_lines(self):
        events = [{"type": "assistant", "message": {"content": []}}]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        assert c.line_count == 1

    def test_invalid_json_is_skipped_but_collected(self):
        pipe = make_pipe("not json\n{also not}\n")
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        assert c.line_count == 2  # lines collected
        assert result == {}  # no result captured

    def test_result_event_populates_result_capture(self):
        events = [
            {"type": "result", "total_cost_usd": 0.05, "duration_ms": 2000, "num_turns": 3}
        ]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        assert result["total_cost_usd"] == 0.05
        assert result["num_turns"] == 3

    def test_result_event_is_printed(self, capsys):
        events = [
            {"type": "result", "total_cost_usd": 0.01, "duration_ms": 1000, "num_turns": 1}
        ]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        captured = capsys.readouterr()
        assert "[Result]" in captured.out

    def test_assistant_text_block_is_printed(self, capsys):
        events = [{
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello from Claude"}]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        captured = capsys.readouterr()
        assert "Hello from Claude" in captured.out
        assert "[Claude]" in captured.out

    def test_empty_text_block_is_not_printed(self, capsys):
        events = [{
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "   "}]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        captured = capsys.readouterr()
        assert "[Claude]" not in captured.out

    def test_long_text_block_is_truncated(self, capsys):
        long_text = "x" * (OUTPUT_PREVIEW_MAX_CHARS + 50)
        events = [{
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": long_text}]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        captured = capsys.readouterr()
        assert "..." in captured.out
        # Should not print the full text
        assert long_text not in captured.out

    def test_tool_use_read_shows_file_path(self, capsys):
        events = [{
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use",
                "name": "Read",
                "input": {"file_path": "/some/file.py"}
            }]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        captured = capsys.readouterr()
        assert "Read" in captured.out
        assert "/some/file.py" in captured.out

    def test_tool_use_bash_shows_command(self, capsys):
        events = [{
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use",
                "name": "Bash",
                "input": {"command": "ls -la"}
            }]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        captured = capsys.readouterr()
        assert "Bash" in captured.out
        assert "ls -la" in captured.out

    def test_tool_use_long_bash_command_is_truncated(self, capsys):
        long_cmd = "echo " + "a" * (TOOL_CMD_PREVIEW_MAX_CHARS + 20)
        events = [{
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use",
                "name": "Bash",
                "input": {"command": long_cmd}
            }]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        captured = capsys.readouterr()
        assert "..." in captured.out

    def test_tool_use_grep_shows_pattern(self, capsys):
        events = [{
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use",
                "name": "Grep",
                "input": {"pattern": "def my_func"}
            }]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        captured = capsys.readouterr()
        assert "Grep" in captured.out
        assert "def my_func" in captured.out

    def test_tool_use_unknown_tool_shows_no_detail(self, capsys):
        events = [{
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use",
                "name": "UnknownTool",
                "input": {"secret": "value"}
            }]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        captured = capsys.readouterr()
        assert "UnknownTool" in captured.out
        assert "secret" not in captured.out

    def test_empty_pipe_produces_empty_collector(self):
        pipe = make_pipe("")
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        assert c.line_count == 0
        assert result == {}

    def test_multiple_result_events_accumulate(self):
        events = [
            {"type": "result", "total_cost_usd": 0.01, "duration_ms": 1000, "num_turns": 1},
            {"type": "result", "total_cost_usd": 0.02, "duration_ms": 2000, "num_turns": 2},
        ]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        # Last result wins (update semantics)
        assert result["total_cost_usd"] == 0.02

    def test_unknown_event_type_is_silently_ignored(self, capsys):
        events = [{"type": "unknown_event", "data": "something"}]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        stream_json_output(pipe, c, result)
        # Line should be collected but nothing printed
        assert c.line_count == 1
        captured = capsys.readouterr()
        assert captured.out == ""


# ─── Constants ────────────────────────────────────────────────────────────────


class TestConstants:
    def test_output_preview_max_chars_is_positive(self):
        assert OUTPUT_PREVIEW_MAX_CHARS > 0

    def test_tool_cmd_preview_max_chars_is_positive(self):
        assert TOOL_CMD_PREVIEW_MAX_CHARS > 0
