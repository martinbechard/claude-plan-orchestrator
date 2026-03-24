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
    ToolCallRecord,
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


# ─── stream_json_output: tool_calls accumulation ──────────────────────────────


class TestStreamJsonOutputToolCallsAccumulation:
    def test_tool_calls_none_by_default(self):
        """Passing no tool_calls arg does not raise and produces no side-effects."""
        events = [{
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "/f"}}]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        # Must not raise even without tool_calls arg
        stream_json_output(pipe, c, result)

    def test_tool_use_block_appended_to_tool_calls(self):
        events = [{
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        tool_calls: list[ToolCallRecord] = []
        stream_json_output(pipe, c, result, tool_calls)
        assert len(tool_calls) == 1
        assert tool_calls[0]["type"] == "tool_use"
        assert tool_calls[0]["tool_name"] == "Bash"
        assert tool_calls[0]["tool_input"] == {"command": "ls"}

    def test_text_block_appended_to_tool_calls(self):
        events = [{
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello from Claude"}]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        tool_calls: list[ToolCallRecord] = []
        stream_json_output(pipe, c, result, tool_calls)
        assert len(tool_calls) == 1
        assert tool_calls[0]["type"] == "text"
        assert tool_calls[0]["tool_input"] == {"text": "Hello from Claude"}

    def test_empty_text_block_not_appended(self):
        events = [{
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "   "}]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        tool_calls: list[ToolCallRecord] = []
        stream_json_output(pipe, c, result, tool_calls)
        assert len(tool_calls) == 0

    def test_multiple_blocks_all_appended(self):
        events = [{
            "type": "assistant",
            "message": {"content": [
                {"type": "text", "text": "Thinking..."},
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/a.py"}},
                {"type": "tool_use", "name": "Write", "input": {"file_path": "/b.py"}},
            ]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        tool_calls: list[ToolCallRecord] = []
        stream_json_output(pipe, c, result, tool_calls)
        assert len(tool_calls) == 3
        assert tool_calls[0]["type"] == "text"
        assert tool_calls[1]["tool_name"] == "Read"
        assert tool_calls[2]["tool_name"] == "Write"

    def test_tool_call_record_has_timestamp(self):
        events = [{
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "Glob", "input": {"pattern": "*.py"}}]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        tool_calls: list[ToolCallRecord] = []
        stream_json_output(pipe, c, result, tool_calls)
        assert len(tool_calls) == 1
        assert tool_calls[0]["timestamp"] != ""

    def test_result_event_does_not_append_to_tool_calls(self):
        events = [
            {"type": "result", "total_cost_usd": 0.01, "duration_ms": 1000, "num_turns": 1}
        ]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        tool_calls: list[ToolCallRecord] = []
        stream_json_output(pipe, c, result, tool_calls)
        assert len(tool_calls) == 0

    def test_tool_calls_list_not_mutated_when_none(self):
        """When tool_calls is None (default), no ToolCallRecord is produced."""
        events = [{
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "pwd"}}]}
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        # No assertion needed -- verifies no AttributeError is raised on None
        stream_json_output(pipe, c, result, None)


# ─── stream_json_output: duration tracking ────────────────────────────────────


class TestStreamJsonOutputDurationTracking:
    def test_duration_s_set_when_tool_result_arrives(self):
        """duration_s is computed when a user message with matching tool_use_id arrives."""
        events = [
            {
                "type": "assistant",
                "message": {"content": [{
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": "ls"},
                    "id": "tu_001",
                }]},
            },
            {
                "type": "user",
                "message": {"content": [{
                    "type": "tool_result",
                    "tool_use_id": "tu_001",
                    "content": "file1\nfile2",
                }]},
            },
        ]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        tool_calls: list[ToolCallRecord] = []
        stream_json_output(pipe, c, result, tool_calls)
        assert len(tool_calls) == 1
        assert tool_calls[0]["type"] == "tool_use"
        assert tool_calls[0].get("duration_s") is not None
        assert tool_calls[0]["duration_s"] >= 0.0  # type: ignore[operator]

    def test_duration_s_not_set_for_text_blocks(self):
        """Text blocks never have duration_s because they have no tool_result pairing."""
        events = [{
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello from Claude"}]},
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        tool_calls: list[ToolCallRecord] = []
        stream_json_output(pipe, c, result, tool_calls)
        assert len(tool_calls) == 1
        assert tool_calls[0]["type"] == "text"
        assert tool_calls[0].get("duration_s") is None

    def test_duration_s_not_set_for_unmatched_tool_calls(self):
        """Tool calls with no arriving tool_result leave duration_s unset."""
        events = [{
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use",
                "name": "Read",
                "input": {"file_path": "/a.py"},
                "id": "tu_002",
            }]},
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        tool_calls: list[ToolCallRecord] = []
        stream_json_output(pipe, c, result, tool_calls)
        assert len(tool_calls) == 1
        assert tool_calls[0]["type"] == "tool_use"
        assert tool_calls[0].get("duration_s") is None

    def test_start_time_set_on_tool_use_record(self):
        """start_time is captured when the tool_use block is processed."""
        events = [{
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use",
                "name": "Glob",
                "input": {"pattern": "*.py"},
                "id": "tu_003",
            }]},
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        tool_calls: list[ToolCallRecord] = []
        stream_json_output(pipe, c, result, tool_calls)
        assert len(tool_calls) == 1
        assert tool_calls[0].get("start_time") is not None

    def test_tool_use_id_set_on_record(self):
        """tool_use_id from the block is stored on ToolCallRecord."""
        events = [{
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use",
                "name": "Bash",
                "input": {"command": "pwd"},
                "id": "tu_abc",
            }]},
        }]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        tool_calls: list[ToolCallRecord] = []
        stream_json_output(pipe, c, result, tool_calls)
        assert tool_calls[0].get("tool_use_id") == "tu_abc"

    def test_unmatched_tool_result_does_not_raise(self):
        """A tool_result with no corresponding pending tool_use is silently ignored."""
        events = [
            {
                "type": "user",
                "message": {"content": [{
                    "type": "tool_result",
                    "tool_use_id": "no_such_id",
                    "content": "data",
                }]},
            },
        ]
        pipe = _make_json_pipe(events)
        c = OutputCollector()
        result: dict = {}
        tool_calls: list[ToolCallRecord] = []
        stream_json_output(pipe, c, result, tool_calls)
        assert len(tool_calls) == 0  # No tool_use was emitted


# ─── Constants ────────────────────────────────────────────────────────────────


class TestConstants:
    def test_output_preview_max_chars_is_positive(self):
        assert OUTPUT_PREVIEW_MAX_CHARS > 0

    def test_tool_cmd_preview_max_chars_is_positive(self):
        assert TOOL_CMD_PREVIEW_MAX_CHARS > 0
