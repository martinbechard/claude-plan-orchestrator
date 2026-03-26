# langgraph_pipeline/executor/nodes/task_runner.py
# execute_task LangGraph node: spawns Claude CLI to execute a plan task.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""execute_task node for the executor StateGraph.

Loads the agent definition for the current task, builds a prompt, spawns
Claude CLI as a subprocess (streaming output in real-time), parses token
usage, updates the plan YAML task status, git-commits on success, and calls
interrupt() when the agent requests Slack-based suspension.
"""

import json
import os
import subprocess
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from langgraph.types import interrupt

from langgraph_pipeline.executor.circuit_breaker import record_failure, reset_failures
from langgraph_pipeline.executor.state import TaskResult, TaskState
from langgraph_pipeline.shared.quota import detect_quota_exhaustion
from langgraph_pipeline.shared.langsmith import add_trace_metadata, emit_tool_call_traces
from langgraph_pipeline.shared.claude_cli import (
    OutputCollector,
    ToolCallRecord,
    stream_json_output,
    stream_output,
)
from langgraph_pipeline.shared.config import load_orchestrator_config
from langgraph_pipeline.shared.git import git_commit_files
from langgraph_pipeline.shared.paths import STATUS_FILE_PATH, TASK_LOG_DIR
from langgraph_pipeline.shared.suspension import create_suspension_marker

# ─── Constants ────────────────────────────────────────────────────────────────

import logging

CLAUDE_TIMEOUT_SECONDS = 900      # 15 minutes per task
DEFAULT_AGENTS_DIR = ".claude/agents"
DEFAULT_BUILD_COMMAND = "pnpm run build"
DEFAULT_DEV_SERVER_PORT = 3000
DEFAULT_DEV_SERVER_COMMAND = "pnpm dev"
STRIPPED_ENV_VAR = "CLAUDECODE"   # removed so Claude can spawn from Claude Code
COST_API_TIMEOUT_S = 10           # timeout for POST /api/cost

logger = logging.getLogger(__name__)

# Status values the agent writes to task-status.json
_STATUS_COMPLETED = "completed"
_STATUS_FAILED = "failed"
_STATUS_SUSPENDED = "suspended"

# Maps ModelTier literals to full Claude CLI model identifiers
MODEL_TIER_TO_CLI_NAME: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

# ─── Agent Loading ────────────────────────────────────────────────────────────


def _parse_agent_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from an agent markdown file.

    Returns (frontmatter_dict, body_string). Returns ({}, content) when no
    valid frontmatter block is found.
    """
    parts = content.split("---", 2)
    if len(parts) < 3 or parts[0].strip():
        return ({}, content)
    try:
        frontmatter = yaml.safe_load(parts[1])
        if not isinstance(frontmatter, dict):
            return ({}, content)
        return (frontmatter, parts[2].lstrip("\n"))
    except yaml.YAMLError:
        return ({}, content)


def _load_agent_definition(agent_name: str, agents_dir: str) -> Optional[dict]:
    """Load agent metadata and body from the agents directory.

    Returns a dict with name, model, body keys, or None if the file is missing
    or cannot be parsed.
    """
    agent_path = os.path.join(agents_dir, f"{agent_name}.md")
    if not os.path.isfile(agent_path):
        print(f"[execute_task] Agent definition not found: {agent_path}")
        return None
    try:
        with open(agent_path) as f:
            content = f.read()
        frontmatter, body = _parse_agent_frontmatter(content)
        return {
            "name": frontmatter.get("name", agent_name),
            "model": frontmatter.get("model", ""),
            "body": body,
        }
    except Exception as exc:
        print(f"[execute_task] Failed to load agent '{agent_name}': {exc}")
        return None


# ─── Plan Helpers ─────────────────────────────────────────────────────────────


def _find_task_by_id(plan_data: dict, task_id: str) -> Optional[dict]:
    """Return the task dict with the given id, searching all sections."""
    for section in plan_data.get("sections", []):
        for task in section.get("tasks", []):
            if task.get("id") == task_id:
                return task
    return None


def _find_section_for_task(plan_data: dict, task_id: str) -> Optional[dict]:
    """Return the section dict that contains the task with the given id."""
    for section in plan_data.get("sections", []):
        for task in section.get("tasks", []):
            if task.get("id") == task_id:
                return section
    return None


def _save_plan_yaml(plan_path: str, plan_data: dict) -> None:
    """Write the plan dict back to disk in YAML format."""
    with open(plan_path, "w") as f:
        yaml.dump(plan_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


# ─── Prompt Building ──────────────────────────────────────────────────────────


def _build_prompt(
    plan_data: dict,
    section: dict,
    task: dict,
    plan_path: str,
    task_attempt: int,
    build_command: str,
    agents_dir: str,
) -> str:
    """Build the Claude CLI prompt string for a task execution.

    Prepends the agent body (if found), any previous validation findings, and
    structured task details with attempt-aware start instructions.
    """
    plan_doc = plan_data.get("meta", {}).get("plan_doc", "")
    agent_name = task.get("agent", "coder")
    agent_def = _load_agent_definition(agent_name, agents_dir)

    agent_content = ""
    if agent_def and agent_def["body"]:
        agent_content = agent_def["body"] + "\n\n---\n\n"

    validation_findings = task.get("validation_findings", "")
    validation_header = ""
    if validation_findings:
        validation_header = (
            "## PREVIOUS VALIDATION FAILED\n\n"
            "The previous attempt at this task was completed but failed validation.\n"
            "You must address these findings:\n\n"
            f"{validation_findings}\n\n---\n\n"
        )

    if task_attempt >= 2:
        start_instruction = (
            f"1. This is attempt {task_attempt}. A previous attempt failed. "
            "Check the current state before proceeding - some work may already be done."
        )
    else:
        start_instruction = (
            "1. This is a fresh start (attempt 1). The task shows as in_progress because "
            "the orchestrator assigned it to you. Start working immediately on the task."
        )

    return (
        f"{agent_content}{validation_header}"
        f"Run task {task['id']} from the implementation plan.\n\n"
        "## Task Details\n"
        f"- **Section:** {section['name']} ({section['id']})\n"
        f"- **Task:** {task['name']}\n"
        f"- **Description:** {task.get('description', 'No description')}\n"
        f"- **Plan Document:** {plan_doc}\n"
        f"- **YAML Plan File:** {plan_path}\n\n"
        "## Instructions\n"
        f"{start_instruction}\n"
        "2. Read the relevant section from the plan document for detailed implementation steps\n"
        "3. Implement the task following the plan's specifications\n"
        f"4. Run `{build_command}` to verify no build errors\n"
        "5. If you changed middleware, layout files, or auth-related code: run "
        "`npx playwright test tests/SMOKE01-critical-paths.spec.ts --reporter=list` "
        "to verify critical paths\n"
        "6. Commit your changes with a descriptive message\n"
        f"6. Write a status file to `{STATUS_FILE_PATH}` with this format:\n"
        "   ```json\n"
        "   {\n"
        f'     "task_id": "{task["id"]}",\n'
        '     "status": "completed",  // or "failed"\n'
        '     "message": "Brief description of what was done or what failed",\n'
        '     "timestamp": "<ISO timestamp>",\n'
        '     "plan_modified": false  // set to true if you modified the YAML plan\n'
        "   }\n"
        "   ```\n\n"
        "## Plan Modification (Optional)\n"
        f"You MAY modify the YAML plan file ({plan_path}) if it makes sense:\n"
        "- **Split a task** that's too large into smaller subtasks (e.g., 5.2 -> 5.2a, 5.2b)\n"
        "- **Add a task** if you discover something missing from the plan\n"
        "- **Update descriptions** to be more accurate based on what you learned\n"
        "- **Add notes** to tasks with important context\n"
        "- **Skip a task** by setting status to \"skipped\" with a reason if it's no longer needed\n\n"
        "If you modify the plan, set \"plan_modified\": true in the status file so the "
        "orchestrator reloads it.\n\n"
        "IMPORTANT: You MUST write the status file before finishing. This is how the "
        "orchestrator knows the task result.\n"
    )


# ─── Claude CLI Execution ─────────────────────────────────────────────────────


def _build_child_env() -> dict:
    """Return environment dict with CLAUDECODE stripped for child Claude processes."""
    env = os.environ.copy()
    env.pop(STRIPPED_ENV_VAR, None)
    return env


def _write_task_log(
    result_capture: dict,
    stdout_text: str,
    stderr_text: str,
    duration: float,
    returncode: int,
) -> None:
    """Save Claude output and usage stats to a timestamped log file."""
    try:
        TASK_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = TASK_LOG_DIR / f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
        with open(log_path, "w") as f:
            f.write("=== Claude Task Output ===\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Duration: {duration:.1f}s\n")
            f.write(f"Return code: {returncode}\n")
            if result_capture:
                cost = result_capture.get("total_cost_usd", 0)
                usage = result_capture.get("usage", {})
                f.write(f"Cost: ${cost:.4f}\n")
                f.write(
                    f"Tokens: {usage.get('input_tokens', 0)} input / "
                    f"{usage.get('output_tokens', 0)} output\n"
                )
            f.write("\n=== STDOUT ===\n")
            f.write(stdout_text)
            f.write("\n=== STDERR ===\n")
            f.write(stderr_text)
        print(f"[execute_task] Log: {log_path}")
    except Exception as exc:
        print(f"[execute_task] Failed to write task log: {exc}")


def _run_claude(prompt: str, model_cli_name: str) -> tuple[bool, int, dict, str, str, list[ToolCallRecord]]:
    """Spawn Claude CLI and stream its output in real-time.

    Returns (success, returncode, result_capture, stdout_text, stderr_text, tool_calls).
    success is True when Claude exits with return code 0.
    returncode is process.returncode on normal exit, -1 on TimeoutExpired, -2 on Exception.
    result_capture holds the parsed 'result' JSON event with usage data.
    tool_calls accumulates ToolCallRecord entries from each tool_use and text event.
    """
    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--verbose",
        "--model", model_cli_name,
        "--print", prompt,
    ]
    stdout_collector = OutputCollector()
    stderr_collector = OutputCollector()
    result_capture: dict = {}
    tool_calls: list[ToolCallRecord] = []

    start_time = time.time()
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.getcwd(),
            env=_build_child_env(),
        )
        stdout_thread = threading.Thread(
            target=stream_json_output,
            args=(process.stdout, stdout_collector, result_capture, tool_calls),
        )
        stderr_thread = threading.Thread(
            target=stream_output,
            args=(process.stderr, "ERR", stderr_collector, True),
        )
        stdout_thread.start()
        stderr_thread.start()

        while process.poll() is None:
            time.sleep(1)
            if time.time() - start_time > CLAUDE_TIMEOUT_SECONDS:
                process.terminate()
                process.wait(timeout=5)
                raise subprocess.TimeoutExpired(cmd, CLAUDE_TIMEOUT_SECONDS)

        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        duration = time.time() - start_time
        _write_task_log(
            result_capture=result_capture,
            stdout_text=stdout_collector.get_output(),
            stderr_text=stderr_collector.get_output(),
            duration=duration,
            returncode=process.returncode,
        )
        return (
            process.returncode == 0,
            process.returncode,
            result_capture,
            stdout_collector.get_output(),
            stderr_collector.get_output(),
            tool_calls,
        )

    except subprocess.TimeoutExpired:
        print(f"[execute_task] Claude CLI timed out after {CLAUDE_TIMEOUT_SECONDS}s")
        return (False, -1, {}, "", "Timed out", [])
    except Exception as exc:
        print(f"[execute_task] Failed to spawn Claude CLI: {exc}")
        return (False, -2, {}, "", str(exc), [])


# ─── Cost Reporting ───────────────────────────────────────────────────────────


def _tool_call_to_dict(tc: ToolCallRecord) -> dict:
    """Convert a ToolCallRecord to a ToolCallEntry dict for the cost API.

    Derives file_path from tool_input for file-oriented tools and command for
    Bash, mirroring the field-mapping logic in proxy.get_tool_call_attribution().
    """
    tool_name = tc["tool_name"]
    tool_input = tc.get("tool_input") or {}
    file_path: Optional[str] = None
    command: Optional[str] = None
    if tool_name in ("Read", "Edit", "Write"):
        file_path = tool_input.get("file_path")
    elif tool_name in ("Grep", "Glob"):
        file_path = tool_input.get("path")
    elif tool_name == "Bash":
        command = tool_input.get("command")
    entry: dict = {"tool": tool_name}
    if file_path is not None:
        entry["file_path"] = file_path
    if command is not None:
        entry["command"] = command
    result_bytes = tc.get("result_bytes")
    if result_bytes is not None:
        entry["result_bytes"] = result_bytes
    return entry


def _post_cost_to_api(
    plan_data: dict,
    task_id: str,
    agent_type: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    duration_s: float,
    tool_calls: list[ToolCallRecord],
) -> None:
    """POST a per-task cost record to {LANGCHAIN_ENDPOINT}/api/cost.

    Only posts when LANGCHAIN_ENDPOINT is set to a localhost URL.
    Fire-and-forget: logs a warning on error but never raises.
    """
    endpoint = os.environ.get("LANGCHAIN_ENDPOINT", "")
    if not endpoint.startswith("http://localhost"):
        return

    source_item = plan_data.get("meta", {}).get("source_item", "")
    item_slug = Path(source_item).stem if source_item else ""
    item_type = "defect" if source_item and "defect" in source_item.lower() else "feature"

    tool_call_dicts = [
        _tool_call_to_dict(tc)
        for tc in tool_calls
        if tc.get("type") == "tool_use"
    ]

    payload = {
        "item_slug": item_slug,
        "item_type": item_type,
        "task_id": task_id,
        "agent_type": agent_type,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "duration_s": round(duration_s, 1),
        "tool_calls": tool_call_dicts,
    }

    url = f"{endpoint}/api/cost"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=COST_API_TIMEOUT_S):
            pass
    except Exception as exc:
        logger.warning("[execute_task] Failed to POST cost to %s: %s", url, exc)


# ─── Status File ──────────────────────────────────────────────────────────────


def _read_status_file() -> Optional[dict]:
    """Read and parse the task-status.json written by Claude after task completion."""
    if not os.path.exists(STATUS_FILE_PATH):
        return None
    try:
        with open(STATUS_FILE_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


# ─── Dev Server Management ───────────────────────────────────────────────────


def _stop_dev_server(port: int) -> None:
    """Kill any process listening on the configured dev server port.

    Uses lsof to find the PID and sends SIGTERM. Non-fatal if nothing
    is running on the port or if the kill fails.
    """
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5,
        )
        pids = result.stdout.strip()
        if not pids:
            return
        for pid in pids.splitlines():
            pid = pid.strip()
            if pid:
                subprocess.run(["kill", pid], capture_output=True, timeout=5)
        logger.info("Stopped dev server on port %d (PIDs: %s)", port, pids.replace("\n", ", "))
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("Could not stop dev server on port %d: %s", port, exc)


def _start_dev_server(command: str, port: int) -> None:
    """Start the dev server in the background.

    Spawns the command as a detached subprocess. Non-fatal if the command
    fails to start.
    """
    try:
        subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info("Started dev server: %s (port %d)", command, port)
    except OSError as exc:
        logger.warning("Could not start dev server: %s", exc)


# ─── Node ─────────────────────────────────────────────────────────────────────


def execute_task(state: TaskState) -> dict:
    """LangGraph node: execute the current task via Claude CLI.

    Sequence:
    1. Resolve the current task and section from state.
    2. Mark the task in_progress in the plan YAML.
    3. Build the prompt using the agent definition.
    4. Spawn Claude CLI and stream output.
    5. Parse token usage and read the status file.
    6. Update plan YAML: completed on success, failed on failure.
    7. Git-commit the plan YAML update on success.
    8. Call interrupt() if Claude requested Slack suspension.

    Returns a partial state dict with updated task_results, cost accumulators,
    consecutive_failures, and plan_data.
    """
    task_id = state["current_task_id"]
    if task_id is None:
        print("[execute_task] No current_task_id in state; nothing to run")
        add_trace_metadata({
            "node_name": "execute_task",
            "graph_level": "executor",
            "claude_invoked": False,
            "skip_reason": "no_current_task_id",
        })
        return {}

    plan_data: dict = state["plan_data"]
    plan_path: str = state["plan_path"]
    task_attempt: int = state.get("task_attempt") or 1
    effective_model: str = state.get("effective_model") or "sonnet"

    task = _find_task_by_id(plan_data, task_id)
    section = _find_section_for_task(plan_data, task_id)

    if task is None or section is None:
        print(f"[execute_task] Task {task_id!r} not found in plan_data")
        add_trace_metadata({
            "node_name": "execute_task",
            "graph_level": "executor",
            "task_id": task_id,
            "claude_invoked": False,
            "skip_reason": "task_not_found_in_plan",
        })
        failure_count = record_failure(state.get("consecutive_failures") or 0)
        return {
            "consecutive_failures": failure_count,
            "task_results": [
                TaskResult(
                    task_id=task_id,
                    status="failed",
                    model=effective_model,
                    cost_usd=0.0,
                    input_tokens=0,
                    output_tokens=0,
                    message=f"Task {task_id!r} not found in plan_data",
                )
            ],
        }

    # Mark in_progress and persist to disk so other processes see the lock
    task["status"] = "in_progress"
    task["last_attempt"] = datetime.now().isoformat()
    task["attempts"] = (task.get("attempts") or 0) + 1
    task["model_used"] = effective_model
    _save_plan_yaml(plan_path, plan_data)

    # Build prompt
    config = load_orchestrator_config()
    build_command = config.get("build_command", DEFAULT_BUILD_COMMAND)
    agents_dir = config.get("agents_dir", DEFAULT_AGENTS_DIR)
    dev_server_port = int(config.get("dev_server_port", DEFAULT_DEV_SERVER_PORT))
    dev_server_command = config.get("dev_server_command", DEFAULT_DEV_SERVER_COMMAND)
    prompt = _build_prompt(plan_data, section, task, plan_path, task_attempt, build_command, agents_dir)

    # Map tier to full model name for --model flag
    model_cli_name = MODEL_TIER_TO_CLI_NAME.get(effective_model, effective_model)
    print(f"[execute_task] Running task {task_id!r} with model {model_cli_name!r}")

    # Stop dev server before task execution to avoid cache/runtime conflicts
    _stop_dev_server(dev_server_port)

    # Execute Claude CLI
    _exec_start = time.time()
    cli_success, returncode, result_capture, _stdout, _stderr, tool_calls = _run_claude(prompt, model_cli_name)
    _duration_ms = int((time.time() - _exec_start) * 1000)

    # Detect quota exhaustion before processing outcome.
    # Only check stderr — stdout contains Claude's response which may include
    # rate-limit keywords literally when the work item discusses them.
    if detect_quota_exhaustion(_stderr):
        print(f"[execute_task] Quota exhaustion detected for task {task_id!r}; resetting to pending")
        task["status"] = "pending"
        _save_plan_yaml(plan_path, plan_data)
        add_trace_metadata({
            "node_name": "execute_task",
            "graph_level": "executor",
            "task_id": task_id,
            "claude_invoked": False,
            "skip_reason": "quota_exhausted",
            "quota_exhausted": True,
        })
        return {"quota_exhausted": True, "plan_data": plan_data}

    # Parse usage data
    cost_usd = float(result_capture.get("total_cost_usd", 0.0))
    usage = result_capture.get("usage", {})
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))

    # Post cost record to the web API (fire-and-forget)
    _post_cost_to_api(
        plan_data=plan_data,
        task_id=task_id,
        agent_type=task.get("agent", "coder"),
        model=model_cli_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        duration_s=_duration_ms / 1000.0,
        tool_calls=tool_calls,
    )

    # Read agent's status report
    status_dict = _read_status_file()

    # Determine task outcome
    if cli_success and status_dict and status_dict.get("status") == _STATUS_COMPLETED:
        outcome = _STATUS_COMPLETED
        result_message = status_dict.get("message", "Task completed")
    elif status_dict and status_dict.get("status") == _STATUS_SUSPENDED:
        outcome = _STATUS_SUSPENDED
        result_message = status_dict.get("message", "Task suspended")
    elif status_dict and status_dict.get("status") == _STATUS_FAILED:
        outcome = _STATUS_FAILED
        result_message = status_dict.get("message", "Task failed")
    else:
        outcome = _STATUS_FAILED
        result_message = (
            "No status file written by Claude" if not status_dict else "Unknown status"
        )

    # Update plan YAML with outcome
    if outcome == _STATUS_COMPLETED:
        task["status"] = "completed"
        task["completed_at"] = datetime.now().isoformat()
    elif outcome == _STATUS_SUSPENDED:
        task["status"] = "suspended"
        question = status_dict.get("question", "")
        question_context = status_dict.get("question_context", "")
        source_item = plan_data.get("meta", {}).get("source_item", "") if plan_data else ""
        slug = Path(source_item).stem if source_item else ""
        item_type = "defect" if source_item and "defect" in source_item.lower() else "feature"
        if slug and question:
            marker_path = create_suspension_marker(
                slug, item_type, source_item, plan_path, task_id, question, question_context
            )
            logger.info("Suspension marker created: %s", marker_path)
    else:
        task["status"] = "failed"
    task["result_message"] = result_message
    _save_plan_yaml(plan_path, plan_data)

    # Git-commit and reset failures on success; increment on failure
    if outcome == _STATUS_COMPLETED:
        commit_msg = f"plan: Task {task_id} completed\n\n{result_message}"
        git_commit_files([plan_path], commit_msg)
        new_failures = reset_failures()
    elif outcome == _STATUS_SUSPENDED:
        new_failures = state.get("consecutive_failures") or 0
    else:
        new_failures = record_failure(state.get("consecutive_failures") or 0)

    # Restart dev server after task execution
    _start_dev_server(dev_server_command, dev_server_port)

    task_result = TaskResult(
        task_id=task_id,
        status=task["status"],
        model=effective_model,
        cost_usd=cost_usd,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        message=result_message,
    )

    partial_state: dict = {
        "plan_data": plan_data,
        "task_results": [task_result],
        "plan_cost_usd": (state.get("plan_cost_usd") or 0.0) + cost_usd,
        "plan_input_tokens": (state.get("plan_input_tokens") or 0) + input_tokens,
        "plan_output_tokens": (state.get("plan_output_tokens") or 0) + output_tokens,
        "consecutive_failures": new_failures,
    }

    plan_name = plan_data.get("meta", {}).get("name", "")
    emit_tool_call_traces(
        tool_calls,
        f"execute_task:{task_id}",
        {
            "task_id": task_id,
            "model": effective_model,
            "plan_name": plan_name,
        },
        parent_run_id=state.get("langsmith_root_run_id"),
    )

    if returncode == 0:
        failure_reason = "ok"
    elif returncode == -1:
        failure_reason = "timeout"
    else:
        failure_reason = f"exit_code_{returncode}"

    add_trace_metadata({
        "node_name": "execute_task",
        "graph_level": "executor",
        "task_id": task_id,
        "model": effective_model,
        "total_cost_usd": cost_usd,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": _duration_ms,
        "tool_calls_count": len(tool_calls),
        "subprocess_exit_code": returncode,
        "subprocess_error": _stderr[:500] if not cli_success else "",
        "failure_reason": failure_reason,
        "claude_invoked": True,
    })

    # Interrupt the graph for Slack-based human suspension (after state is built)
    if outcome == _STATUS_SUSPENDED:
        print(f"[execute_task] Task {task_id!r} requested suspension: {result_message}")
        interrupt({"task_id": task_id, "message": result_message})

    return partial_state
