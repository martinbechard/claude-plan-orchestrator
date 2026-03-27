# langgraph_pipeline/shared/claude_cli.py
# OutputCollector and subprocess output streaming helpers shared across pipeline scripts.
# Design: docs/plans/2026-02-25-02-extract-shared-modules-design.md

"""OutputCollector class and subprocess output streaming utilities for the Claude CLI."""

import json
import logging
import os
import shutil
import subprocess
from datetime import datetime
from typing import IO, Literal, NamedTuple, NotRequired, Optional, TypedDict

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

OUTPUT_PREVIEW_MAX_CHARS = 200   # Max chars of Claude text blocks shown inline
TOOL_CMD_PREVIEW_MAX_CHARS = 80  # Max chars of Bash command shown inline

# ─── Constants ────────────────────────────────────────────────────────────────

STRIPPED_ENV_VAR = "CLAUDECODE"  # Removed so child Claude can spawn from Claude Code
DEFAULT_CALL_TIMEOUT_SECONDS = 120


# ─── Types ────────────────────────────────────────────────────────────────────


class ClaudeResult(NamedTuple):
    """Return value from call_claude().

    text holds the LLM response on success, or empty string on failure.
    failure_reason holds a descriptive string on failure, or None on success.
    total_cost_usd is the cost reported by the Claude CLI, or 0.0 when unavailable.
    input_tokens / output_tokens are from the usage dict in the JSON response.
    raw_stdout holds the full subprocess stdout for logging/debugging.
    """

    text: str
    failure_reason: Optional[str]
    total_cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    raw_stdout: str = ""


class ToolCallRecord(TypedDict):
    """A single tool call or text event captured during Claude CLI streaming.

    type distinguishes tool invocations from assistant text blocks.
    tool_input holds the raw input dict for tool_use events, or
    {"text": "..."} for text events.
    tool_use_id correlates this record with its tool_result event.
    start_time and duration_s are set when the matching tool_result arrives,
    enabling accurate span widths in LangSmith traces.
    """

    type: Literal["tool_use", "text"]
    tool_name: str
    tool_input: dict
    timestamp: str
    tool_use_id: NotRequired[Optional[str]]
    start_time: NotRequired[Optional[datetime]]
    duration_s: NotRequired[Optional[float]]
    result_bytes: NotRequired[Optional[int]]


# ─── call_claude ─────────────────────────────────────────────────────────────


def _find_claude_binary() -> str:
    """Find the claude CLI binary path."""
    path = shutil.which("claude")
    if path:
        return path
    # Common install locations
    for candidate in ("/usr/local/bin/claude", os.path.expanduser("~/.claude/bin/claude")):
        if os.path.isfile(candidate):
            return candidate
    return "claude"  # Fall back, let subprocess raise if missing


def _build_child_env() -> dict:
    """Return environment dict with CLAUDECODE stripped for child Claude processes."""
    env = os.environ.copy()
    env.pop(STRIPPED_ENV_VAR, None)
    return env


def call_claude(
    prompt: str,
    model: str = "sonnet",
    timeout: Optional[int] = DEFAULT_CALL_TIMEOUT_SECONDS,
) -> ClaudeResult:
    """Call Claude CLI with --print and return a ClaudeResult.

    Uses subprocess.run to invoke claude --print with JSON output format.
    This is the shared LLM callback used by Slack intake, message routing,
    and Q&A.

    Args:
        prompt: The prompt text to send.
        model: Model name (e.g. "sonnet", "haiku", "claude-opus-4-6").
        timeout: Subprocess timeout in seconds, or None for no timeout.

    Returns:
        ClaudeResult with text set on success, or failure_reason set on failure.
    """
    claude_bin = _find_claude_binary()
    cmd = [
        claude_bin, "--print", prompt,
        "--model", model,
        "--output-format", "json",
        "--dangerously-skip-permissions",
        "--permission-mode", "acceptEdits",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
            env=_build_child_env(),
        )
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            cost = float(data.get("total_cost_usd", 0.0))
            usage = data.get("usage", {})
            return ClaudeResult(
                text=data.get("result", "").strip(),
                failure_reason=None,
                total_cost_usd=cost,
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
                raw_stdout=proc.stdout or "",
            )
        reason = f"claude --print returned code {proc.returncode}: {proc.stderr}"
        logger.warning(reason)
        return ClaudeResult(text="", failure_reason=reason, raw_stdout=proc.stdout or "")
    except subprocess.TimeoutExpired:
        reason = f"claude --print timed out after {timeout}s"
        logger.warning(reason)
        return ClaudeResult(text="", failure_reason=reason)
    except json.JSONDecodeError as exc:
        reason = f"claude --print JSON decode error: {exc}"
        logger.warning(reason)
        return ClaudeResult(text="", failure_reason=reason)
    except OSError as exc:
        reason = f"claude --print OS error: {exc}"
        logger.warning(reason)
        return ClaudeResult(text="", failure_reason=reason)


# ─── OutputCollector ──────────────────────────────────────────────────────────


class OutputCollector:
    """Collects output from a subprocess and tracks stats."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.bytes_received: int = 0
        self.line_count: int = 0

    def add_line(self, line: str) -> None:
        self.lines.append(line)
        self.bytes_received += len(line.encode("utf-8"))
        self.line_count += 1

    def get_output(self) -> str:
        return "".join(self.lines)


# ─── Streaming Functions ──────────────────────────────────────────────────────


def stream_output(pipe: IO[str], prefix: str, collector: OutputCollector, show_full: bool) -> None:
    """Stream output from a subprocess pipe line by line.

    Each line is appended to collector. When show_full is True, each line is
    printed to stdout with a timestamp prefix.
    """
    try:
        for line in iter(pipe.readline, ""):
            if line:
                collector.add_line(line)
                if show_full:
                    ts = datetime.now().strftime("%H:%M:%S")
                    print(f"[{ts}] [{prefix}] {line.rstrip()}", flush=True)
    except Exception:
        pass  # Streaming errors are non-fatal; caller reads collector for results


def stream_json_output(
    pipe: IO[str],
    collector: OutputCollector,
    result_capture: dict,
    tool_calls: Optional[list[ToolCallRecord]] = None,
) -> None:
    """Stream Claude CLI output in stream-json format, printing tool use and text in real-time.

    Lines are accumulated in collector. When a 'result' event is received,
    result_capture is populated with its fields so the caller can read cost/usage data
    after the thread joins.

    When tool_calls is provided, each tool_use block and non-empty text block from
    assistant events is appended as a ToolCallRecord for post-hoc LangSmith tracing.
    """
    pending: dict[str, tuple[datetime, ToolCallRecord]] = {}
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                continue
            collector.add_line(line)
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

            event_type = event.get("type", "")
            ts = datetime.now().strftime("%H:%M:%S")

            if event_type == "assistant":
                msg = event.get("message", {})
                for block in msg.get("content", []):
                    block_type = block.get("type", "")
                    if block_type == "text":
                        text = block.get("text", "").strip()
                        if text:
                            display = text[:OUTPUT_PREVIEW_MAX_CHARS] + (
                                "..." if len(text) > OUTPUT_PREVIEW_MAX_CHARS else ""
                            )
                            print(f"  [{ts}] [Claude] {display}", flush=True)
                            if tool_calls is not None:
                                tool_calls.append(ToolCallRecord(
                                    type="text",
                                    tool_name="",
                                    tool_input={"text": text},
                                    timestamp=ts,
                                ))
                    elif block_type == "tool_use":
                        tool_name = block.get("name", "?")
                        tool_input = block.get("input", {})
                        tool_use_id = block.get("id")
                        start_time = datetime.now()
                        if tool_name in ("Read", "Edit", "Write"):
                            detail = tool_input.get("file_path", "")
                        elif tool_name == "Bash":
                            cmd = tool_input.get("command", "")
                            detail = cmd[:TOOL_CMD_PREVIEW_MAX_CHARS] + (
                                "..." if len(cmd) > TOOL_CMD_PREVIEW_MAX_CHARS else ""
                            )
                        elif tool_name in ("Grep", "Glob"):
                            detail = tool_input.get("pattern", "")
                        else:
                            detail = ""
                        print(f"  [{ts}] [Tool] {tool_name}: {detail}", flush=True)
                        if tool_calls is not None:
                            record = ToolCallRecord(
                                type="tool_use",
                                tool_name=tool_name,
                                tool_input=tool_input,
                                timestamp=ts,
                                tool_use_id=tool_use_id,
                                start_time=start_time,
                            )
                            tool_calls.append(record)
                            if tool_use_id:
                                pending[tool_use_id] = (start_time, record)

            elif event_type == "user":
                msg = event.get("message", {})
                for block in msg.get("content", []):
                    if block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id and tool_use_id in pending:
                            start, record = pending.pop(tool_use_id)
                            record["duration_s"] = (datetime.now() - start).total_seconds()
                            content = block.get("content", "")
                            record["result_bytes"] = len(json.dumps(content))

            elif event_type == "result":
                cost = event.get("total_cost_usd", 0)
                duration = event.get("duration_ms", 0) / 1000
                turns = event.get("num_turns", 0)
                print(f"  [{ts}] [Result] {turns} turns, {duration:.1f}s, ${cost:.4f}", flush=True)
                result_capture.update(event)

    except Exception:
        pass  # Streaming errors are non-fatal; caller reads collector for results
