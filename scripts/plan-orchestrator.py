#!/usr/bin/env python3
"""
Plan Orchestrator for Claude Code
Executes implementation plans step-by-step with retry logic and notifications.

Usage:
    python scripts/plan-orchestrator.py [--plan PATH] [--dry-run] [--resume-from TASK_ID]

Copyright (c) 2025 Martin Bechard [martin.bechard@DevConsult.ca]
"""

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

# Configuration
DEFAULT_PLAN_PATH = ".claude/plans/pipeline-optimization.yaml"
STATUS_FILE_PATH = ".claude/plans/task-status.json"
DEFAULT_MAX_ATTEMPTS = 3
CLAUDE_TIMEOUT_SECONDS = 600  # 10 minutes per task


@dataclass
class TaskResult:
    """Result of a task execution."""
    success: bool
    message: str
    duration_seconds: float
    plan_modified: bool = False


def load_plan(plan_path: str) -> dict:
    """Load the YAML plan file."""
    with open(plan_path, "r") as f:
        return yaml.safe_load(f)


def save_plan(plan_path: str, plan: dict, commit: bool = False, commit_message: str = "") -> None:
    """Save the YAML plan file and optionally commit it."""
    with open(plan_path, "w") as f:
        yaml.dump(plan, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    if commit:
        try:
            subprocess.run(
                ["git", "add", plan_path],
                capture_output=True,
                check=True
            )
            msg = commit_message or f"Update plan: {datetime.now().isoformat()}"
            subprocess.run(
                ["git", "commit", "-m", msg],
                capture_output=True,
                check=True
            )
            print(f"[Committed plan changes: {msg}]")
        except subprocess.CalledProcessError as e:
            print(f"[Warning: Failed to commit plan changes: {e}]")


def read_status_file() -> Optional[dict]:
    """Read the status file written by Claude after task completion."""
    if not os.path.exists(STATUS_FILE_PATH):
        return None
    try:
        with open(STATUS_FILE_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def clear_status_file() -> None:
    """Clear the status file before running a task."""
    if os.path.exists(STATUS_FILE_PATH):
        os.remove(STATUS_FILE_PATH)


def find_next_task(plan: dict) -> Optional[tuple[dict, dict]]:
    """Find the next pending task to execute. Returns (section, task) or None."""
    for section in plan.get("sections", []):
        if section.get("status") == "completed":
            continue

        for task in section.get("tasks", []):
            status = task.get("status", "pending")
            if status == "pending":
                return (section, task)
            elif status == "in_progress":
                # Resume in-progress task
                return (section, task)

    return None


def find_task_by_id(plan: dict, task_id: str) -> Optional[tuple[dict, dict]]:
    """Find a specific task by ID. Returns (section, task) or None."""
    for section in plan.get("sections", []):
        for task in section.get("tasks", []):
            if task.get("id") == task_id:
                return (section, task)
    return None


def build_claude_prompt(plan: dict, section: dict, task: dict, plan_path: str) -> str:
    """Build the prompt for Claude to execute a task."""
    plan_doc = plan.get("meta", {}).get("plan_doc", "")

    return f"""Run task {task['id']} from the implementation plan.

## Task Details
- **Section:** {section['name']} ({section['id']})
- **Task:** {task['name']}
- **Description:** {task.get('description', 'No description')}
- **Plan Document:** {plan_doc}
- **YAML Plan File:** {plan_path}

## Instructions
1. First, verify the current state - a previous attempt may have failed
2. Read the relevant section from the plan document for detailed implementation steps
3. Implement the task following the plan's specifications
4. Run `pnpm run build` to verify no TypeScript errors
5. Commit your changes with a descriptive message
6. Write a status file to `.claude/plans/task-status.json` with this format:
   ```json
   {{
     "task_id": "{task['id']}",
     "status": "completed",  // or "failed"
     "message": "Brief description of what was done or what failed",
     "timestamp": "<ISO timestamp>",
     "plan_modified": false  // set to true if you modified the YAML plan
   }}
   ```

## Plan Modification (Optional)
You MAY modify the YAML plan file ({plan_path}) if it makes sense:
- **Split a task** that's too large into smaller subtasks (e.g., 5.2 -> 5.2a, 5.2b)
- **Add a task** if you discover something missing from the plan
- **Update descriptions** to be more accurate based on what you learned
- **Add notes** to tasks with important context
- **Skip a task** by setting status to "skipped" with a reason if it's no longer needed

If you modify the plan, set "plan_modified": true in the status file so the orchestrator reloads it.

IMPORTANT: You MUST write the status file before finishing. This is how the orchestrator knows the task result.
"""


def run_claude_task(prompt: str, dry_run: bool = False) -> TaskResult:
    """Execute a task using Claude CLI."""
    if dry_run:
        print(f"[DRY RUN] Would execute:\n{prompt[:200]}...")
        return TaskResult(success=True, message="Dry run", duration_seconds=0)

    start_time = time.time()

    try:
        # Run claude with bypass permissions and print mode
        result = subprocess.run(
            [
                "claude",
                "--dangerously-skip-permissions",
                "--print",
                prompt
            ],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT_SECONDS,
            cwd=os.getcwd()
        )

        duration = time.time() - start_time

        if result.returncode != 0:
            return TaskResult(
                success=False,
                message=f"Claude exited with code {result.returncode}: {result.stderr[:500]}",
                duration_seconds=duration
            )

        # Check the status file for task result
        status = read_status_file()
        plan_modified = status.get("plan_modified", False) if status else False

        if status and status.get("status") == "completed":
            return TaskResult(
                success=True,
                message=status.get("message", "Task completed"),
                duration_seconds=duration,
                plan_modified=plan_modified
            )
        elif status and status.get("status") == "failed":
            return TaskResult(
                success=False,
                message=status.get("message", "Task failed"),
                duration_seconds=duration,
                plan_modified=plan_modified
            )
        else:
            # No status file or unclear status - check if build passes
            return TaskResult(
                success=False,
                message="No status file written by Claude",
                duration_seconds=duration
            )

    except subprocess.TimeoutExpired:
        return TaskResult(
            success=False,
            message=f"Task timed out after {CLAUDE_TIMEOUT_SECONDS} seconds",
            duration_seconds=CLAUDE_TIMEOUT_SECONDS
        )
    except Exception as e:
        return TaskResult(
            success=False,
            message=f"Error running Claude: {str(e)}",
            duration_seconds=time.time() - start_time
        )


def send_notification(plan: dict, subject: str, message: str) -> None:
    """Send a notification via Claude."""
    email = plan.get("meta", {}).get("notification_email", "")
    if not email:
        print(f"[NOTIFICATION] {subject}: {message}")
        return

    notification_prompt = f"""Send a notification to the user.

Subject: {subject}
Message: {message}

Use the admin notification system or console log if notifications aren't configured.
"""

    try:
        subprocess.run(
            ["claude", "--dangerously-skip-permissions", "--print", notification_prompt],
            capture_output=True,
            text=True,
            timeout=60
        )
    except Exception as e:
        print(f"[NOTIFICATION FAILED] {subject}: {message} (Error: {e})")


def update_section_status(section: dict) -> None:
    """Update section status based on task statuses."""
    tasks = section.get("tasks", [])
    if not tasks:
        return

    statuses = [t.get("status") for t in tasks]

    if all(s == "completed" for s in statuses):
        section["status"] = "completed"
    elif any(s == "in_progress" for s in statuses):
        section["status"] = "in_progress"
    elif any(s == "failed" for s in statuses):
        section["status"] = "failed"
    elif all(s == "pending" for s in statuses):
        section["status"] = "pending"
    else:
        section["status"] = "in_progress"


def run_orchestrator(
    plan_path: str,
    dry_run: bool = False,
    resume_from: Optional[str] = None,
    single_task: bool = False
) -> None:
    """Main orchestrator loop."""
    plan = load_plan(plan_path)
    meta = plan.get("meta", {})
    default_max_attempts = meta.get("max_attempts_default", DEFAULT_MAX_ATTEMPTS)

    print(f"=== Plan Orchestrator ===")
    print(f"Plan: {meta.get('name', 'Unknown')}")
    print(f"Max attempts per task: {default_max_attempts}")
    print(f"Dry run: {dry_run}")
    print()

    # Find starting point
    if resume_from:
        result = find_task_by_id(plan, resume_from)
        if not result:
            print(f"Error: Task {resume_from} not found in plan")
            sys.exit(1)
        section, task = result
        # Reset task status if resuming
        task["status"] = "pending"
        task["attempts"] = 0

    tasks_completed = 0
    tasks_failed = 0

    while True:
        # Find next task
        result = find_next_task(plan)
        if not result:
            print("\n=== All tasks completed! ===")
            send_notification(
                plan,
                "Plan Completed",
                f"All tasks in '{meta.get('name')}' have been completed. "
                f"Completed: {tasks_completed}, Failed: {tasks_failed}"
            )
            break

        section, task = result
        task_id = task.get("id")
        max_attempts = task.get("max_attempts", default_max_attempts)
        current_attempts = task.get("attempts", 0)

        print(f"\n--- Task {task_id}: {task.get('name')} ---")
        print(f"Section: {section.get('name')}")
        print(f"Attempt: {current_attempts + 1}/{max_attempts}")

        if current_attempts >= max_attempts:
            print(f"Max attempts ({max_attempts}) reached for task {task_id}")
            task["status"] = "failed"
            tasks_failed += 1

            send_notification(
                plan,
                f"Task Failed: {task_id}",
                f"Task '{task.get('name')}' failed after {max_attempts} attempts. "
                f"Manual intervention required."
            )

            if not dry_run:
                save_plan(
                    plan_path, plan,
                    commit=True,
                    commit_message=f"plan: Task {task_id} failed after {max_attempts} attempts"
                )
            continue

        # Mark as in progress
        task["status"] = "in_progress"
        task["attempts"] = current_attempts + 1
        task["last_attempt"] = datetime.now().isoformat()
        if not dry_run:
            save_plan(plan_path, plan)  # Don't commit in_progress state

        # Clear previous status file
        clear_status_file()

        # Build and execute prompt
        prompt = build_claude_prompt(plan, section, task, plan_path)
        task_result = run_claude_task(prompt, dry_run=dry_run)

        print(f"Result: {'SUCCESS' if task_result.success else 'FAILED'}")
        print(f"Duration: {task_result.duration_seconds:.1f}s")
        print(f"Message: {task_result.message}")

        # Check if Claude modified the plan
        if task_result.plan_modified:
            print("[Plan was modified by Claude - reloading]")
            plan = load_plan(plan_path)
            meta = plan.get("meta", {})
            # Re-find the task in the reloaded plan
            task_lookup = find_task_by_id(plan, task_id)
            if task_lookup:
                section, task = task_lookup

        if task_result.success:
            task["status"] = "completed"
            task["completed_at"] = datetime.now().isoformat()
            task["result_message"] = task_result.message
            tasks_completed += 1

            # Check if section is complete
            update_section_status(section)
            if section.get("status") == "completed":
                print(f"\n=== Section {section.get('id')} completed! ===")
                send_notification(
                    plan,
                    f"Section Completed: {section.get('name')}",
                    f"All tasks in section '{section.get('name')}' have been completed successfully."
                )
        else:
            task["status"] = "pending"  # Will retry
            task["last_error"] = task_result.message

        # Save and commit on success or if Claude modified the plan
        if not dry_run:
            should_commit = task_result.success or task_result.plan_modified
            commit_msg = f"plan: Task {task_id} {'completed' if task_result.success else 'updated'}"
            save_plan(plan_path, plan, commit=should_commit, commit_message=commit_msg)

        if single_task:
            print("\n[Single task mode - stopping]")
            break

        # Small delay between tasks
        if not dry_run:
            time.sleep(2)

    print(f"\n=== Summary ===")
    print(f"Tasks completed: {tasks_completed}")
    print(f"Tasks failed: {tasks_failed}")


def main():
    parser = argparse.ArgumentParser(
        description="Execute implementation plans step-by-step with Claude"
    )
    parser.add_argument(
        "--plan",
        default=DEFAULT_PLAN_PATH,
        help=f"Path to YAML plan file (default: {DEFAULT_PLAN_PATH})"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be executed without running"
    )
    parser.add_argument(
        "--resume-from",
        metavar="TASK_ID",
        help="Resume from a specific task ID (e.g., '5.2')"
    )
    parser.add_argument(
        "--single-task",
        action="store_true",
        help="Run only one task then stop"
    )

    args = parser.parse_args()

    if not os.path.exists(args.plan):
        print(f"Error: Plan file not found: {args.plan}")
        sys.exit(1)

    run_orchestrator(
        plan_path=args.plan,
        dry_run=args.dry_run,
        resume_from=args.resume_from,
        single_task=args.single_task
    )


if __name__ == "__main__":
    main()
