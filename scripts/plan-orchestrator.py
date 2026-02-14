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
import re
import shutil
import subprocess
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import yaml

# Worktree configuration
WORKTREE_BASE_DIR = ".worktrees"

# Orchestrator project config
ORCHESTRATOR_CONFIG_PATH = ".claude/orchestrator-config.yaml"
DEFAULT_DEV_SERVER_PORT = 3000
DEFAULT_BUILD_COMMAND = "pnpm run build"
DEFAULT_TEST_COMMAND = "pnpm test"
DEFAULT_DEV_SERVER_COMMAND = "pnpm dev"
DEFAULT_AGENTS_DIR = ".claude/agents/"

# Configuration
DEFAULT_PLAN_PATH = ".claude/plans/pipeline-optimization.yaml"
STATUS_FILE_PATH = ".claude/plans/task-status.json"
STOP_SEMAPHORE_PATH = ".claude/plans/.stop"
DEFAULT_MAX_ATTEMPTS = 3
CLAUDE_TIMEOUT_SECONDS = 600  # 10 minutes per task


def load_orchestrator_config() -> dict:
    """Load project-level orchestrator config from .claude/orchestrator-config.yaml.

    Returns the parsed dict, or an empty dict if the file doesn't exist.
    """
    try:
        with open(ORCHESTRATOR_CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)
        return config if isinstance(config, dict) else {}
    except (IOError, yaml.YAMLError):
        return {}


_config = load_orchestrator_config()
DEV_SERVER_PORT = int(_config.get("dev_server_port", DEFAULT_DEV_SERVER_PORT))
BUILD_COMMAND = _config.get("build_command", DEFAULT_BUILD_COMMAND)
TEST_COMMAND = _config.get("test_command", DEFAULT_TEST_COMMAND)
DEV_SERVER_COMMAND = _config.get("dev_server_command", DEFAULT_DEV_SERVER_COMMAND)
AGENTS_DIR = _config.get("agents_dir", DEFAULT_AGENTS_DIR)

def parse_agent_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from an agent definition markdown file.

    Splits the content on '---' delimiters to extract the YAML frontmatter
    block. The frontmatter must appear at the very start of the file,
    enclosed between two '---' lines.

    Returns a tuple of (frontmatter_dict, body_string). If no valid
    frontmatter is found, returns ({}, content).
    """
    parts = content.split("---", 2)
    if len(parts) < 3 or parts[0].strip():
        # No valid frontmatter: either fewer than 3 parts after splitting,
        # or non-empty content before the first '---'
        return ({}, content)

    try:
        frontmatter = yaml.safe_load(parts[1])
        if not isinstance(frontmatter, dict):
            return ({}, content)
        body = parts[2].lstrip("\n")
        return (frontmatter, body)
    except yaml.YAMLError:
        return ({}, content)


def load_agent_definition(agent_name: str) -> Optional[dict]:
    """Load and parse an agent definition file from the agents directory.

    Takes an agent name (e.g. 'coder') and reads the corresponding markdown
    file from AGENTS_DIR. Parses the YAML frontmatter for metadata (name,
    description, tools, model) and returns a dict with the full content and
    parsed fields.

    Returns None if the file does not exist or cannot be parsed.
    """
    agent_path = os.path.join(AGENTS_DIR, f"{agent_name}.md")

    if not os.path.isfile(agent_path):
        print(f"[WARNING] Agent definition not found: {agent_path}")
        return None

    try:
        with open(agent_path, "r") as f:
            content = f.read()

        frontmatter, body = parse_agent_frontmatter(content)

        return {
            "name": frontmatter.get("name", agent_name),
            "description": frontmatter.get("description", ""),
            "tools": frontmatter.get("tools", []),
            "model": frontmatter.get("model", ""),
            "content": content,
            "body": body,
        }
    except Exception as e:
        print(f"[WARNING] Failed to load agent definition '{agent_name}': {e}")
        return None


# Keywords in task descriptions that indicate a review/verification task.
# When infer_agent_for_task() matches any of these in the description,
# it selects the "code-reviewer" agent instead of the default "coder".
REVIEWER_KEYWORDS = [
    "verify", "review", "check", "validate", "regression", "compliance"
]

# Regex patterns for parsing validation verdicts from validator agent output.
# Matches structured output like: **Verdict: PASS**
VERDICT_PATTERN = re.compile(
    r"\*\*Verdict:\s*(PASS|WARN|FAIL)\*\*", re.IGNORECASE
)

# Matches individual finding lines like: - [FAIL] Build failed at line 42
FINDING_PATTERN = re.compile(
    r"- \[(PASS|WARN|FAIL)\]\s+(.+)", re.IGNORECASE
)


def infer_agent_for_task(task: dict) -> Optional[str]:
    """Infer which agent should execute a task based on its description keywords.

    Scans the task description for keywords associated with review/verification
    work. If any REVIEWER_KEYWORDS are found, returns "code-reviewer". Otherwise
    returns the default "coder" agent.

    Returns None if the agents directory (AGENTS_DIR) does not exist, which
    preserves backward compatibility for projects that have not adopted agents.
    """
    if not os.path.isdir(AGENTS_DIR):
        return None

    description = task.get("description", "").lower()

    for keyword in REVIEWER_KEYWORDS:
        if keyword in description:
            return "code-reviewer"

    return "coder"


# Known locations for the claude binary
CLAUDE_BINARY_SEARCH_PATHS = [
    "/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/cli.js",
    "/usr/local/lib/node_modules/@anthropic-ai/claude-code/cli.js",
]

# Rate limit detection
RATE_LIMIT_DEFAULT_WAIT_SECONDS = 3600  # 1 hour fallback if we can't parse reset time
RATE_LIMIT_PATTERN = re.compile(
    r"(?:You've hit your limit|you've hit your limit|Usage limit reached)"
    r".*?resets?\s+(\w+\s+\d{1,2})\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?)"
    r"(?:\s*\(([^)]+)\))?",
    re.IGNORECASE | re.DOTALL,
)
# Month name mapping for parsing
MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}

# Global verbose flag
VERBOSE = False

# Resolved claude command (set at startup)
CLAUDE_CMD: list[str] = ["claude"]

# Environment variables to strip from child Claude processes
# CLAUDECODE is set by Claude Code to detect nested sessions; we must remove it
# so the orchestrator can spawn Claude from within a Claude Code session.
STRIPPED_ENV_VARS = ["CLAUDECODE"]


def build_child_env() -> dict[str, str]:
    """Build a clean environment for spawning Claude child processes."""
    env = os.environ.copy()
    for var in STRIPPED_ENV_VARS:
        env.pop(var, None)
    return env


def verbose_log(message: str, prefix: str = "VERBOSE") -> None:
    """Print a verbose log message if verbose mode is enabled."""
    if VERBOSE:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] [{prefix}] {message}", flush=True)


def resolve_claude_binary() -> list[str]:
    """Find the claude binary, checking PATH then known install locations.

    Returns a command list (e.g. ['claude'] or ['node', '/path/to/cli.js']).
    """
    # First check if 'claude' is directly in PATH
    claude_path = shutil.which("claude")
    if claude_path:
        return [claude_path]

    # Check known installation paths (npm global installs)
    for search_path in CLAUDE_BINARY_SEARCH_PATHS:
        if os.path.isfile(search_path):
            node_path = shutil.which("node")
            if node_path:
                return [node_path, search_path]

    # Last resort: try npx
    npx_path = shutil.which("npx")
    if npx_path:
        return [npx_path, "@anthropic-ai/claude-code"]

    # Fallback - will fail at runtime with clear error
    print("[WARNING] Could not find 'claude' binary. Tasks will fail.")
    print("[WARNING] Install with: npm install -g @anthropic-ai/claude-code")
    return ["claude"]


def check_stop_requested() -> bool:
    """Check if a graceful stop has been requested via semaphore file.

    The orchestrator checks for the file at .claude/plans/.stop before
    starting each new task. If the file exists, the orchestrator will
    finish the current task but not start any new ones.

    To request a stop:  touch .claude/plans/.stop
    The file is auto-cleaned when the orchestrator starts.
    """
    if os.path.exists(STOP_SEMAPHORE_PATH):
        verbose_log("Stop semaphore detected", "STOP")
        return True
    return False


def clear_stop_semaphore() -> None:
    """Remove the stop semaphore file if it exists (called on startup)."""
    if os.path.exists(STOP_SEMAPHORE_PATH):
        os.remove(STOP_SEMAPHORE_PATH)
        print(f"[Cleared stale stop semaphore: {STOP_SEMAPHORE_PATH}]")


# Circuit breaker configuration
DEFAULT_CIRCUIT_BREAKER_THRESHOLD = 3  # consecutive failures to trip
DEFAULT_CIRCUIT_BREAKER_RESET_TIMEOUT = 300  # 5 minutes before retry
DEFAULT_BACKOFF_BASE = 5  # base seconds for exponential backoff
DEFAULT_BACKOFF_MAX = 120  # max backoff seconds


@dataclass
class TaskResult:
    """Result of a task execution."""
    success: bool
    message: str
    duration_seconds: float
    plan_modified: bool = False
    rate_limited: bool = False
    rate_limit_reset_time: Optional[datetime] = None


@dataclass
class ValidationConfig:
    """Configuration for per-task validation parsed from plan meta.

    Parsed from the optional meta.validation block in the plan YAML.
    When enabled, the orchestrator spawns a validator agent after each
    implementation task to independently verify the result.
    """
    enabled: bool = False
    run_after: list[str] = field(default_factory=lambda: ["coder"])
    validators: list[str] = field(default_factory=lambda: ["validator"])
    max_validation_attempts: int = 1


@dataclass
class ValidationVerdict:
    """Result of a validation pass on a completed task.

    The verdict is extracted from the validator's output using VERDICT_PATTERN.
    Individual findings are parsed using FINDING_PATTERN.
    """
    verdict: str       # "PASS", "WARN", or "FAIL"
    findings: list[str] = field(default_factory=list)
    raw_output: str = ""


def parse_validation_config(plan: dict) -> ValidationConfig:
    """Parse the optional meta.validation block from the plan YAML.

    Extracts validation configuration from plan['meta']['validation'].
    If the validation block is missing, empty, or not a dict, returns
    a ValidationConfig with defaults (enabled=False).

    Args:
        plan: The parsed plan dictionary containing an optional meta.validation block.

    Returns:
        A ValidationConfig populated from the plan meta, or defaults if absent.
    """
    val_dict = plan.get("meta", {}).get("validation", {})
    if not isinstance(val_dict, dict) or not val_dict:
        return ValidationConfig()

    return ValidationConfig(
        enabled=val_dict.get("enabled", False),
        run_after=val_dict.get("run_after", ["coder"]),
        validators=val_dict.get("validators", ["validator"]),
        max_validation_attempts=val_dict.get("max_validation_attempts", 1),
    )


class CircuitBreaker:
    """Circuit breaker to prevent runaway failures when LLM is unavailable."""

    def __init__(
        self,
        threshold: int = DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
        reset_timeout: int = DEFAULT_CIRCUIT_BREAKER_RESET_TIMEOUT,
        backoff_base: int = DEFAULT_BACKOFF_BASE,
        backoff_max: int = DEFAULT_BACKOFF_MAX
    ):
        self.threshold = threshold
        self.reset_timeout = reset_timeout
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.consecutive_failures = 0
        self.last_failure_time: Optional[float] = None
        self.is_open = False

    def record_success(self) -> None:
        """Record a successful task execution."""
        self.consecutive_failures = 0
        self.is_open = False
        self.last_failure_time = None

    def record_failure(self) -> None:
        """Record a failed task execution."""
        self.consecutive_failures += 1
        self.last_failure_time = time.time()

        if self.consecutive_failures >= self.threshold:
            self.is_open = True
            print(f"\n[CIRCUIT BREAKER] Tripped after {self.consecutive_failures} consecutive failures")

    def can_proceed(self) -> bool:
        """Check if we can proceed with another task."""
        if not self.is_open:
            return True

        # Check if enough time has passed to try again
        if self.last_failure_time:
            elapsed = time.time() - self.last_failure_time
            if elapsed >= self.reset_timeout:
                print(f"[CIRCUIT BREAKER] Reset timeout elapsed ({self.reset_timeout}s), attempting recovery")
                self.is_open = False
                self.consecutive_failures = 0
                return True

        return False

    def get_backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        delay = min(self.backoff_base * (2 ** (attempt - 1)), self.backoff_max)
        return delay

    def wait_for_reset(self) -> bool:
        """Wait for circuit breaker reset timeout. Returns True if should continue."""
        if not self.is_open or not self.last_failure_time:
            return True

        elapsed = time.time() - self.last_failure_time
        remaining = self.reset_timeout - elapsed

        if remaining > 0:
            print(f"[CIRCUIT BREAKER] Open - waiting {remaining:.0f}s before retry...")
            print(f"[CIRCUIT BREAKER] Press Ctrl+C to abort")
            try:
                time.sleep(remaining)
            except KeyboardInterrupt:
                print("\n[CIRCUIT BREAKER] Aborted by user")
                return False

        self.is_open = False
        self.consecutive_failures = 0
        return True


def parse_rate_limit_reset_time(output: str) -> Optional[datetime]:
    """Parse a rate limit reset time from Claude CLI output.

    Recognizes messages like:
      "You've hit your limit · resets Feb 9 at 6pm (America/Toronto)"
      "You've hit your limit · resets February 9 at 6:30pm (America/Toronto)"

    Returns a timezone-aware datetime if parseable, None otherwise.
    """
    match = RATE_LIMIT_PATTERN.search(output)
    if not match:
        return None

    date_str = match.group(1).strip()      # e.g. "Feb 9"
    time_str = match.group(2).strip()      # e.g. "6pm" or "6:30pm"
    tz_str = match.group(3)                # e.g. "America/Toronto" or None

    try:
        # Parse month and day
        parts = date_str.split()
        month_name = parts[0].lower()
        day = int(parts[1])
        month = MONTH_NAMES.get(month_name)
        if month is None:
            print(f"[RATE LIMIT] Could not parse month: {month_name}")
            return None

        # Parse time - handle "6pm", "6:30pm", "18:00"
        time_str_lower = time_str.lower().strip()
        hour = 0
        minute = 0

        if "am" in time_str_lower or "pm" in time_str_lower:
            is_pm = "pm" in time_str_lower
            time_digits = time_str_lower.replace("am", "").replace("pm", "").strip()
            if ":" in time_digits:
                hour_str, min_str = time_digits.split(":")
                hour = int(hour_str)
                minute = int(min_str)
            else:
                hour = int(time_digits)
            if is_pm and hour != 12:
                hour += 12
            elif not is_pm and hour == 12:
                hour = 0
        elif ":" in time_str_lower:
            hour_str, min_str = time_str_lower.split(":")
            hour = int(hour_str)
            minute = int(min_str)
        else:
            hour = int(time_str_lower)

        # Parse timezone
        tz = ZoneInfo("UTC")
        if tz_str:
            try:
                tz = ZoneInfo(tz_str.strip())
            except (KeyError, ValueError):
                print(f"[RATE LIMIT] Unknown timezone '{tz_str}', using UTC")

        # Build the datetime - use current year, handle year rollover
        now = datetime.now(tz)
        reset_time = now.replace(month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)

        # If the reset time is in the past, it might be next year
        if reset_time < now - timedelta(hours=1):
            reset_time = reset_time.replace(year=now.year + 1)

        return reset_time

    except (ValueError, IndexError) as e:
        print(f"[RATE LIMIT] Failed to parse reset time: {e}")
        return None


def check_rate_limit(output: str) -> tuple[bool, Optional[datetime]]:
    """Check if output contains a rate limit message.

    Returns (is_rate_limited, reset_time).
    reset_time is None if rate limited but couldn't parse the time.
    """
    # Check for the rate limit pattern
    if not re.search(r"(?:You've hit your limit|Usage limit reached)", output, re.IGNORECASE):
        return False, None

    reset_time = parse_rate_limit_reset_time(output)
    return True, reset_time


def wait_for_rate_limit_reset(reset_time: Optional[datetime]) -> bool:
    """Sleep until the rate limit resets.

    If reset_time is None, sleeps for RATE_LIMIT_DEFAULT_WAIT_SECONDS.
    Returns True if the wait completed, False if interrupted by user.
    """
    if reset_time:
        now = datetime.now(reset_time.tzinfo)
        wait_seconds = (reset_time - now).total_seconds()
        if wait_seconds <= 0:
            print("[RATE LIMIT] Reset time already passed, continuing immediately")
            return True
        # Add a small buffer to ensure we're past the reset
        wait_seconds += 30
        reset_str = reset_time.strftime("%Y-%m-%d %H:%M %Z")
        print(f"\n[RATE LIMIT] API rate limit hit. Resets at: {reset_str}")
        print(f"[RATE LIMIT] Sleeping for {wait_seconds:.0f}s ({wait_seconds / 60:.1f} minutes)")
    else:
        wait_seconds = RATE_LIMIT_DEFAULT_WAIT_SECONDS
        print(f"\n[RATE LIMIT] API rate limit hit. Could not parse reset time.")
        print(f"[RATE LIMIT] Sleeping for default {wait_seconds}s ({wait_seconds / 60:.0f} minutes)")

    print("[RATE LIMIT] Press Ctrl+C to abort")
    try:
        time.sleep(wait_seconds)
        print("[RATE LIMIT] Wait complete, resuming...")
        return True
    except KeyboardInterrupt:
        print("\n[RATE LIMIT] Aborted by user")
        return False


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
    sections = plan.get("sections", [])
    verbose_log(f"Scanning {len(sections)} sections for next task", "FIND")

    for section in sections:
        section_id = section.get("id", "unknown")
        section_status = section.get("status", "pending")
        verbose_log(f"  Section '{section_id}': status={section_status}", "FIND")

        if section_status == "completed":
            verbose_log(f"    Skipping completed section", "FIND")
            continue

        tasks = section.get("tasks", [])
        verbose_log(f"    Checking {len(tasks)} tasks in section", "FIND")

        for task in tasks:
            task_id = task.get("id", "unknown")
            task_status = task.get("status", "pending")
            task_depends = task.get("depends_on", [])
            verbose_log(f"      Task '{task_id}': status={task_status}, depends_on={task_depends}", "FIND")

            if task_status == "pending":
                # Check dependencies
                if task_depends:
                    deps_satisfied = check_dependencies_satisfied(plan, task_depends)
                    verbose_log(f"      Dependencies satisfied: {deps_satisfied}", "FIND")
                    if not deps_satisfied:
                        verbose_log(f"      Skipping - dependencies not met", "FIND")
                        continue

                verbose_log(f"      SELECTED: Task '{task_id}' is pending and ready", "FIND")
                return (section, task)
            elif task_status == "in_progress":
                verbose_log(f"      SELECTED: Task '{task_id}' is in_progress (resuming)", "FIND")
                # Resume in-progress task
                return (section, task)
            else:
                verbose_log(f"      Skipping task with status '{task_status}'", "FIND")

    verbose_log("No pending or in_progress tasks found", "FIND")
    return None


def check_dependencies_satisfied(plan: dict, depends_on: list) -> bool:
    """Check if all dependencies for a task are completed."""
    for dep_id in depends_on:
        result = find_task_by_id(plan, dep_id)
        if not result:
            verbose_log(f"        Dependency '{dep_id}' not found in plan", "DEPS")
            return False
        _, dep_task = result
        dep_status = dep_task.get("status", "pending")
        verbose_log(f"        Dependency '{dep_id}' status: {dep_status}", "DEPS")
        if dep_status != "completed":
            return False
    return True


def find_task_by_id(plan: dict, task_id: str) -> Optional[tuple[dict, dict]]:
    """Find a specific task by ID. Returns (section, task) or None."""
    for section in plan.get("sections", []):
        for task in section.get("tasks", []):
            if task.get("id") == task_id:
                return (section, task)
    return None


def extract_files_from_description(description: str) -> set[str]:
    """Extract file paths mentioned in a task description.

    Looks for patterns like:
    - Files: src/path/to/file.tsx
    - New: src/path/to/newfile.ts
    - src/components/Something.tsx
    - Explicit paths ending in common extensions

    Returns a set of normalized file paths.
    """
    import re

    files: set[str] = set()

    # Pattern for explicit "Files:" or "New:" declarations
    file_patterns = [
        r'Files?:\s*([^\n]+)',
        r'New:\s*([^\n]+)',
    ]

    for pattern in file_patterns:
        for match in re.finditer(pattern, description, re.IGNORECASE):
            # Split by common separators and clean each path
            paths = re.split(r'[,;]|\s+', match.group(1))
            for path in paths:
                path = path.strip()
                if path and '/' in path and not path.startswith('#'):
                    # Remove trailing punctuation
                    path = re.sub(r'[,;:]+$', '', path)
                    files.add(path)

    # Pattern for standalone file paths (src/..., test/..., etc.)
    path_pattern = r'\b((?:src|test|lib|app|components|hooks|pages|api)/[\w\-./]+\.(?:tsx?|jsx?|md|json|yaml|css|scss))\b'
    for match in re.finditer(path_pattern, description):
        files.add(match.group(1))

    return files


def check_parallel_task_conflicts(tasks: list[tuple[dict, dict, str]]) -> tuple[bool, str]:
    """Check if parallel tasks have any file or resource conflicts.

    Returns (has_conflict, conflict_message) tuple.
    """
    task_files: dict[str, set[str]] = {}
    task_resources: dict[str, set[str]] = {}

    for section, task, group_name in tasks:
        task_id = task.get("id", "unknown")
        description = task.get("description", "")

        # Extract files from description
        files = extract_files_from_description(description)
        task_files[task_id] = files

        # Get exclusive resources declared by task
        resources = set(task.get("exclusive_resources", []))
        task_resources[task_id] = resources

    # Check for file overlaps between tasks
    task_ids = list(task_files.keys())
    for i in range(len(task_ids)):
        for j in range(i + 1, len(task_ids)):
            id1, id2 = task_ids[i], task_ids[j]
            files1, files2 = task_files[id1], task_files[id2]

            # Check direct file conflicts
            overlap = files1 & files2
            if overlap:
                return (True, f"Tasks {id1} and {id2} both modify: {', '.join(sorted(overlap))}")

            # Check directory-level conflicts (if one task modifies a parent directory)
            for f1 in files1:
                for f2 in files2:
                    if f1.startswith(f2.rsplit('/', 1)[0] + '/') or f2.startswith(f1.rsplit('/', 1)[0] + '/'):
                        # Files in same directory - only warn if same immediate parent
                        dir1 = f1.rsplit('/', 1)[0] if '/' in f1 else ''
                        dir2 = f2.rsplit('/', 1)[0] if '/' in f2 else ''
                        if dir1 == dir2:
                            verbose_log(f"Warning: Tasks {id1} and {id2} modify files in same directory: {dir1}", "CONFLICT")

            # Check exclusive resource conflicts
            res1, res2 = task_resources[id1], task_resources[id2]
            resource_overlap = res1 & res2
            if resource_overlap:
                return (True, f"Tasks {id1} and {id2} both require exclusive resource: {', '.join(sorted(resource_overlap))}")

    return (False, "")


def find_parallel_tasks(plan: dict) -> list[tuple[dict, dict, str]]:
    """Find all tasks ready to run in parallel with the same parallel_group.

    Returns list of (section, task, parallel_group) tuples for tasks that:
    - Have status 'pending'
    - Have all dependencies satisfied
    - Share the same parallel_group value
    - Do NOT have file or resource conflicts with each other

    Only returns tasks from the first parallel_group found with ready tasks.
    """
    parallel_groups: dict[str, list[tuple[dict, dict]]] = {}

    for section in plan.get("sections", []):
        if section.get("status") == "completed":
            continue

        for task in section.get("tasks", []):
            if task.get("status") != "pending":
                continue

            parallel_group = task.get("parallel_group")
            if not parallel_group:
                continue

            # Check dependencies
            depends_on = task.get("depends_on", [])
            if depends_on and not check_dependencies_satisfied(plan, depends_on):
                continue

            if parallel_group not in parallel_groups:
                parallel_groups[parallel_group] = []
            parallel_groups[parallel_group].append((section, task))

    # Return tasks from the first parallel group with ready tasks (and no conflicts)
    for group_name, tasks in parallel_groups.items():
        if len(tasks) >= 2:  # Only parallelize if 2+ tasks ready
            candidate_tasks = [(s, t, group_name) for s, t in tasks]

            # Check for conflicts
            has_conflict, conflict_msg = check_parallel_task_conflicts(candidate_tasks)
            if has_conflict:
                print(f"[CONFLICT] Cannot parallelize group '{group_name}': {conflict_msg}")
                print(f"[CONFLICT] Falling back to sequential execution for conflicting tasks")
                verbose_log(f"Parallel group '{group_name}' has conflicts - executing sequentially", "PARALLEL")
                # Return empty to fall back to sequential execution
                return []

            return candidate_tasks

    return []


# =============================================================================
# WORKTREE MANAGEMENT
# =============================================================================

def get_worktree_path(plan_name: str, task_id: str) -> Path:
    """Get the path for a task's worktree."""
    safe_plan_name = plan_name.replace(" ", "-").lower()[:30]
    safe_task_id = task_id.replace(".", "-")
    return Path(WORKTREE_BASE_DIR) / f"{safe_plan_name}-{safe_task_id}"


def create_worktree(plan_name: str, task_id: str) -> Optional[Path]:
    """Create a git worktree for a task.

    Returns the worktree path if successful, None if failed.
    """
    worktree_path = get_worktree_path(plan_name, task_id)
    branch_name = f"parallel/{task_id.replace('.', '-')}"

    # Ensure base directory exists
    Path(WORKTREE_BASE_DIR).mkdir(parents=True, exist_ok=True)

    # Clean up if worktree already exists
    if worktree_path.exists():
        cleanup_worktree(worktree_path)

    # Delete stale branch if it exists (from previous failed run)
    subprocess.run(
        ["git", "branch", "-D", branch_name],
        capture_output=True,
        text=True,
        check=False  # Don't fail if branch doesn't exist
    )

    # Prune any stale worktree references
    subprocess.run(
        ["git", "worktree", "prune"],
        capture_output=True,
        text=True,
        check=False
    )

    try:
        # Get current branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True
        )
        current_branch = result.stdout.strip()

        # Create worktree with new branch from current HEAD
        subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
            capture_output=True,
            text=True,
            check=True
        )

        verbose_log(f"Created worktree at {worktree_path} on branch {branch_name}", "WORKTREE")

        # Clear stale task-status.json inherited from main branch to prevent
        # the orchestrator from reading results from a previous plan's run
        stale_status = worktree_path / ".claude" / "plans" / "task-status.json"
        if stale_status.exists():
            stale_status.unlink()
            verbose_log("Removed stale task-status.json from worktree", "WORKTREE")

        return worktree_path

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to create worktree: {e.stderr}")
        return None


def cleanup_worktree(worktree_path: Path) -> bool:
    """Remove a worktree and its branch.

    Returns True if cleanup was successful.
    """
    try:
        # Remove the worktree
        subprocess.run(
            ["git", "worktree", "remove", str(worktree_path), "--force"],
            capture_output=True,
            text=True,
            check=False  # Don't fail if already removed
        )

        # Prune any stale worktree references
        subprocess.run(
            ["git", "worktree", "prune"],
            capture_output=True,
            text=True,
            check=False
        )

        verbose_log(f"Cleaned up worktree at {worktree_path}", "WORKTREE")
        return True

    except Exception as e:
        print(f"[WARNING] Failed to cleanup worktree {worktree_path}: {e}")
        return False


def cleanup_stale_claims(max_age_minutes: int = 60) -> int:
    """Remove stale claims from agent-claims.json.

    A claim is stale if:
    - Its claimed_at timestamp is older than max_age_minutes
    - OR no corresponding subagent status file exists with recent heartbeat

    Returns the number of claims removed.
    """
    claims_path = Path(".claude/agent-claims.json")
    if not claims_path.exists():
        return 0

    try:
        with open(claims_path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return 0

    claims = data.get("claims", [])
    if not claims:
        return 0

    now = datetime.now()
    max_age = max_age_minutes * 60  # Convert to seconds
    active_claims = []
    removed_count = 0

    for claim in claims:
        claimed_at_str = claim.get("claimed_at", "")
        agent_id = claim.get("agent", "")

        # Parse claimed_at timestamp
        try:
            claimed_at = datetime.fromisoformat(claimed_at_str.replace("Z", "+00:00"))
            # Make naive for comparison
            if claimed_at.tzinfo:
                claimed_at = claimed_at.replace(tzinfo=None)
            age_seconds = (now - claimed_at).total_seconds()
        except (ValueError, TypeError):
            age_seconds = float('inf')  # Invalid timestamp = stale

        # Check if claim is stale by age
        if age_seconds > max_age:
            verbose_log(f"Removing stale claim from {agent_id} (age: {age_seconds/60:.1f} min)", "CLEANUP")
            removed_count += 1
            continue

        # Check subagent status file for heartbeat
        status_path = Path(f".claude/subagent-status/{agent_id}.json")
        if status_path.exists():
            try:
                with open(status_path, "r") as f:
                    status = json.load(f)
                # If status is completed/failed, claim should be released
                if status.get("status") in ["completed", "failed"]:
                    verbose_log(f"Removing claim from {agent_id} (status: {status.get('status')})", "CLEANUP")
                    removed_count += 1
                    continue
            except (json.JSONDecodeError, IOError):
                pass

        # Keep this claim
        active_claims.append(claim)

    # Write back if changes were made
    if removed_count > 0:
        data["claims"] = active_claims
        with open(claims_path, "w") as f:
            json.dump(data, f, indent=2)
        verbose_log(f"Cleaned up {removed_count} stale claims", "CLEANUP")

    return removed_count


def copy_worktree_artifacts(worktree_path: Path, task_id: str) -> tuple[bool, str, list[str]]:
    """Copy changed files from a worktree into the main working directory.

    Instead of using git merge (which fails when multiple parallel branches all
    modify the YAML plan file), this function:
    1. Diffs the worktree branch against the fork point to find changed files
    2. Copies added/modified files from the worktree into main
    3. Removes deleted files from main
    4. Skips coordination files (.claude/plans/) that the orchestrator manages

    Returns (success, message, files_copied) tuple.
    """
    branch_name = f"parallel/{task_id.replace('.', '-')}"
    # Coordination paths that the orchestrator manages -- never copy from worktrees
    SKIP_PREFIXES = (".claude/plans/", ".claude/subagent-status/", ".claude/agent-claims")

    try:
        # Find the fork point (common ancestor of main and branch)
        fork_result = subprocess.run(
            ["git", "merge-base", "HEAD", branch_name],
            capture_output=True, text=True, check=True
        )
        fork_point = fork_result.stdout.strip()

        # Get list of changed files between fork point and branch tip
        diff_result = subprocess.run(
            ["git", "diff", "--name-status", fork_point, branch_name],
            capture_output=True, text=True, check=True
        )

        if not diff_result.stdout.strip():
            verbose_log(f"No file changes in {branch_name}", "MERGE")
            return (True, "No changes to copy", [])

        files_copied: list[str] = []
        files_deleted: list[str] = []
        files_skipped: list[str] = []

        for line in diff_result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            status = parts[0][0]  # A, M, D, R, C (first char)
            file_path = parts[-1]  # Last element handles renames

            # Skip orchestrator coordination files
            if any(file_path.startswith(prefix) for prefix in SKIP_PREFIXES):
                files_skipped.append(file_path)
                verbose_log(f"  Skipping coordination file: {file_path}", "MERGE")
                continue

            if status in ("A", "M", "C"):
                # Added, Modified, or Copied -- copy from worktree to main
                src = worktree_path / file_path
                dst = Path(file_path)
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))
                    files_copied.append(file_path)
                    verbose_log(f"  Copied: {file_path}", "MERGE")
                else:
                    verbose_log(f"  WARNING: Source missing in worktree: {file_path}", "MERGE")

            elif status == "D":
                # Deleted -- remove from main if it exists
                dst = Path(file_path)
                if dst.exists():
                    dst.unlink()
                    files_deleted.append(file_path)
                    verbose_log(f"  Deleted: {file_path}", "MERGE")

            elif status == "R":
                # Renamed -- old path in parts[1], new path in parts[2]
                if len(parts) >= 3:
                    old_path = parts[1]
                    new_path = parts[2]
                    src = worktree_path / new_path
                    if src.exists():
                        Path(new_path).parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(src), str(new_path))
                        files_copied.append(new_path)
                        # Remove old file if it still exists in main
                        old_dst = Path(old_path)
                        if old_dst.exists():
                            old_dst.unlink()
                            files_deleted.append(old_path)
                        verbose_log(f"  Renamed: {old_path} -> {new_path}", "MERGE")

        all_changes = files_copied + files_deleted
        summary_parts = []
        if files_copied:
            summary_parts.append(f"{len(files_copied)} copied")
        if files_deleted:
            summary_parts.append(f"{len(files_deleted)} deleted")
        if files_skipped:
            summary_parts.append(f"{len(files_skipped)} skipped")
        summary = ", ".join(summary_parts) or "no file changes"

        verbose_log(f"Artifacts from {branch_name}: {summary}", "MERGE")

        # Delete the branch after successful copy
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            capture_output=True, text=True, check=False
        )

        return (True, f"Copied from {branch_name}: {summary}", all_changes)

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr or e.stdout or str(e)
        return (False, f"Failed to copy artifacts: {error_msg}", [])


def run_parallel_task(
    plan: dict,
    section: dict,
    task: dict,
    plan_path: str,
    plan_name: str,
    parallel_group: str,
    sibling_task_ids: list[str],
    dry_run: bool = False
) -> tuple[str, TaskResult]:
    """Run a single task in a worktree for parallel execution.

    Returns (task_id, TaskResult) tuple.
    """
    task_id = task.get("id")
    verbose_log(f"[PARALLEL] Starting task {task_id}", "PARALLEL")

    if dry_run:
        print(f"[DRY RUN] Would execute task {task_id} in worktree")
        return (task_id, TaskResult(success=True, message="Dry run", duration_seconds=0))

    # Create worktree
    worktree_path = create_worktree(plan_name, task_id)
    if not worktree_path:
        return (task_id, TaskResult(
            success=False,
            message=f"Failed to create worktree for task {task_id}",
            duration_seconds=0
        ))

    start_time = time.time()

    # Build subagent context
    agent_id = f"subagent-{task_id.replace('.', '-')}"
    subagent_context = {
        "agent_id": agent_id,
        "worktree_path": str(worktree_path),
        "parallel_group": parallel_group,
        "sibling_tasks": [tid for tid in sibling_task_ids if tid != task_id]
    }

    try:
        # Build prompt with subagent context
        prompt = build_claude_prompt(plan, section, task, plan_path, subagent_context,
                                     attempt_number=task.get("attempts", 1))

        # Run Claude in the worktree directory
        cmd = [
            *CLAUDE_CMD,
            "--dangerously-skip-permissions",
            "--print",
            prompt
        ]

        verbose_log(f"[PARALLEL] Running Claude for task {task_id} in {worktree_path}", "PARALLEL")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(worktree_path),
            env=build_child_env()
        )

        stdout, stderr = process.communicate(timeout=CLAUDE_TIMEOUT_SECONDS)
        duration = time.time() - start_time

        if process.returncode != 0:
            # Check for rate limit in parallel task output
            combined_output = (stdout or "") + "\n" + (stderr or "")
            is_rate_limited, reset_time = check_rate_limit(combined_output)

            if is_rate_limited:
                return (task_id, TaskResult(
                    success=False,
                    message="API rate limit reached",
                    duration_seconds=duration,
                    rate_limited=True,
                    rate_limit_reset_time=reset_time
                ))

            return (task_id, TaskResult(
                success=False,
                message=f"Claude exited with code {process.returncode}: {stderr[:500]}",
                duration_seconds=duration
            ))

        # Check status file in worktree
        worktree_status_file = worktree_path / ".claude" / "plans" / "task-status.json"
        status = None
        if worktree_status_file.exists():
            try:
                with open(worktree_status_file, "r") as f:
                    status = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        if status and status.get("status") == "completed":
            # Commit changes in worktree before returning
            try:
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=str(worktree_path),
                    capture_output=True,
                    check=True
                )
                subprocess.run(
                    ["git", "commit", "-m", f"plan: Task {task_id} completed (parallel)"],
                    cwd=str(worktree_path),
                    capture_output=True,
                    check=False  # May have nothing to commit
                )
            except subprocess.CalledProcessError:
                pass  # No changes to commit is OK

            return (task_id, TaskResult(
                success=True,
                message=status.get("message", "Task completed"),
                duration_seconds=duration,
                plan_modified=status.get("plan_modified", False)
            ))
        elif status and status.get("status") == "failed":
            return (task_id, TaskResult(
                success=False,
                message=status.get("message", "Task failed"),
                duration_seconds=duration
            ))
        else:
            return (task_id, TaskResult(
                success=False,
                message="No status file written by Claude",
                duration_seconds=duration
            ))

    except subprocess.TimeoutExpired:
        return (task_id, TaskResult(
            success=False,
            message=f"Task timed out after {CLAUDE_TIMEOUT_SECONDS} seconds",
            duration_seconds=CLAUDE_TIMEOUT_SECONDS
        ))
    except Exception as e:
        return (task_id, TaskResult(
            success=False,
            message=f"Error running parallel task: {str(e)}",
            duration_seconds=time.time() - start_time
        ))


def build_claude_prompt(
    plan: dict,
    section: dict,
    task: dict,
    plan_path: str,
    subagent_context: Optional[dict] = None,
    attempt_number: int = 1
) -> str:
    """Build the prompt for Claude to execute a task.

    Args:
        plan: The full plan dict
        section: The section containing the task
        task: The task to execute
        plan_path: Path to the YAML plan file
        subagent_context: Optional dict with subagent info for parallel execution
            - agent_id: Unique identifier for this subagent
            - worktree_path: Path to this agent's worktree
            - parallel_group: Name of the parallel group
            - sibling_tasks: List of other task IDs running in parallel
        attempt_number: Which attempt this is (1 = fresh start, 2+ = retry after failure)
    """
    plan_doc = plan.get("meta", {}).get("plan_doc", "")

    # Resolve agent for this task (explicit or inferred)
    agent_name = task.get("agent")
    if agent_name is None:
        agent_name = infer_agent_for_task(task)

    agent_content = ""
    if agent_name:
        agent_def = load_agent_definition(agent_name)
        if agent_def:
            agent_content = agent_def["body"] + "\n\n---\n\n"
            verbose_log(f"Using agent '{agent_name}' for task {task['id']}", "AGENT")

    # Add subagent header if running as parallel worker
    subagent_header = ""
    if subagent_context:
        subagent_header = f"""
## SUBAGENT CONTEXT (You are a parallel worker)

**SUBAGENT_ID:** {subagent_context['agent_id']}
**WORKTREE_PATH:** {subagent_context['worktree_path']}
**PARALLEL_GROUP:** {subagent_context['parallel_group']}
**SIBLING_TASKS:** {', '.join(subagent_context.get('sibling_tasks', []))}

### MANDATORY: Follow the agent-sync protocol

You are running in parallel with other agents. Before editing ANY file:

1. **Initialize your status file:**
   ```bash
   mkdir -p .claude/subagent-status
   echo '{{"status":"starting","task_id":"{task['id']}","heartbeat":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}}' > .claude/subagent-status/{subagent_context['agent_id']}.json
   ```

2. **Check claims before editing:**
   ```bash
   cat .claude/agent-claims.json
   ```

3. **Claim files before editing** - Add your claim to agent-claims.json

4. **Update status as you work** - Keep heartbeat current

5. **Release claims when done** - Remove from agent-claims.json

6. **Write final status:**
   ```bash
   echo '{{"status":"completed","task_id":"{task['id']}","heartbeat":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}}' > .claude/subagent-status/{subagent_context['agent_id']}.json
   ```

Read `.claude/skills/agent-sync.md` for the full protocol.

---

"""

    # Build attempt-aware instruction for step 1
    if attempt_number >= 2:
        state_verification_instruction = (
            f"1. This is attempt {attempt_number}. A previous attempt failed. "
            "Check the current state before proceeding - some work may already be done."
        )
    else:
        state_verification_instruction = (
            "1. This is a fresh start (attempt 1). The task shows as in_progress because "
            "the orchestrator assigned it to you. Start working immediately on the task."
        )

    return f"""{agent_content}{subagent_header}Run task {task['id']} from the implementation plan.

## Task Details
- **Section:** {section['name']} ({section['id']})
- **Task:** {task['name']}
- **Description:** {task.get('description', 'No description')}
- **Plan Document:** {plan_doc}
- **YAML Plan File:** {plan_path}

## Instructions
{state_verification_instruction}
2. Read the relevant section from the plan document for detailed implementation steps
3. Implement the task following the plan's specifications
4. Run `{BUILD_COMMAND}` to verify no build errors
5. If you changed middleware, layout files, or auth-related code: run `npx playwright test tests/SMOKE01-critical-paths.spec.ts --reporter=list` to verify critical paths
6. Commit your changes with a descriptive message
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


def run_smoke_tests() -> bool:
    """Run smoke tests to verify critical paths still work after plan completion.

    Returns True if smoke tests pass, False otherwise.
    Uses PLAYWRIGHT_BASE_URL to target an existing dev server (avoids starting a
    competing QA server that would corrupt the shared .next cache).
    """
    print("\n=== Running post-plan smoke tests ===")
    print("Verifying critical user paths...")

    # Detect which port has a running server
    smoke_port = None
    try:
        check = subprocess.run(
            ["lsof", "-ti", f":{DEV_SERVER_PORT}"],
            capture_output=True, text=True, timeout=5
        )
        if check.stdout.strip():
            smoke_port = DEV_SERVER_PORT
    except Exception:
        pass

    if not smoke_port:
        print(f"[SMOKE] No dev server detected on port {DEV_SERVER_PORT} - skipping smoke tests")
        print(f"[SMOKE] Start a server with '{DEV_SERVER_COMMAND}' before running smoke tests")
        return True  # Don't fail the plan if no server is running

    print(f"[SMOKE] Using existing server on port {smoke_port}")

    # Set env to target existing server and skip webServer startup
    env = os.environ.copy()
    env["PLAYWRIGHT_BASE_URL"] = f"http://localhost:{smoke_port}"
    env["SMOKE_SKIP_WEBSERVER"] = "true"

    try:
        result = subprocess.run(
            ["npx", "playwright", "test", "tests/SMOKE01-critical-paths.spec.ts",
             "--reporter=list", "--timeout=30000",
             "--project=chromium"],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=os.getcwd(),
            env=env
        )

        if result.returncode == 0:
            print("[SMOKE] All smoke tests PASSED")
            return True
        else:
            print(f"[SMOKE] Smoke tests FAILED (exit code {result.returncode})")
            # Show relevant output
            for line in result.stdout.splitlines()[-20:]:
                print(f"  {line}")
            if result.stderr:
                for line in result.stderr.splitlines()[-10:]:
                    print(f"  [stderr] {line}")
            return False
    except subprocess.TimeoutExpired:
        print("[SMOKE] Smoke tests TIMED OUT (180s)")
        return False
    except FileNotFoundError:
        print("[SMOKE] npx/playwright not found - skipping smoke tests")
        return True  # Don't fail the plan if playwright isn't installed


class OutputCollector:
    """Collects output from Claude CLI and tracks stats."""

    def __init__(self):
        self.lines: list[str] = []
        self.bytes_received = 0
        self.line_count = 0

    def add_line(self, line: str) -> None:
        self.lines.append(line)
        self.bytes_received += len(line.encode('utf-8'))
        self.line_count += 1

    def get_output(self) -> str:
        return ''.join(self.lines)


def stream_output(pipe, prefix: str, collector: OutputCollector, show_full: bool) -> None:
    """Stream output from a subprocess pipe line by line."""
    try:
        for line in iter(pipe.readline, ''):
            if line:
                collector.add_line(line)
                if show_full:
                    print(f"[CLAUDE {prefix}] {line.rstrip()}", flush=True)
    except Exception as e:
        if VERBOSE:
            verbose_log(f"Error streaming {prefix}: {e}", "ERROR")


def stream_json_output(pipe, collector: OutputCollector) -> None:
    """Stream output from Claude CLI in stream-json format, showing tool use and text in real-time."""
    try:
        for line in iter(pipe.readline, ''):
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
                            # Show first 200 chars of text blocks
                            display = text[:200] + ("..." if len(text) > 200 else "")
                            print(f"  [{ts}] [Claude] {display}", flush=True)
                    elif block_type == "tool_use":
                        tool_name = block.get("name", "?")
                        tool_input = block.get("input", {})
                        # Show tool name + key info
                        if tool_name in ("Read", "Edit", "Write"):
                            detail = tool_input.get("file_path", "")
                        elif tool_name == "Bash":
                            cmd = tool_input.get("command", "")
                            detail = cmd[:80] + ("..." if len(cmd) > 80 else "")
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

    except Exception as e:
        if VERBOSE:
            verbose_log(f"Error streaming JSON: {e}", "ERROR")


def run_claude_task(prompt: str, dry_run: bool = False) -> TaskResult:
    """Execute a task using Claude CLI."""
    if dry_run:
        print(f"[DRY RUN] Would execute:\n{prompt[:200]}...")
        return TaskResult(success=True, message="Dry run", duration_seconds=0)

    start_time = time.time()

    verbose_log("Building Claude CLI command", "EXEC")
    cmd = [
        *CLAUDE_CMD,
        "--dangerously-skip-permissions",
        "--print",
        prompt
    ]
    # In verbose mode, use stream-json for real-time tool/text streaming
    if VERBOSE:
        cmd.extend(["--output-format", "stream-json", "--verbose"])
    verbose_log(f"Command: {' '.join(CLAUDE_CMD)} --dangerously-skip-permissions --print <prompt>", "EXEC")
    verbose_log(f"Prompt length: {len(prompt)} chars", "EXEC")
    verbose_log(f"Working directory: {os.getcwd()}", "EXEC")
    verbose_log(f"Timeout: {CLAUDE_TIMEOUT_SECONDS}s", "EXEC")

    # Output collectors for both modes
    stdout_collector = OutputCollector()
    stderr_collector = OutputCollector()

    try:
        if VERBOSE:
            verbose_log("Starting Claude CLI process with real-time streaming...", "EXEC")
            print("=" * 60, flush=True)
            print("[CLAUDE OUTPUT START]", flush=True)
            print("=" * 60, flush=True)

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.getcwd(),
            env=build_child_env()
        )

        # Start threads to stream/collect stdout and stderr
        if VERBOSE:
            stdout_thread = threading.Thread(
                target=stream_json_output,
                args=(process.stdout, stdout_collector)
            )
        else:
            stdout_thread = threading.Thread(
                target=stream_output,
                args=(process.stdout, "OUT", stdout_collector, False)
            )
        stderr_thread = threading.Thread(
            target=stream_output,
            args=(process.stderr, "ERR", stderr_collector, VERBOSE)
        )
        stdout_thread.start()
        stderr_thread.start()

        # In regular mode, show progress updates
        if not VERBOSE:
            print("[Claude] Working", end="", flush=True)
            last_bytes = 0
            dots = 0
            while process.poll() is None:
                time.sleep(1)
                current_bytes = stdout_collector.bytes_received + stderr_collector.bytes_received
                if current_bytes > last_bytes:
                    # Show a dot for each 1KB received
                    new_kb = (current_bytes - last_bytes) // 1024
                    if new_kb > 0:
                        print("." * min(new_kb, 5), end="", flush=True)
                        dots += min(new_kb, 5)
                    elif current_bytes > last_bytes:
                        print(".", end="", flush=True)
                        dots += 1
                    last_bytes = current_bytes

                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > CLAUDE_TIMEOUT_SECONDS:
                    print(" [TIMEOUT]", flush=True)
                    process.terminate()
                    process.wait(timeout=5)
                    raise subprocess.TimeoutExpired(cmd, CLAUDE_TIMEOUT_SECONDS)

            print(f" done ({stdout_collector.line_count} lines, {stdout_collector.bytes_received:,} bytes)", flush=True)

        # Wait for process with timeout (verbose mode)
        if VERBOSE:
            try:
                returncode = process.wait(timeout=CLAUDE_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                verbose_log("Process timed out, terminating...", "EXEC")
                process.terminate()
                process.wait(timeout=5)
                raise
        else:
            returncode = process.returncode

        # Wait for threads to finish
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        if VERBOSE:
            print("=" * 60, flush=True)
            print("[CLAUDE OUTPUT END]", flush=True)
            print("=" * 60, flush=True)
            verbose_log(f"Process completed with return code: {returncode}", "EXEC")

        duration = time.time() - start_time

        # Save output to log file for debugging
        log_dir = Path(".claude/plans/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
        with open(log_file, "w") as f:
            f.write(f"=== Claude Task Output ===\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Duration: {duration:.1f}s\n")
            f.write(f"Return code: {returncode}\n")
            f.write(f"Stdout lines: {stdout_collector.line_count}\n")
            f.write(f"Stderr lines: {stderr_collector.line_count}\n")
            f.write(f"\n=== STDOUT ===\n")
            f.write(stdout_collector.get_output())
            f.write(f"\n=== STDERR ===\n")
            f.write(stderr_collector.get_output())

        print(f"[Log saved to: {log_file}]")

        if VERBOSE:
            verbose_log(f"Duration: {duration:.1f}s", "EXEC")

        if returncode != 0:
            # Combine stdout and stderr to check for rate limit messages
            combined_output = stdout_collector.get_output() + "\n" + stderr_collector.get_output()
            is_rate_limited, reset_time = check_rate_limit(combined_output)

            if is_rate_limited:
                return TaskResult(
                    success=False,
                    message="API rate limit reached",
                    duration_seconds=duration,
                    rate_limited=True,
                    rate_limit_reset_time=reset_time
                )

            error_msg = stderr_collector.get_output()[:500] if stderr_collector.bytes_received > 0 else "Unknown error"
            return TaskResult(
                success=False,
                message=f"Claude exited with code {returncode}: {error_msg}",
                duration_seconds=duration
            )

        # Check the status file for task result
        verbose_log(f"Checking status file: {STATUS_FILE_PATH}", "STATUS")
        status = read_status_file()

        if status:
            verbose_log(f"Status file contents: {json.dumps(status, indent=2)}", "STATUS")
        else:
            verbose_log("No status file found or failed to parse", "STATUS")

        plan_modified = status.get("plan_modified", False) if status else False

        if status and status.get("status") == "completed":
            verbose_log("Task status: COMPLETED", "STATUS")
            return TaskResult(
                success=True,
                message=status.get("message", "Task completed"),
                duration_seconds=duration,
                plan_modified=plan_modified
            )
        elif status and status.get("status") == "failed":
            verbose_log("Task status: FAILED", "STATUS")
            return TaskResult(
                success=False,
                message=status.get("message", "Task failed"),
                duration_seconds=duration,
                plan_modified=plan_modified
            )
        else:
            verbose_log("Task status: UNKNOWN (no status file)", "STATUS")
            # No status file or unclear status - check if build passes
            return TaskResult(
                success=False,
                message="No status file written by Claude",
                duration_seconds=duration
            )

    except subprocess.TimeoutExpired:
        verbose_log(f"TIMEOUT after {CLAUDE_TIMEOUT_SECONDS}s", "ERROR")
        return TaskResult(
            success=False,
            message=f"Task timed out after {CLAUDE_TIMEOUT_SECONDS} seconds",
            duration_seconds=CLAUDE_TIMEOUT_SECONDS
        )
    except Exception as e:
        verbose_log(f"Exception: {type(e).__name__}: {e}", "ERROR")
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
            [*CLAUDE_CMD, "--dangerously-skip-permissions", "--print", notification_prompt],
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
    single_task: bool = False,
    verbose: bool = False,
    parallel: bool = False,
    skip_smoke: bool = False
) -> None:
    """Main orchestrator loop."""
    global VERBOSE
    VERBOSE = verbose

    verbose_log(f"Loading plan from: {plan_path}", "INIT")
    plan = load_plan(plan_path)
    verbose_log(f"Plan loaded successfully", "INIT")

    meta = plan.get("meta", {})
    default_max_attempts = meta.get("max_attempts_default", DEFAULT_MAX_ATTEMPTS)

    verbose_log(f"Plan meta: {json.dumps(meta, indent=2, default=str)}", "INIT")
    verbose_log(f"Sections in plan: {len(plan.get('sections', []))}", "INIT")

    # Initialize circuit breaker with configurable settings
    circuit_breaker = CircuitBreaker(
        threshold=meta.get("circuit_breaker_threshold", DEFAULT_CIRCUIT_BREAKER_THRESHOLD),
        reset_timeout=meta.get("circuit_breaker_reset_timeout", DEFAULT_CIRCUIT_BREAKER_RESET_TIMEOUT),
        backoff_base=meta.get("backoff_base", DEFAULT_BACKOFF_BASE),
        backoff_max=meta.get("backoff_max", DEFAULT_BACKOFF_MAX)
    )

    # Resolve the claude binary path
    global CLAUDE_CMD
    CLAUDE_CMD = resolve_claude_binary()

    # Clear any stale stop semaphore from a previous run
    clear_stop_semaphore()

    print(f"=== Plan Orchestrator (PID {os.getpid()}) ===")
    print(f"Plan: {meta.get('name', 'Unknown')}")
    print(f"Claude binary: {' '.join(CLAUDE_CMD)}")
    print(f"Max attempts per task: {default_max_attempts}")
    print(f"Circuit breaker threshold: {circuit_breaker.threshold} consecutive failures")
    print(f"Parallel mode: {parallel}")
    print(f"Dry run: {dry_run}")
    print(f"Graceful stop: touch {STOP_SEMAPHORE_PATH}")
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

    iteration = 0
    while True:
        iteration += 1
        verbose_log(f"=== Loop iteration {iteration} ===", "LOOP")

        # Check for graceful stop request
        if check_stop_requested():
            print(f"\n=== Graceful stop requested (found {STOP_SEMAPHORE_PATH}) ===")
            print(f"Stopping after current task completes. No new tasks will be started.")
            os.remove(STOP_SEMAPHORE_PATH)
            break

        # Check circuit breaker before proceeding
        verbose_log(f"Circuit breaker state: open={circuit_breaker.is_open}, failures={circuit_breaker.consecutive_failures}", "LOOP")
        if not circuit_breaker.can_proceed():
            verbose_log("Circuit breaker blocking - waiting for reset", "LOOP")
            if not circuit_breaker.wait_for_reset():
                print("\n=== Orchestrator stopped by circuit breaker ===")
                break

        # =====================================================================
        # PARALLEL EXECUTION MODE
        # =====================================================================
        if parallel:
            parallel_tasks = find_parallel_tasks(plan)
            if parallel_tasks:
                group_name = parallel_tasks[0][2]
                print(f"\n=== PARALLEL EXECUTION: {len(parallel_tasks)} tasks in group '{group_name}' ===")

                # Prepare subagent infrastructure
                if not dry_run:
                    # Create subagent status directory
                    status_dir = Path(".claude/subagent-status")
                    status_dir.mkdir(parents=True, exist_ok=True)
                    verbose_log(f"Created subagent status directory: {status_dir}", "PARALLEL")

                    # Clean up stale claims (older than 1 hour)
                    cleanup_stale_claims()

                # Mark all tasks as in_progress
                for section, task, _ in parallel_tasks:
                    task["status"] = "in_progress"
                    task["attempts"] = task.get("attempts", 0) + 1
                    task["last_attempt"] = datetime.now().isoformat()
                if not dry_run:
                    save_plan(plan_path, plan)

                # Collect sibling task IDs for context
                sibling_task_ids = [task.get("id") for _, task, _ in parallel_tasks]

                # Execute tasks in parallel using ThreadPoolExecutor
                plan_name = meta.get("name", "plan")
                results: dict[str, TaskResult] = {}
                worktree_paths: dict[str, Path] = {}

                with ThreadPoolExecutor(max_workers=len(parallel_tasks)) as executor:
                    futures = {
                        executor.submit(
                            run_parallel_task,
                            plan, section, task, plan_path, plan_name,
                            group_name, sibling_task_ids, dry_run
                        ): task.get("id")
                        for section, task, _ in parallel_tasks
                    }

                    for section, task, _ in parallel_tasks:
                        task_id = task.get("id")
                        worktree_paths[task_id] = get_worktree_path(plan_name, task_id)

                    for future in as_completed(futures):
                        task_id, task_result = future.result()
                        results[task_id] = task_result
                        print(f"  [{task_id}] {'SUCCESS' if task_result.success else 'FAILED'} ({task_result.duration_seconds:.1f}s)")

                # Copy artifacts from successful worktrees into main
                merge_failures = []
                all_copied_files: list[str] = []
                for task_id, task_result in results.items():
                    if task_result.success:
                        worktree_path = worktree_paths.get(task_id)
                        if worktree_path and worktree_path.exists():
                            copy_ok, copy_msg, copied_files = copy_worktree_artifacts(
                                worktree_path, task_id
                            )
                            if not copy_ok:
                                merge_failures.append((task_id, copy_msg))
                                print(f"  [{task_id}] COPY FAILED: {copy_msg}")
                            else:
                                all_copied_files.extend(copied_files)
                                print(f"  [{task_id}] {copy_msg}")

                # Stage and commit all copied artifacts in a single commit
                if all_copied_files and not dry_run:
                    try:
                        # Separate existing files (add) from deleted files (rm)
                        files_to_add = [f for f in all_copied_files if Path(f).exists()]
                        files_to_rm = [f for f in all_copied_files if not Path(f).exists()]

                        if files_to_add:
                            subprocess.run(
                                ["git", "add"] + files_to_add,
                                capture_output=True, text=True, check=True
                            )
                        if files_to_rm:
                            subprocess.run(
                                ["git", "rm", "--cached", "--ignore-unmatch"] + files_to_rm,
                                capture_output=True, text=True, check=True
                            )

                        task_ids_merged = [
                            tid for tid, res in results.items() if res and res.success
                        ]
                        subprocess.run(
                            ["git", "commit", "-m",
                             f"plan: Merge artifacts from parallel tasks "
                             f"{', '.join(task_ids_merged)}"],
                            capture_output=True, text=True, check=False
                        )
                        verbose_log(
                            f"Committed {len(all_copied_files)} files from "
                            f"{len(task_ids_merged)} parallel tasks", "MERGE"
                        )
                    except subprocess.CalledProcessError as e:
                        print(f"  [WARNING] Failed to commit merged artifacts: {e.stderr}")

                # Cleanup worktrees
                for task_id, worktree_path in worktree_paths.items():
                    if worktree_path.exists():
                        cleanup_worktree(worktree_path)

                # Check if any parallel tasks hit rate limits
                rate_limited_results = [
                    r for r in results.values() if r and r.rate_limited
                ]
                if rate_limited_results:
                    # Find the latest reset time among all rate-limited tasks
                    reset_times = [r.rate_limit_reset_time for r in rate_limited_results if r.rate_limit_reset_time]
                    latest_reset = max(reset_times) if reset_times else None
                    print(f"\n[RATE LIMIT] {len(rate_limited_results)} parallel tasks hit rate limit")

                    # Reset all tasks in the group to pending (don't count attempts)
                    for section, task, _ in parallel_tasks:
                        task["status"] = "pending"
                        task["attempts"] = max(0, task.get("attempts", 1) - 1)

                    if not dry_run:
                        save_plan(plan_path, plan)

                    # Wait for rate limit reset
                    should_continue = wait_for_rate_limit_reset(latest_reset)
                    if not should_continue:
                        if not dry_run:
                            save_plan(plan_path, plan, commit=True,
                                      commit_message=f"plan: Rate limit wait aborted by user")
                        break
                    continue  # Retry the parallel group

                # Update task statuses in plan
                for section, task, _ in parallel_tasks:
                    task_id = task.get("id")
                    task_result = results.get(task_id)
                    if task_result and task_result.success and task_id not in [f[0] for f in merge_failures]:
                        task["status"] = "completed"
                        task["completed_at"] = datetime.now().isoformat()
                        task["result_message"] = task_result.message
                        tasks_completed += 1
                        circuit_breaker.record_success()
                        update_section_status(section)
                    else:
                        task["status"] = "pending"  # Will retry
                        if task_result:
                            task["last_error"] = task_result.message
                        circuit_breaker.record_failure()

                # Save plan after parallel execution
                if not dry_run:
                    save_plan(plan_path, plan, commit=True,
                              commit_message=f"plan: Parallel group '{group_name}' completed")

                # Check if there were merge failures requiring human intervention
                if merge_failures:
                    print(f"\n[WARNING] {len(merge_failures)} merge failures - manual intervention may be required")
                    for task_id, msg in merge_failures:
                        print(f"  - Task {task_id}: {msg}")

                if single_task:
                    print("\n[Single task mode - stopping after parallel group]")
                    break

                continue  # Next iteration

        # =====================================================================
        # SEQUENTIAL EXECUTION (default)
        # =====================================================================

        # Find next task
        verbose_log("Searching for next task...", "LOOP")
        result = find_next_task(plan)
        verbose_log(f"find_next_task returned: {result is not None}", "LOOP")

        if not result:
            print("\n=== All tasks completed! ===")

            # Run smoke tests as post-plan verification
            if not dry_run and not skip_smoke:
                smoke_ok = run_smoke_tests()
                if not smoke_ok:
                    print("\n[WARNING] Smoke tests FAILED after plan completion!")
                    print("[WARNING] The plan completed but critical user paths may be broken.")
                    print("[WARNING] Run 'npx playwright test tests/SMOKE*.spec.ts --reporter=list' to investigate.")
                    send_notification(
                        plan,
                        "Plan Completed - SMOKE TESTS FAILED",
                        f"All tasks in '{meta.get('name')}' completed "
                        f"(Completed: {tasks_completed}, Failed: {tasks_failed}) "
                        f"but smoke tests FAILED. Critical paths may be broken!"
                    )
                else:
                    send_notification(
                        plan,
                        "Plan Completed - All Verified",
                        f"All tasks in '{meta.get('name')}' completed and smoke tests passed. "
                        f"Completed: {tasks_completed}, Failed: {tasks_failed}"
                    )
            else:
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

        verbose_log(f"Found task: {task_id}", "TASK")
        verbose_log(f"Task details: {json.dumps(task, indent=2, default=str)}", "TASK")
        verbose_log(f"Section: {section.get('name')} ({section.get('id')})", "TASK")

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
        verbose_log("Clearing previous status file", "TASK")
        clear_status_file()

        # Build and execute prompt
        verbose_log("Building Claude prompt...", "TASK")
        prompt = build_claude_prompt(plan, section, task, plan_path,
                                     attempt_number=task.get("attempts", 1))
        verbose_log(f"Prompt built, length: {len(prompt)} chars", "TASK")
        if VERBOSE:
            print("-" * 40)
            print("[PROMPT PREVIEW]")
            print(prompt[:500] + ("..." if len(prompt) > 500 else ""))
            print("-" * 40)

        verbose_log("Executing Claude task...", "TASK")
        task_result = run_claude_task(prompt, dry_run=dry_run)
        verbose_log(f"Task result: success={task_result.success}, message={task_result.message}", "TASK")

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
            circuit_breaker.record_success()

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

            # Handle rate limiting separately from regular failures
            if task_result.rate_limited:
                print(f"\n[RATE LIMIT] Task {task_id} hit API rate limit")
                # Don't count rate limits as circuit breaker failures
                # Don't increment attempt count - this wasn't a real failure
                task["attempts"] = max(0, task.get("attempts", 1) - 1)

                if not dry_run:
                    save_plan(plan_path, plan)

                # Wait for rate limit reset
                should_continue = wait_for_rate_limit_reset(task_result.rate_limit_reset_time)
                if not should_continue:
                    # User aborted, save and exit
                    if not dry_run:
                        save_plan(plan_path, plan, commit=True,
                                  commit_message=f"plan: Rate limit wait aborted by user at task {task_id}")
                    break
                # After waiting, continue the loop to retry the same task
                continue

            circuit_breaker.record_failure()

            # Check if circuit breaker tripped
            if circuit_breaker.is_open:
                print(f"\n[CIRCUIT BREAKER] Stopping orchestrator - too many consecutive failures")
                print(f"[CIRCUIT BREAKER] Will wait {circuit_breaker.reset_timeout}s before allowing retry")
                send_notification(
                    plan,
                    "Circuit Breaker Tripped",
                    f"Orchestrator stopped after {circuit_breaker.consecutive_failures} consecutive failures. "
                    f"LLM may be unavailable. Manual intervention required."
                )
                if not dry_run:
                    save_plan(plan_path, plan, commit=True,
                              commit_message=f"plan: Circuit breaker tripped after {circuit_breaker.consecutive_failures} failures")
                break

        # Save and commit on success or if Claude modified the plan
        if not dry_run:
            should_commit = task_result.success or task_result.plan_modified
            commit_msg = f"plan: Task {task_id} {'completed' if task_result.success else 'updated'}"
            save_plan(plan_path, plan, commit=should_commit, commit_message=commit_msg)

        if single_task:
            print("\n[Single task mode - stopping]")
            break

        # Exponential backoff between tasks on failure, small delay on success
        if not dry_run:
            if task_result.success:
                time.sleep(2)
            else:
                backoff = circuit_breaker.get_backoff_delay(current_attempts + 1)
                print(f"[Backoff] Waiting {backoff:.0f}s before retry...")
                time.sleep(backoff)

    print(f"\n=== Summary ===")
    print(f"Tasks completed: {tasks_completed}")
    print(f"Tasks failed: {tasks_failed}")

    # Return non-zero exit code when tasks failed so callers (e.g. auto-pipeline)
    # know the orchestrator did not fully succeed.
    if tasks_failed > 0:
        sys.exit(1)


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
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output with detailed tracing"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable parallel task execution using git worktrees for tasks with same parallel_group"
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip post-plan smoke tests (not recommended)"
    )

    args = parser.parse_args()

    if not os.path.exists(args.plan):
        print(f"Error: Plan file not found: {args.plan}")
        sys.exit(1)

    run_orchestrator(
        plan_path=args.plan,
        dry_run=args.dry_run,
        resume_from=args.resume_from,
        single_task=args.single_task,
        verbose=args.verbose,
        parallel=args.parallel,
        skip_smoke=args.skip_smoke
    )


if __name__ == "__main__":
    main()
