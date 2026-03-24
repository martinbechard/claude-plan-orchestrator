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
from typing import IO, Optional

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

OUTPUT_PREVIEW_MAX_CHARS = 200   # Max chars of Claude text blocks shown inline
TOOL_CMD_PREVIEW_MAX_CHARS = 80  # Max chars of Bash command shown inline

# ─── Constants ────────────────────────────────────────────────────────────────

STRIPPED_ENV_VAR = "CLAUDECODE"  # Removed so child Claude can spawn from Claude Code
DEFAULT_CALL_TIMEOUT_SECONDS = 120


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
) -> str:
    """Call Claude CLI with --print and return the text result.

    Uses subprocess.run to invoke claude --print with JSON output format.
    This is the shared LLM callback used by Slack intake, message routing,
    and Q&A.

    Args:
        prompt: The prompt text to send.
        model: Model name (e.g. "sonnet", "haiku", "claude-opus-4-6").
        timeout: Subprocess timeout in seconds, or None for no timeout.

    Returns:
        The LLM text response, or empty string on failure.
    """
    claude_bin = _find_claude_binary()
    cmd = [
        claude_bin, "--print", prompt,
        "--model", model,
        "--output-format", "json",
        "--dangerously-skip-permissions",
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
            return data.get("result", "").strip()
        logger.warning("claude --print returned code %d: %s", proc.returncode, proc.stderr[:200])
        return ""
    except subprocess.TimeoutExpired:
        logger.warning("claude --print timed out after %ds", timeout)
        return ""
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("claude --print failed: %s", exc)
        return ""


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
) -> None:
    """Stream Claude CLI output in stream-json format, printing tool use and text in real-time.

    Lines are accumulated in collector. When a 'result' event is received,
    result_capture is populated with its fields so the caller can read cost/usage data
    after the thread joins.
    """
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
                    elif block_type == "tool_use":
                        tool_name = block.get("name", "?")
                        tool_input = block.get("input", {})
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

            elif event_type == "result":
                cost = event.get("total_cost_usd", 0)
                duration = event.get("duration_ms", 0) / 1000
                turns = event.get("num_turns", 0)
                print(f"  [{ts}] [Result] {turns} turns, {duration:.1f}s, ${cost:.4f}", flush=True)
                result_capture.update(event)

    except Exception:
        pass  # Streaming errors are non-fatal; caller reads collector for results
