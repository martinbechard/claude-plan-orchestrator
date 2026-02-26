# langgraph_pipeline/executor/nodes/parallel.py
# fan_out, execute_parallel_task, and fan_in LangGraph nodes for parallel worktree execution.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Parallel task execution nodes for the executor StateGraph.

fan_out groups pending tasks by parallel_group, checks exclusive_resource
conflicts to avoid concurrent access to shared resources, and dispatches
each runnable task to execute_parallel_task via LangGraph Send() API.

execute_parallel_task creates an isolated git worktree, runs Claude CLI
inside it, copies non-plan artifacts back to the main working directory,
updates the main plan YAML (thread-safe), and cleans up.

fan_in reloads the plan from disk after all parallel branches complete and
commits the aggregated artifact changes in a single consolidated commit.
"""

import json
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from langgraph.types import Send

from langgraph_pipeline.executor.circuit_breaker import record_failure, reset_failures
from langgraph_pipeline.executor.state import TaskResult, TaskState
from langgraph_pipeline.shared.langsmith import add_trace_metadata
from langgraph_pipeline.shared.claude_cli import (
    OutputCollector,
    stream_json_output,
    stream_output,
)
from langgraph_pipeline.shared.git import (
    cleanup_worktree,
    copy_worktree_artifacts,
    create_worktree,
    git_commit_files,
)
from langgraph_pipeline.shared.paths import STATUS_FILE_PATH  # noqa: F401 (re-exported for tests)

# ─── Constants ────────────────────────────────────────────────────────────────

CLAUDE_TIMEOUT_SECONDS = 900          # 15 minutes per parallel task
DEFAULT_AGENTS_DIR = ".claude/agents"
PENDING_STATUS = "pending"
STRIPPED_ENV_VAR = "CLAUDECODE"       # removed so Claude can spawn from Claude Code

# Status file path relative to either the main repo or a worktree root
WORKTREE_STATUS_FILE_RELATIVE = ".claude/plans/task-status.json"

# Task outcome string constants
_OUTCOME_COMPLETED = "completed"
_OUTCOME_FAILED = "failed"

# Maps ModelTier literals to full Claude CLI model identifiers
MODEL_TIER_TO_CLI_NAME: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

# Terminal statuses used for dependency resolution
_TERMINAL_STATUSES = frozenset({"completed", "failed", "skipped"})

# Thread-safe lock serialising plan YAML reads/writes and git index staging
# from concurrently executing parallel branches.
_PLAN_LOCK = threading.Lock()

# ─── Plan Helpers ─────────────────────────────────────────────────────────────


def _load_plan_yaml(plan_path: str) -> dict:
    """Load and parse YAML plan from disk."""
    with open(plan_path, "r") as f:
        return yaml.safe_load(f) or {}


def _save_plan_yaml(plan_path: str, plan_data: dict) -> None:
    """Write the plan dict back to disk in YAML format."""
    with open(plan_path, "w") as f:
        yaml.dump(plan_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _find_task_by_id(plan_data: dict, task_id: str) -> Optional[dict]:
    """Return the task dict with the given id, searching all sections."""
    for section in plan_data.get("sections", []):
        for task in section.get("tasks", []):
            if task.get("id") == task_id:
                return task
    return None


def _find_section_for_task(plan_data: dict, task_id: str) -> Optional[dict]:
    """Return the section dict containing the task with the given id."""
    for section in plan_data.get("sections", []):
        for task in section.get("tasks", []):
            if task.get("id") == task_id:
                return section
    return None


def _collect_tasks(plan_data: dict) -> list[dict]:
    """Return a flat list of all task dicts from all sections."""
    tasks: list[dict] = []
    for section in plan_data.get("sections", []):
        tasks.extend(section.get("tasks", []))
    return tasks


def _completed_task_ids(all_tasks: list[dict]) -> set[str]:
    """Return the set of task IDs that have reached a terminal status."""
    return {t["id"] for t in all_tasks if t.get("status") in _TERMINAL_STATUSES}


# ─── Parallel Group Helpers ───────────────────────────────────────────────────


def _find_parallel_group_tasks(plan_data: dict, parallel_group: str) -> list[dict]:
    """Return pending, dependency-satisfied tasks belonging to the given parallel_group.

    Args:
        plan_data: Parsed YAML plan dict.
        parallel_group: The group identifier to match against task.parallel_group.

    Returns:
        Tasks in the group whose status is pending and whose dependencies
        are all in a terminal state.
    """
    all_tasks = _collect_tasks(plan_data)
    completed_ids = _completed_task_ids(all_tasks)
    result: list[dict] = []
    for task in all_tasks:
        if task.get("parallel_group") != parallel_group:
            continue
        if task.get("status") != PENDING_STATUS:
            continue
        deps: list[str] = task.get("dependencies") or []
        if all(dep in completed_ids for dep in deps):
            result.append(task)
    return result


def _filter_exclusive_resources(tasks: list[dict]) -> list[dict]:
    """Remove tasks blocked by exclusive_resource conflicts.

    When multiple tasks in a parallel group share the same exclusive_resource
    value, only the first (in declaration order) is included in the runnable
    set.  Remaining tasks stay pending and are picked up in subsequent cycles.

    Args:
        tasks: Candidate parallel tasks after dependency filtering.

    Returns:
        Subset of tasks that can run concurrently without resource conflicts.
    """
    seen: set[str] = set()
    runnable: list[dict] = []
    for task in tasks:
        resource = task.get("exclusive_resource")
        if resource is None:
            runnable.append(task)
        elif resource not in seen:
            seen.add(resource)
            runnable.append(task)
    return runnable


# ─── Prompt Building ──────────────────────────────────────────────────────────


def _build_parallel_prompt(
    plan_data: dict,
    section: dict,
    task: dict,
    plan_path: str,
    task_attempt: int,
) -> str:
    """Build a Claude CLI prompt for a task executing inside a git worktree.

    The prompt mirrors the structure from task_runner._build_prompt but
    instructs Claude to write its status file inside the worktree (relative
    path), since the worktree has the same directory structure as the main repo.
    """
    plan_doc = plan_data.get("meta", {}).get("plan_doc", "")
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
        "4. Commit your changes with a descriptive message\n"
        f"5. Write a status file to `{WORKTREE_STATUS_FILE_RELATIVE}` in this format:\n"
        "   ```json\n"
        "   {\n"
        f'     "task_id": "{task["id"]}",\n'
        '     "status": "completed",  // or "failed"\n'
        '     "message": "Brief description of what was done or what failed",\n'
        '     "timestamp": "<ISO timestamp>"\n'
        "   }\n"
        "   ```\n\n"
        "IMPORTANT: You MUST write the status file before finishing. This is how the "
        "orchestrator knows the task result.\n"
    )


# ─── Claude CLI Execution ─────────────────────────────────────────────────────


def _build_child_env() -> dict:
    """Return environment dict with CLAUDECODE stripped for child Claude processes."""
    env = os.environ.copy()
    env.pop(STRIPPED_ENV_VAR, None)
    return env


def _run_claude_in_worktree(
    prompt: str, model_cli_name: str, worktree_path: Path
) -> tuple[bool, dict]:
    """Spawn Claude CLI inside the given worktree directory and stream output.

    Args:
        prompt: Full text prompt to pass via --print.
        model_cli_name: Full model identifier for the --model flag.
        worktree_path: Absolute path to the git worktree root.

    Returns:
        (success, result_capture) where result_capture holds the parsed
        'result' event with total_cost_usd and usage fields.
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

    start_time = time.time()
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(worktree_path),
            env=_build_child_env(),
        )
        stdout_thread = threading.Thread(
            target=stream_json_output,
            args=(process.stdout, stdout_collector, result_capture),
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

        return (process.returncode == 0, result_capture)

    except subprocess.TimeoutExpired:
        print(f"[execute_parallel_task] Claude CLI timed out after {CLAUDE_TIMEOUT_SECONDS}s")
        return (False, {})
    except Exception as exc:
        print(f"[execute_parallel_task] Failed to spawn Claude CLI: {exc}")
        return (False, {})


# ─── Status File ──────────────────────────────────────────────────────────────


def _read_worktree_status(worktree_path: Path) -> Optional[dict]:
    """Read the task-status.json written by Claude inside the worktree.

    Args:
        worktree_path: Absolute path to the git worktree root.

    Returns:
        Parsed status dict, or None if the file is absent or unreadable.
    """
    status_path = worktree_path / WORKTREE_STATUS_FILE_RELATIVE
    if not status_path.exists():
        return None
    try:
        with open(status_path) as f:
            return json.load(f)
    except Exception:
        return None


# ─── Mark In-Progress Helper ──────────────────────────────────────────────────


def _mark_task_in_progress(plan_path: str, task_id: str, effective_model: str) -> None:
    """Reload plan YAML, mark the task in_progress, and save (caller holds _PLAN_LOCK)."""
    live_plan = _load_plan_yaml(plan_path)
    live_task = _find_task_by_id(live_plan, task_id)
    if live_task:
        live_task["status"] = "in_progress"
        live_task["last_attempt"] = datetime.now().isoformat()
        live_task["attempts"] = (live_task.get("attempts") or 0) + 1
        live_task["model_used"] = effective_model
        _save_plan_yaml(plan_path, live_plan)


def _update_task_outcome(
    plan_path: str, task_id: str, outcome: str, result_message: str
) -> None:
    """Reload plan YAML, update the task outcome, and save (caller holds _PLAN_LOCK)."""
    live_plan = _load_plan_yaml(plan_path)
    live_task = _find_task_by_id(live_plan, task_id)
    if live_task:
        live_task["status"] = outcome
        live_task["result_message"] = result_message
        if outcome == _OUTCOME_COMPLETED:
            live_task["completed_at"] = datetime.now().isoformat()
        _save_plan_yaml(plan_path, live_plan)


# ─── Nodes ────────────────────────────────────────────────────────────────────


def fan_out(state: TaskState) -> list[Send]:
    """LangGraph node: dispatch parallel branch executions via the Send() API.

    Sequence:
    1. Identify the parallel_group of current_task_id.
    2. Collect all pending, dependency-satisfied tasks in that group.
    3. Remove tasks blocked by exclusive_resource conflicts.
    4. Return one Send("execute_parallel_task", branch_state) per runnable task.

    If no runnable tasks are found (all blocked or already complete), returns
    an empty list; LangGraph routes to fan_in with no new branch results.

    Args:
        state: TaskState after find_next_task has set current_task_id.

    Returns:
        List of Send objects dispatching to execute_parallel_task.
    """
    task_id = state.get("current_task_id")
    plan_data: dict = state.get("plan_data") or {}

    if not task_id:
        print("[fan_out] No current_task_id; nothing to dispatch")
        return []

    current_task = _find_task_by_id(plan_data, task_id)
    if current_task is None:
        print(f"[fan_out] Task {task_id!r} not found in plan_data; nothing to dispatch")
        return []

    parallel_group = current_task.get("parallel_group")
    if not parallel_group:
        # No parallel_group -- single branch dispatch
        print(f"[fan_out] Task {task_id!r} has no parallel_group; dispatching as single branch")
        return [Send("execute_parallel_task", dict(state))]

    group_tasks = _find_parallel_group_tasks(plan_data, parallel_group)
    if not group_tasks:
        print(f"[fan_out] No pending eligible tasks in group {parallel_group!r}")
        return []

    runnable = _filter_exclusive_resources(group_tasks)
    deferred = len(group_tasks) - len(runnable)
    if deferred:
        print(
            f"[fan_out] Group {parallel_group!r}: {len(runnable)} runnable, "
            f"{deferred} deferred due to exclusive_resource conflicts"
        )
    else:
        print(f"[fan_out] Dispatching {len(runnable)} tasks from group {parallel_group!r}")

    return [
        Send("execute_parallel_task", {**state, "current_task_id": task["id"]})
        for task in runnable
    ]


def execute_parallel_task(state: TaskState) -> dict:
    """LangGraph node: execute a single task in an isolated git worktree.

    Sequence:
    1. Mark task in_progress in the main plan YAML (thread-safe via _PLAN_LOCK).
    2. Create a git worktree via shared/git.create_worktree.
    3. Run Claude CLI inside the worktree directory.
    4. Read the task-status.json from the worktree.
    5. Copy non-plan artifacts from the worktree to the main directory.
    6. Stage copied artifacts for the fan_in commit (thread-safe via _PLAN_LOCK).
    7. Update the main plan YAML with the task outcome (thread-safe via _PLAN_LOCK).
    8. Clean up the worktree.

    Args:
        state: Branch TaskState with current_task_id set to this task's ID.

    Returns:
        Partial state dict with task_results and updated cost accumulators.
    """
    task_id = state["current_task_id"]
    plan_path: str = state["plan_path"]
    effective_model: str = state.get("effective_model") or "sonnet"
    task_attempt: int = state.get("task_attempt") or 1

    with _PLAN_LOCK:
        plan_data = _load_plan_yaml(plan_path)

    task = _find_task_by_id(plan_data, task_id)
    section = _find_section_for_task(plan_data, task_id)

    if task is None or section is None:
        print(f"[execute_parallel_task] Task {task_id!r} not found in plan")
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
                    message=f"Task {task_id!r} not found in plan",
                )
            ],
        }

    plan_name = plan_data.get("meta", {}).get("name", "plan")

    with _PLAN_LOCK:
        _mark_task_in_progress(plan_path, task_id, effective_model)

    worktree_path = create_worktree(plan_name, task_id)
    if worktree_path is None:
        print(f"[execute_parallel_task] Failed to create worktree for task {task_id!r}")
        with _PLAN_LOCK:
            _update_task_outcome(plan_path, task_id, _OUTCOME_FAILED, "Failed to create git worktree")
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
                    message="Failed to create git worktree",
                )
            ],
        }

    prompt = _build_parallel_prompt(plan_data, section, task, plan_path, task_attempt)
    model_cli_name = MODEL_TIER_TO_CLI_NAME.get(effective_model, effective_model)
    print(
        f"[execute_parallel_task] Running task {task_id!r} in worktree {worktree_path} "
        f"with model {model_cli_name!r}"
    )

    _exec_start = time.time()
    cli_success, result_capture = _run_claude_in_worktree(prompt, model_cli_name, worktree_path)
    _duration_ms = int((time.time() - _exec_start) * 1000)

    cost_usd = float(result_capture.get("total_cost_usd", 0.0))
    usage = result_capture.get("usage", {})
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))

    status_dict = _read_worktree_status(worktree_path)
    if cli_success and status_dict and status_dict.get("status") == _OUTCOME_COMPLETED:
        outcome = _OUTCOME_COMPLETED
        result_message = status_dict.get("message", "Task completed")
    else:
        outcome = _OUTCOME_FAILED
        result_message = (
            "No status file written by Claude"
            if not status_dict
            else status_dict.get("message", "Task failed")
        )

    if outcome == _OUTCOME_COMPLETED:
        copy_success, copy_msg, copied_files = copy_worktree_artifacts(worktree_path, task_id)
        if not copy_success:
            print(f"[execute_parallel_task] Artifact copy failed for {task_id!r}: {copy_msg}")
            outcome = _OUTCOME_FAILED
            result_message = f"Artifact copy failed: {copy_msg}"
        elif copied_files:
            with _PLAN_LOCK:
                subprocess.run(["git", "add"] + copied_files, capture_output=True, check=False)

    cleanup_worktree(worktree_path)

    with _PLAN_LOCK:
        _update_task_outcome(plan_path, task_id, outcome, result_message)

    new_failures = reset_failures() if outcome == _OUTCOME_COMPLETED else record_failure(
        state.get("consecutive_failures") or 0
    )

    add_trace_metadata({
        "node_name": "execute_parallel_task",
        "graph_level": "executor",
        "task_id": task_id,
        "model": effective_model,
        "total_cost_usd": cost_usd,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": _duration_ms,
    })

    return {
        "task_results": [
            TaskResult(
                task_id=task_id,
                status=outcome,
                model=effective_model,
                cost_usd=cost_usd,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                message=result_message,
            )
        ],
        "consecutive_failures": new_failures,
        "plan_cost_usd": (state.get("plan_cost_usd") or 0.0) + cost_usd,
        "plan_input_tokens": (state.get("plan_input_tokens") or 0) + input_tokens,
        "plan_output_tokens": (state.get("plan_output_tokens") or 0) + output_tokens,
    }


def fan_in(state: TaskState) -> dict:
    """LangGraph node: merge parallel branch results and commit aggregated artifacts.

    Called once after all execute_parallel_task branches complete.  Reloads
    plan_data from disk because parallel branches have been updating the YAML
    concurrently.  Stages the plan YAML and commits with a consolidated message
    covering all tasks that completed in this parallel batch.

    The task_results list is already merged by LangGraph via operator.add before
    this node runs, so state.task_results contains results from all branches.

    Args:
        state: Merged TaskState after all parallel branches have completed.

    Returns:
        Partial state dict with refreshed plan_data.
    """
    plan_path: str = state["plan_path"]
    fresh_plan_data = _load_plan_yaml(plan_path)

    task_results: list[TaskResult] = state.get("task_results") or []
    completed_ids = [
        r["task_id"] for r in task_results if r.get("status") == _OUTCOME_COMPLETED
    ]
    print(
        f"[fan_in] {len(task_results)} parallel task(s) finished; "
        f"{len(completed_ids)} completed: {completed_ids}"
    )

    if completed_ids:
        commit_msg = f"plan: Parallel tasks completed: {', '.join(completed_ids)}"
        git_commit_files([plan_path], commit_msg)

    add_trace_metadata({
        "node_name": "fan_in",
        "graph_level": "executor",
        "completed_task_count": len(completed_ids),
        "total_task_count": len(task_results),
    })

    return {"plan_data": fresh_plan_data}
