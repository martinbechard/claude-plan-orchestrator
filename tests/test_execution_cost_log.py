# tests/test_execution_cost_log.py
# Unit tests for ToolCallRecord, write_execution_cost_log, and tool call extraction.
# Design ref: docs/plans/2026-03-24-12-structured-execution-cost-log-and-analysis-design.md

import importlib.util
import json
from pathlib import Path

import pytest

# plan-orchestrator.py has a hyphen in the filename, so we must use importlib
# to load it as a module under a valid Python identifier.
spec = importlib.util.spec_from_file_location(
    "plan_orchestrator", "scripts/plan-orchestrator.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ToolCallRecord = mod.ToolCallRecord
TaskUsage = mod.TaskUsage
write_execution_cost_log = mod.write_execution_cost_log
_extract_tool_calls_from_json_output = mod._extract_tool_calls_from_json_output
_make_tool_call_record = mod._make_tool_call_record


# --- ToolCallRecord dataclass tests ---


def test_tool_call_record_all_fields():
    """ToolCallRecord should store all provided fields."""
    record = ToolCallRecord(tool="Read", file_path="src/foo.py", result_bytes=4200)
    assert record.tool == "Read"
    assert record.file_path == "src/foo.py"
    assert record.command is None
    assert record.result_bytes == 4200


def test_tool_call_record_optional_fields_default_to_none():
    """ToolCallRecord with only tool name should have all optional fields None."""
    record = ToolCallRecord(tool="Agent")
    assert record.tool == "Agent"
    assert record.file_path is None
    assert record.command is None
    assert record.result_bytes is None


def test_tool_call_record_bash():
    """Bash tool call should store command, not file_path."""
    record = ToolCallRecord(tool="Bash", command="pnpm run build", result_bytes=380)
    assert record.tool == "Bash"
    assert record.command == "pnpm run build"
    assert record.file_path is None
    assert record.result_bytes == 380


# --- write_execution_cost_log tests ---


def _make_usage(**kwargs) -> TaskUsage:
    defaults = dict(input_tokens=1000, output_tokens=200, total_cost_usd=0.01)
    defaults.update(kwargs)
    return TaskUsage(**defaults)


def test_write_creates_file_on_first_call(tmp_path, monkeypatch):
    """First call should create the JSON file with correct outer structure."""
    monkeypatch.setattr(mod, "COST_LOG_DIR", tmp_path)

    write_execution_cost_log(
        item_slug="12-test-item",
        item_type="feature",
        task_id="1.1",
        agent_type="coder",
        model="claude-sonnet-4-6",
        usage=_make_usage(input_tokens=42000, output_tokens=1800, total_cost_usd=0.042),
        duration_s=87.3,
        tool_calls=[],
    )

    log_path = tmp_path / "12-test-item.json"
    assert log_path.exists()

    data = json.loads(log_path.read_text())
    assert data["item_slug"] == "12-test-item"
    assert data["item_type"] == "feature"
    assert len(data["tasks"]) == 1

    task = data["tasks"][0]
    assert task["task_id"] == "1.1"
    assert task["agent_type"] == "coder"
    assert task["model"] == "claude-sonnet-4-6"
    assert task["input_tokens"] == 42000
    assert task["output_tokens"] == 1800
    assert task["cost_usd"] == pytest.approx(0.042)
    assert task["duration_s"] == pytest.approx(87.3, abs=0.1)
    assert task["tool_calls"] == []


def test_write_appends_on_subsequent_calls(tmp_path, monkeypatch):
    """Subsequent calls should append to the existing tasks list."""
    monkeypatch.setattr(mod, "COST_LOG_DIR", tmp_path)

    write_execution_cost_log(
        item_slug="12-test-item",
        item_type="feature",
        task_id="1.1",
        agent_type="coder",
        model="claude-sonnet-4-6",
        usage=_make_usage(),
        duration_s=10.0,
        tool_calls=[],
    )
    write_execution_cost_log(
        item_slug="12-test-item",
        item_type="feature",
        task_id="2.1",
        agent_type="validator",
        model="claude-sonnet-4-6",
        usage=_make_usage(input_tokens=5000, output_tokens=300, total_cost_usd=0.005),
        duration_s=15.5,
        tool_calls=[],
    )

    data = json.loads((tmp_path / "12-test-item.json").read_text())
    assert len(data["tasks"]) == 2
    assert data["tasks"][0]["task_id"] == "1.1"
    assert data["tasks"][1]["task_id"] == "2.1"
    assert data["tasks"][1]["agent_type"] == "validator"


def test_write_includes_tool_calls(tmp_path, monkeypatch):
    """Tool calls should be serialised into the task record."""
    monkeypatch.setattr(mod, "COST_LOG_DIR", tmp_path)

    tool_calls = [
        ToolCallRecord(tool="Read", file_path="src/foo.py", result_bytes=4200),
        ToolCallRecord(tool="Bash", command="pnpm run build", result_bytes=380),
    ]
    write_execution_cost_log(
        item_slug="12-test-item",
        item_type="feature",
        task_id="1.1",
        agent_type="coder",
        model="claude-sonnet-4-6",
        usage=_make_usage(),
        duration_s=30.0,
        tool_calls=tool_calls,
    )

    data = json.loads((tmp_path / "12-test-item.json").read_text())
    recorded_calls = data["tasks"][0]["tool_calls"]
    assert len(recorded_calls) == 2
    assert recorded_calls[0] == {"tool": "Read", "file_path": "src/foo.py", "result_bytes": 4200}
    assert recorded_calls[1] == {"tool": "Bash", "command": "pnpm run build", "result_bytes": 380}


def test_write_omits_none_fields_from_tool_calls(tmp_path, monkeypatch):
    """None optional fields should not appear in the serialised tool call dicts."""
    monkeypatch.setattr(mod, "COST_LOG_DIR", tmp_path)

    tool_calls = [ToolCallRecord(tool="Agent")]
    write_execution_cost_log(
        item_slug="12-test-item",
        item_type="feature",
        task_id="1.1",
        agent_type="coder",
        model="claude-sonnet-4-6",
        usage=_make_usage(),
        duration_s=5.0,
        tool_calls=tool_calls,
    )

    data = json.loads((tmp_path / "12-test-item.json").read_text())
    call_dict = data["tasks"][0]["tool_calls"][0]
    assert call_dict == {"tool": "Agent"}
    assert "file_path" not in call_dict
    assert "command" not in call_dict
    assert "result_bytes" not in call_dict


# --- tool_use / tool_result pairing tests ---


def test_extract_tool_calls_pairs_result_bytes():
    """tool_use/tool_result pairs should produce correct result_bytes on the record."""
    result_content = "hello world"
    expected_bytes = len(json.dumps(result_content))

    result_json = {
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_01",
                        "name": "Read",
                        "input": {"file_path": "src/bar.py"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_01",
                        "content": result_content,
                    }
                ],
            },
        ]
    }

    records = _extract_tool_calls_from_json_output(result_json)
    assert len(records) == 1
    assert records[0].tool == "Read"
    assert records[0].file_path == "src/bar.py"
    assert records[0].result_bytes == expected_bytes


def test_extract_tool_calls_missing_result_leaves_result_bytes_none():
    """A tool_use with no matching tool_result should leave result_bytes as None."""
    result_json = {
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_99",
                        "name": "Bash",
                        "input": {"command": "ls"},
                    }
                ],
            }
        ]
    }

    records = _extract_tool_calls_from_json_output(result_json)
    assert len(records) == 1
    assert records[0].tool == "Bash"
    assert records[0].command == "ls"
    assert records[0].result_bytes is None


def test_extract_tool_calls_multiple_pairs():
    """Multiple sequential tool calls should all be extracted with correct pairing."""
    result_json = {
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "id_a", "name": "Read",
                     "input": {"file_path": "a.py"}},
                    {"type": "tool_use", "id": "id_b", "name": "Bash",
                     "input": {"command": "echo hi"}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "id_a", "content": "content_a"},
                    {"type": "tool_result", "tool_use_id": "id_b", "content": "content_b"},
                ],
            },
        ]
    }

    records = _extract_tool_calls_from_json_output(result_json)
    assert len(records) == 2
    assert records[0].tool == "Read"
    assert records[0].result_bytes == len(json.dumps("content_a"))
    assert records[1].tool == "Bash"
    assert records[1].result_bytes == len(json.dumps("content_b"))


def test_extract_tool_calls_empty_messages():
    """Empty messages list should return empty tool calls list."""
    records = _extract_tool_calls_from_json_output({"messages": []})
    assert records == []


# --- item slug derivation test ---


def test_item_slug_from_plan_path():
    """Path stem should produce the expected item slug."""
    plan_path = ".claude/plans/12-structured-execution-cost-log-and-analysis.yaml"
    slug = Path(plan_path).stem
    assert slug == "12-structured-execution-cost-log-and-analysis"


def test_item_slug_from_plan_path_with_directory_components():
    """Stem extraction should ignore directory components and extension."""
    plan_path = "/some/nested/dir/07-my-feature.yaml"
    slug = Path(plan_path).stem
    assert slug == "07-my-feature"


# --- _make_tool_call_record field mapping tests ---


def test_make_tool_call_record_read():
    """Read tool input should map file_path field."""
    record = _make_tool_call_record("Read", {"file_path": "src/app.py"})
    assert record.tool == "Read"
    assert record.file_path == "src/app.py"
    assert record.command is None


def test_make_tool_call_record_bash():
    """Bash tool input should map command field."""
    record = _make_tool_call_record("Bash", {"command": "npm test"})
    assert record.tool == "Bash"
    assert record.command == "npm test"
    assert record.file_path is None


def test_make_tool_call_record_grep_uses_path():
    """Grep tool input should map path field to file_path."""
    record = _make_tool_call_record("Grep", {"path": "src/"})
    assert record.tool == "Grep"
    assert record.file_path == "src/"
    assert record.command is None


def test_make_tool_call_record_unknown_tool():
    """Unknown tool should produce record with both optional fields None."""
    record = _make_tool_call_record("Agent", {"subagent_type": "general"})
    assert record.tool == "Agent"
    assert record.file_path is None
    assert record.command is None
