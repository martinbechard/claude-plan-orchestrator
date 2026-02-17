#!/usr/bin/env -S python3 -u
"""
Auto-Pipeline: Automated backlog processing for Claude Code.

Monitors docs/defect-backlog/ and docs/feature-backlog/ for new items,
creates implementation plans via Claude, executes them via the plan
orchestrator, and archives completed items.

Usage:
    python scripts/auto-pipeline.py [--dry-run] [--once] [--verbose]

Copyright (c) 2025 Martin Bechard [martin.bechard@DevConsult.ca]
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import termios
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import yaml

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
except ImportError:
    print("[AUTO-PIPELINE] ERROR: watchdog not installed. Run: pip install watchdog")
    sys.exit(1)

# Import SlackNotifier from plan-orchestrator
import importlib.util
_po_spec = importlib.util.spec_from_file_location(
    "plan_orchestrator", "scripts/plan-orchestrator.py")
_po_mod = importlib.util.module_from_spec(_po_spec)
_po_spec.loader.exec_module(_po_mod)
SlackNotifier = _po_mod.SlackNotifier

# ─── Configuration ────────────────────────────────────────────────────

ORCHESTRATOR_CONFIG_PATH = ".claude/orchestrator-config.yaml"
DEFAULT_DEV_SERVER_PORT = 3000
DEFAULT_BUILD_COMMAND = "pnpm run build"
DEFAULT_TEST_COMMAND = "pnpm test"
DEFAULT_DEV_SERVER_COMMAND = "pnpm dev"
DEFAULT_AGENTS_DIR = ".claude/agents/"

DEFECT_DIR = "docs/defect-backlog"
FEATURE_DIR = "docs/feature-backlog"
COMPLETED_DEFECTS_DIR = "docs/completed-backlog/defects"
COMPLETED_FEATURES_DIR = "docs/completed-backlog/features"
COMPLETED_DIRS = {
    "defect": COMPLETED_DEFECTS_DIR,
    "feature": COMPLETED_FEATURES_DIR,
}
PLANS_DIR = ".claude/plans"
DESIGN_DIR = "docs/plans"
STOP_SEMAPHORE_PATH = ".claude/plans/.stop"
SAFETY_SCAN_INTERVAL_SECONDS = 60
PLAN_CREATION_TIMEOUT_SECONDS = 600
CHILD_SHUTDOWN_TIMEOUT_SECONDS = 10
RATE_LIMIT_BUFFER_SECONDS = 30
RATE_LIMIT_DEFAULT_WAIT_SECONDS = 3600
DEFAULT_MAX_QUOTA_PERCENT = 100.0
DEFAULT_QUOTA_CEILING_USD = 0.0
DEFAULT_RESERVED_BUDGET_USD = 0.0


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

# Pattern matching backlog item slugs (NN-slug-name format)
BACKLOG_SLUG_PATTERN = re.compile(r"^\d{2,}-[\w-]+$")

# Status patterns in backlog files that indicate already-processed items
COMPLETED_STATUS_PATTERN = re.compile(
    r"^##\s*Status:\s*(Fixed|Completed)", re.IGNORECASE | re.MULTILINE
)

# Rate limit detection (same pattern as plan-orchestrator.py)
RATE_LIMIT_PATTERN = re.compile(
    r"(?:You've hit your limit|you've hit your limit|Usage limit reached)"
    r".*?resets?\s+(\w+\s+\d{1,2})\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?)"
    r"(?:\s*\(([^)]+)\))?",
    re.IGNORECASE | re.DOTALL,
)
MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}

# Known locations for the claude binary
CLAUDE_BINARY_SEARCH_PATHS = [
    "/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/cli.js",
    "/usr/local/lib/node_modules/@anthropic-ai/claude-code/cli.js",
]

# Global state
VERBOSE = False
CLAUDE_CMD: list[str] = ["claude"]
_saved_terminal_settings = None  # Saved termios settings for restoration

# ─── Terminal Management ─────────────────────────────────────────────


def save_terminal_settings() -> None:
    """Save current terminal settings. Call before spawning child processes."""
    global _saved_terminal_settings
    try:
        if sys.stdin.isatty():
            _saved_terminal_settings = termios.tcgetattr(sys.stdin)
    except (termios.error, OSError):
        pass


def restore_terminal_settings() -> None:
    """Restore terminal settings after child process exits or is killed.

    Claude CLI modifies terminal settings (raw mode). If killed abruptly,
    settings aren't restored, leaving the terminal without echo and in a
    broken state. This fixes that.
    """
    global _saved_terminal_settings
    if _saved_terminal_settings is None:
        return
    try:
        if sys.stdin.isatty():
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, _saved_terminal_settings)
    except (termios.error, OSError):
        pass


# ─── Logging ──────────────────────────────────────────────────────────


_PIPELINE_PID = os.getpid()


def log(message: str) -> None:
    """Print a timestamped log message with PID for process tracking."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [AUTO-PIPELINE:{_PIPELINE_PID}] {message}", flush=True)


def verbose_log(message: str) -> None:
    """Print a verbose log message if verbose mode is enabled."""
    if VERBOSE:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] [VERBOSE:{_PIPELINE_PID}] {message}", flush=True)


# ─── Claude Binary Resolution ────────────────────────────────────────


def resolve_claude_binary() -> list[str]:
    """Find the claude binary, checking PATH then known install locations."""
    claude_path = shutil.which("claude")
    if claude_path:
        return [claude_path]

    for search_path in CLAUDE_BINARY_SEARCH_PATHS:
        if os.path.isfile(search_path):
            node_path = shutil.which("node")
            if node_path:
                return [node_path, search_path]

    npx_path = shutil.which("npx")
    if npx_path:
        return [npx_path, "@anthropic-ai/claude-code"]

    log("WARNING: Could not find 'claude' binary. Tasks will fail.")
    return ["claude"]


# ─── Output Streaming ────────────────────────────────────────────────


class OutputCollector:
    """Collects output from a subprocess and tracks stats."""

    def __init__(self):
        self.lines: list[str] = []
        self.bytes_received: int = 0
        self.line_count: int = 0

    def add_line(self, line: str) -> None:
        self.lines.append(line)
        self.bytes_received += len(line.encode("utf-8"))
        self.line_count += 1

    def get_output(self) -> str:
        return "".join(self.lines)


def stream_output(
    pipe, prefix: str, collector: OutputCollector, show_full: bool
) -> None:
    """Stream output from a subprocess pipe line by line."""
    try:
        for line in iter(pipe.readline, ""):
            if line:
                collector.add_line(line)
                if show_full:
                    ts = datetime.now().strftime("%H:%M:%S")
                    print(f"[{ts}] [{prefix}] {line.rstrip()}", flush=True)
    except Exception as e:
        if VERBOSE:
            verbose_log(f"Error streaming {prefix}: {e}")


# ─── Rate Limit Handling ─────────────────────────────────────────────


def parse_rate_limit_reset_time(output: str) -> Optional[datetime]:
    """Parse a rate limit reset time from Claude CLI output."""
    match = RATE_LIMIT_PATTERN.search(output)
    if not match:
        return None

    date_str = match.group(1).strip()
    time_str = match.group(2).strip()
    tz_str = match.group(3)

    try:
        parts = date_str.split()
        if len(parts) != 2:
            return None
        month_name, day_str = parts
        month = MONTH_NAMES.get(month_name.lower())
        if not month:
            return None
        day = int(day_str)

        time_match = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", time_str, re.IGNORECASE)
        if not time_match:
            return None
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or "0")
        ampm = time_match.group(3).lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        tz = ZoneInfo(tz_str) if tz_str else ZoneInfo("America/Toronto")
        now = datetime.now(tz)
        year = now.year
        reset_time = datetime(year, month, day, hour, minute, tzinfo=tz)

        if reset_time < now:
            reset_time = reset_time.replace(year=year + 1)

        return reset_time
    except (ValueError, KeyError):
        return None


def check_rate_limit(output: str) -> Optional[float]:
    """Check if output contains a rate limit message. Returns seconds to wait, or None."""
    if not re.search(r"(?:You've hit your limit|Usage limit reached)", output, re.IGNORECASE):
        return None

    reset_time = parse_rate_limit_reset_time(output)
    if reset_time:
        now = datetime.now(reset_time.tzinfo)
        wait_seconds = (reset_time - now).total_seconds() + RATE_LIMIT_BUFFER_SECONDS
        return max(wait_seconds, 0)

    return float(RATE_LIMIT_DEFAULT_WAIT_SECONDS)


# ─── Stop Semaphore ──────────────────────────────────────────────────


def check_stop_requested() -> bool:
    """Check if a graceful stop has been requested via semaphore file."""
    return os.path.exists(STOP_SEMAPHORE_PATH)


def clear_stop_semaphore() -> None:
    """Remove the stop semaphore file if it exists."""
    if os.path.exists(STOP_SEMAPHORE_PATH):
        os.remove(STOP_SEMAPHORE_PATH)
        log(f"Cleared stale stop semaphore: {STOP_SEMAPHORE_PATH}")


# ─── Backlog Scanning ────────────────────────────────────────────────


@dataclass
class BacklogItem:
    """A defect or feature backlog item."""
    path: str
    name: str
    slug: str
    item_type: str  # "defect" or "feature"

    @property
    def display_name(self) -> str:
        return f"{self.item_type}: {self.name}"


def is_item_completed(filepath: str) -> bool:
    """Check if a backlog item file has a completed/fixed status."""
    try:
        with open(filepath, "r") as f:
            content = f.read(2000)  # Only need the header
        return bool(COMPLETED_STATUS_PATTERN.search(content))
    except (IOError, OSError):
        return False


def scan_directory(directory: str, item_type: str) -> list[BacklogItem]:
    """Scan a backlog directory for processable .md files."""
    items: list[BacklogItem] = []
    dir_path = Path(directory)

    if not dir_path.exists():
        return items

    for md_file in sorted(dir_path.glob("*.md")):
        if md_file.name.startswith("."):
            continue
        if is_item_completed(str(md_file)):
            verbose_log(f"Skipping completed item: {md_file.name}")
            continue

        slug = md_file.stem  # filename without .md
        items.append(BacklogItem(
            path=str(md_file),
            name=md_file.stem.replace("-", " ").title(),
            slug=slug,
            item_type=item_type,
        ))

    return items


def parse_dependencies(filepath: str) -> list[str]:
    """Parse the ## Dependencies section from a backlog .md file.

    Extracts dependency slugs from lines like '- 03-karma-trust-system.md' or
    '- 03-karma-trust-system'. Non-backlog dependencies (e.g. 'Base application
    scaffold') that don't match the NN-slug pattern are silently skipped.

    Returns list of dependency slugs (e.g. ['03-karma-trust-system']).
    """
    try:
        with open(filepath, "r") as f:
            content = f.read()
    except (IOError, OSError):
        return []

    deps: list[str] = []
    in_deps_section = False

    for line in content.splitlines():
        stripped = line.strip()

        # Detect the Dependencies heading
        if re.match(r"^##\s+Dependencies", stripped, re.IGNORECASE):
            in_deps_section = True
            continue

        # Stop at the next heading
        if in_deps_section and stripped.startswith("##"):
            break

        if not in_deps_section:
            continue

        # Parse list items: '- 03-karma-trust-system.md' or '- 03-karma-trust-system'
        list_match = re.match(r"^-\s+(.+)", stripped)
        if not list_match:
            continue

        raw = list_match.group(1).strip()
        # Extract the filename portion (before any parenthetical comment or space)
        # e.g. '03-karma-trust-system.md (determines who can post)' -> '03-karma-trust-system.md'
        filename_part = re.split(r"\s+\(|$", raw)[0].strip()
        # Strip .md extension if present
        slug = filename_part.removesuffix(".md").strip()

        # Only include items matching the NN-slug backlog pattern
        if BACKLOG_SLUG_PATTERN.match(slug):
            deps.append(slug)
        else:
            verbose_log(f"Ignoring non-backlog dependency: '{raw}' in {filepath}")

    return deps


def completed_slugs() -> set[str]:
    """Build a set of completed backlog item slugs from the archive directories."""
    slugs: set[str] = set()

    for completed_dir_path in [COMPLETED_DEFECTS_DIR, COMPLETED_FEATURES_DIR]:
        completed_dir = Path(completed_dir_path)
        if not completed_dir.exists():
            continue
        for md_file in completed_dir.glob("*.md"):
            slugs.add(md_file.stem)

    return slugs


def scan_all_backlogs() -> list[BacklogItem]:
    """Scan both backlog directories with dependency filtering.

    Returns defects first, then features. Items whose dependencies are not
    all present in the completed/ directories are filtered out.
    """
    defects = scan_directory(DEFECT_DIR, "defect")
    features = scan_directory(FEATURE_DIR, "feature")
    all_items = defects + features

    # Lazy: only load completed slugs when needed for dependency resolution
    done: set[str] | None = None

    # Filter items with unsatisfied dependencies
    ready: list[BacklogItem] = []
    for item in all_items:
        deps = parse_dependencies(item.path)
        if not deps:
            ready.append(item)
            continue

        # First item with dependencies triggers the scan
        if done is None:
            done = completed_slugs()

        unsatisfied = [d for d in deps if d not in done]
        if unsatisfied:
            log(f"Skipped: {item.slug} (waiting on: {', '.join(unsatisfied)})")
        else:
            ready.append(item)

    return ready


# ─── Filesystem Watcher ──────────────────────────────────────────────


class BacklogWatcher(FileSystemEventHandler):
    """Watchdog handler that detects new/modified backlog items."""

    def __init__(self, event_callback):
        super().__init__()
        self.event_callback = event_callback

    def on_created(self, event):
        if isinstance(event, FileCreatedEvent) and event.src_path.endswith(".md"):
            verbose_log(f"File created: {event.src_path}")
            self.event_callback()

    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent) and event.src_path.endswith(".md"):
            verbose_log(f"File modified: {event.src_path}")
            self.event_callback()


# ─── Child Process Runner ────────────────────────────────────────────


@dataclass
class ProcessResult:
    """Result of a child process execution."""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    rate_limited: bool = False
    rate_limit_wait: Optional[float] = None


# Max chars from plan name used in report filenames (matches plan-orchestrator.py)
MAX_PLAN_NAME_LENGTH = 50


class SessionUsageTracker:
    """Accumulates usage reports across all work items in a pipeline session."""

    def __init__(self) -> None:
        self.work_item_costs: list[dict] = []
        self.total_cost_usd: float = 0.0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

    def record_from_report(self, report_path: str, work_item_name: str) -> None:
        """Read a usage report JSON and accumulate totals."""
        try:
            with open(report_path) as f:
                report = json.load(f)
            total = report.get("total", {})
            cost = total.get("cost_usd", 0.0)
            self.total_cost_usd += cost
            self.total_input_tokens += total.get("input_tokens", 0)
            self.total_output_tokens += total.get("output_tokens", 0)
            self.work_item_costs.append({
                "name": work_item_name,
                "cost_usd": cost,
            })
            log(f"[Usage] {work_item_name}: ${cost:.4f}")
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            pass  # Report not available, skip silently

    def format_session_summary(self) -> str:
        """Format session-level usage summary."""
        lines = ["\n=== Pipeline Session Usage ==="]
        lines.append(f"Total cost: ${self.total_cost_usd:.4f}")
        lines.append(
            f"Total tokens: {self.total_input_tokens:,} input / "
            f"{self.total_output_tokens:,} output"
        )
        if self.work_item_costs:
            lines.append("Per work item:")
            for item in self.work_item_costs:
                lines.append(f"  {item['name']}: ${item['cost_usd']:.4f}")
        return "\n".join(lines)

    def write_session_report(self) -> Optional[str]:
        """Write a session summary JSON file."""
        if not self.work_item_costs:
            return None
        log_dir = Path(".claude/plans/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_path = log_dir / f"pipeline-session-{timestamp}.json"
        report = {
            "session_timestamp": datetime.now().isoformat(),
            "total_cost_usd": self.total_cost_usd,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "work_items": self.work_item_costs,
        }
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        return str(report_path)


class PipelineBudgetGuard:
    """Checks session-level cost against budget limits before each work item."""

    def __init__(self, max_quota_percent: float, quota_ceiling_usd: float,
                 reserved_budget_usd: float = 0.0) -> None:
        self.max_quota_percent = max_quota_percent
        self.quota_ceiling_usd = quota_ceiling_usd
        self.reserved_budget_usd = reserved_budget_usd

    @property
    def is_enabled(self) -> bool:
        return self.quota_ceiling_usd > 0

    @property
    def effective_limit_usd(self) -> float:
        if self.quota_ceiling_usd <= 0:
            return float('inf')
        percent_limit = self.quota_ceiling_usd * (self.max_quota_percent / 100.0)
        if self.reserved_budget_usd > 0:
            reserve_limit = self.quota_ceiling_usd - self.reserved_budget_usd
            return min(percent_limit, reserve_limit)
        return percent_limit

    def can_proceed(self, session_cost_usd: float) -> tuple[bool, str]:
        """Check if session budget allows another work item."""
        if not self.is_enabled:
            return (True, "")
        limit = self.effective_limit_usd
        if session_cost_usd >= limit:
            pct = (session_cost_usd / self.quota_ceiling_usd * 100)
            reason = (
                f"Session budget limit reached: ${session_cost_usd:.4f} / ${limit:.4f} "
                f"({pct:.1f}% of ${self.quota_ceiling_usd:.2f} ceiling)"
            )
            return (False, reason)
        return (True, "")


def run_child_process(
    cmd: list[str],
    description: str,
    timeout: Optional[int] = None,
    show_output: bool = False,
) -> ProcessResult:
    """Run a child process with output streaming and crash detection."""
    start_time = time.time()
    log(f"Starting: {description}")
    verbose_log(f"Command: {' '.join(cmd[:3])}...")

    # Save terminal settings before child process can corrupt them
    save_terminal_settings()

    stdout_collector = OutputCollector()
    stderr_collector = OutputCollector()

    try:
        # Force unbuffered output from Python child processes (orchestrator)
        # so their output streams in real-time instead of in chunks
        child_env = os.environ.copy()
        child_env["PYTHONUNBUFFERED"] = "1"
        child_env.pop("CLAUDECODE", None)  # Allow spawning Claude from within Claude Code

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,  # Prevent children from modifying terminal settings
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.getcwd(),
            env=child_env,
        )

        # Track active child for signal handling
        global _active_child_process
        _active_child_process = process
        log(f"Spawned child process PID {process.pid}: {description}")

        # Start output streaming threads
        stdout_thread = threading.Thread(
            target=stream_output,
            args=(process.stdout, description, stdout_collector, show_output or VERBOSE),
        )
        stderr_thread = threading.Thread(
            target=stream_output,
            args=(process.stderr, f"{description} ERR", stderr_collector, show_output or VERBOSE),
        )
        stdout_thread.start()
        stderr_thread.start()

        # Monitor process with optional timeout
        if not (show_output or VERBOSE):
            print(f"  [{description}] Working", end="", flush=True)

        while process.poll() is None:
            time.sleep(1)
            elapsed = time.time() - start_time

            if not (show_output or VERBOSE):
                current_bytes = stdout_collector.bytes_received + stderr_collector.bytes_received
                if current_bytes > 0 and int(elapsed) % 10 == 0:
                    print(".", end="", flush=True)

            if timeout and elapsed > timeout:
                if not (show_output or VERBOSE):
                    print(" [TIMEOUT]", flush=True)
                log(f"TIMEOUT after {timeout}s: {description}")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                stdout_thread.join(timeout=2)
                stderr_thread.join(timeout=2)
                _active_child_process = None
                restore_terminal_settings()
                duration = time.time() - start_time
                return ProcessResult(
                    success=False, exit_code=-1,
                    stdout=stdout_collector.get_output(),
                    stderr=stderr_collector.get_output(),
                    duration_seconds=duration,
                )

        # Process finished
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        _active_child_process = None
        restore_terminal_settings()

        duration = time.time() - start_time
        exit_code = process.returncode
        log(f"Child PID {process.pid} exited with code {exit_code} after {duration:.0f}s: {description}")

        if not (show_output or VERBOSE):
            status = "done" if exit_code == 0 else f"FAILED (exit {exit_code})"
            print(
                f" {status} ({stdout_collector.line_count} lines, "
                f"{stdout_collector.bytes_received:,} bytes, {duration:.0f}s)",
                flush=True,
            )

        full_output = stdout_collector.get_output() + stderr_collector.get_output()

        # Check for rate limiting
        rate_limit_wait = check_rate_limit(full_output)
        if rate_limit_wait is not None:
            return ProcessResult(
                success=False, exit_code=exit_code,
                stdout=stdout_collector.get_output(),
                stderr=stderr_collector.get_output(),
                duration_seconds=duration,
                rate_limited=True,
                rate_limit_wait=rate_limit_wait,
            )

        return ProcessResult(
            success=(exit_code == 0),
            exit_code=exit_code,
            stdout=stdout_collector.get_output(),
            stderr=stderr_collector.get_output(),
            duration_seconds=duration,
        )

    except FileNotFoundError as e:
        _active_child_process = None
        restore_terminal_settings()
        duration = time.time() - start_time
        log(f"ERROR: Command not found: {e}")
        return ProcessResult(
            success=False, exit_code=-1, stdout="", stderr=str(e),
            duration_seconds=duration,
        )
    except Exception as e:
        _active_child_process = None
        restore_terminal_settings()
        duration = time.time() - start_time
        log(f"ERROR: Unexpected error running {description}: {e}")
        return ProcessResult(
            success=False, exit_code=-1, stdout="", stderr=str(e),
            duration_seconds=duration,
        )


# Active child process for signal handling
_active_child_process: Optional[subprocess.Popen] = None


# ─── Plan Creation ────────────────────────────────────────────────────

PLAN_CREATION_PROMPT_TEMPLATE = """You are creating an implementation plan for a backlog item.

## Instructions

1. Read the backlog item file: {item_path}
2. Read procedure-coding-rules.md for coding standards
3. Read an existing YAML plan for format reference: look at .claude/plans/*.yaml files
4. Read the CLAUDE.md file for project conventions
5. If the backlog item has a ## Verification Log section, READ IT CAREFULLY.
   Previous fix attempts and their verification results are recorded there.
   Your plan MUST address any unresolved findings from prior verifications.

## What to produce

1. Create a design document at: docs/plans/{date}-{slug}-design.md
   - Brief architecture overview
   - Key files to create/modify
   - Design decisions

2. Create a YAML plan at: .claude/plans/{slug}.yaml
   - Use the exact format: meta + sections with nested tasks
   - Each section has: id, name, status: pending, tasks: [...]
   - Each task has: id, name, description, status: pending
   - Task descriptions should be detailed enough for a fresh Claude session to execute
   - Include: documentation tasks, implementation tasks, unit tests, verification
   - The verification task should run {build_command} and {test_command}

3. Validate the plan: python scripts/plan-orchestrator.py --plan .claude/plans/{slug}.yaml --dry-run
   - If validation fails, fix the YAML format and retry

4. Git commit both files with message: "plan: add {slug} design and YAML plan"

## Backlog item type: {item_type}

## Agent Selection

Tasks can specify which agent should execute them via the optional "agent" field.
Available agents are in {agents_dir}:

- **coder**: Implementation specialist. Use for coding, implementation, and
  modification tasks. This is the default if no agent is specified.
- **code-reviewer**: Read-only reviewer. Use for verification, review, and
  compliance-checking tasks.
- **systems-designer**: Architecture and data model designer. Use for Phase 0
  design competition tasks that focus on system architecture, data models,
  and API boundaries. Read-only.
- **ux-designer**: Visual and interaction designer. Use for Phase 0
  design competition tasks that focus on wireframes, user workflows,
  and UI component specs. Read-only.
- **planner**: Design-to-implementation bridge. Use for tasks that read a
  winning design and create YAML implementation phases. Sets plan_modified: true.

Example:
  - id: '2.1'
    name: Implement the feature
    agent: coder
    status: pending
    description: ...

  - id: '3.1'
    name: Review code quality
    agent: code-reviewer
    status: pending
    description: ...

Phase 0 Competition Example:
  - id: '0.1'
    name: Generate Design 1
    agent: systems-designer
    parallel_group: phase-0-designs
    status: pending
    description: ...

  - id: '0.7'
    name: Extend plan with implementation tasks
    agent: planner
    status: pending
    description: ...

If you do not set the agent field, the orchestrator will infer it from the
task name and description (review/verification -> code-reviewer, design/architecture
-> systems-designer, plan extension -> planner, everything else -> coder).

## Validation (Optional)

Plans can enable per-task validation by adding a validation block to the meta section. When enabled, a validator agent runs after each coder task to independently verify the result.

Example meta configuration:

  meta:
    validation:
      enabled: true
      run_after:
        - coder
      validators:
        - validator
      max_validation_attempts: 1

The validator produces PASS/WARN/FAIL verdicts:
- PASS: task proceeds normally
- WARN: task completes but warnings are logged
- FAIL: task is retried with validation findings prepended to the prompt

For defect fixes, use the issue-verifier validator instead of or in addition to the default validator. This validator reads the original defect file and checks whether reported symptoms are resolved.

## Important
- Follow the CLAUDE.md change workflow order: docs -> code -> tests -> verification
- For defects: include a task to verify the fix with a regression test
- For features: include documentation, implementation, unit tests, and E2E tests as appropriate
- Keep tasks focused - each task should be completable in one Claude session (under 10 minutes)
- If the backlog item has a ## Verification Log with unresolved findings, your plan
  must specifically address those findings. The previous code fix may be correct but
  incomplete (e.g., operational steps not executed, data not deployed).
"""


def reset_interrupted_tasks(plan_path: str) -> int:
    """Reset in_progress tasks back to pending and clear their attempt counters.

    When the pipeline is killed mid-task, the orchestrator leaves tasks as
    'in_progress'. On recovery, these should be treated as fresh retries,
    not as failed attempts. Returns the number of tasks reset.
    """
    try:
        with open(plan_path, "r") as f:
            plan = yaml.safe_load(f)
    except (IOError, yaml.YAMLError) as e:
        log(f"WARNING: Could not read plan for reset: {e}")
        return 0

    if not plan or "sections" not in plan:
        return 0

    reset_count = 0
    for section in plan.get("sections", []):
        for task in section.get("tasks", []):
            if task.get("status") == "in_progress":
                task_id = task.get("id", "?")
                task["status"] = "pending"
                # Clear attempt counter so interrupted tasks don't burn retries
                task.pop("attempts", None)
                task.pop("last_attempt", None)
                reset_count += 1
                log(f"  Reset interrupted task {task_id}: in_progress -> pending")

        # Also reset section status if it was in_progress
        if section.get("status") == "in_progress":
            section["status"] = "pending"

    if reset_count > 0:
        try:
            with open(plan_path, "w") as f:
                yaml.dump(plan, f, default_flow_style=False, sort_keys=False)
            log(f"Reset {reset_count} interrupted task(s)")
        except IOError as e:
            log(f"WARNING: Could not write plan after reset: {e}")
            return 0

    return reset_count


def check_existing_plan(item: BacklogItem) -> Optional[str]:
    """Check if a valid YAML plan already exists for this item.

    Returns the plan path if it exists and is valid, None otherwise.
    This enables recovery: if the pipeline was interrupted after plan creation
    but before completion, we skip straight to execution on restart.
    """
    plan_path = f"{PLANS_DIR}/{item.slug}.yaml"
    if not os.path.exists(plan_path):
        return None

    # Reset any tasks stuck as in_progress from a previous interrupted run
    reset_interrupted_tasks(plan_path)

    # Count task statuses from YAML directly (faster than dry-run validation)
    try:
        with open(plan_path, "r") as f:
            plan = yaml.safe_load(f)
        if not plan or "sections" not in plan:
            log(f"WARNING: Plan file is empty or invalid: {plan_path}")
            return None
        done = 0
        pending = 0
        for section in plan.get("sections", []):
            for task in section.get("tasks", []):
                status = task.get("status", "pending")
                if status == "completed":
                    done += 1
                elif status == "pending":
                    pending += 1
    except (IOError, yaml.YAMLError):
        log(f"WARNING: Could not parse plan file: {plan_path}")
        return None

    if pending == 0 and done > 0:
        log(f"Found existing plan: {plan_path} (all {done} tasks completed)")
    else:
        log(f"Found existing plan: {plan_path} ({done} completed, {pending} pending)")
    return plan_path


def create_plan(item: BacklogItem, dry_run: bool = False) -> Optional[str]:
    """Create a design doc and YAML plan for a backlog item.

    Returns the plan YAML path on success, or None on failure.
    If a valid plan already exists (from a previous interrupted run), returns it directly.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    plan_path = f"{PLANS_DIR}/{item.slug}.yaml"

    if dry_run:
        existing = os.path.exists(plan_path)
        if existing:
            log(f"[DRY RUN] Would resume existing plan: {plan_path}")
        else:
            log(f"[DRY RUN] Would create plan for: {item.display_name}")
            log(f"  Design: {DESIGN_DIR}/{date_str}-{item.slug}-design.md")
            log(f"  Plan:   {plan_path}")
        return plan_path

    # Check for existing plan (recovery from interrupted run)
    existing_plan = check_existing_plan(item)
    if existing_plan:
        log(f"Resuming from existing plan (skipping Phase 1)")
        return existing_plan

    prompt = PLAN_CREATION_PROMPT_TEMPLATE.format(
        item_path=item.path,
        date=date_str,
        slug=item.slug,
        item_type=item.item_type,
        agents_dir=AGENTS_DIR,
        build_command=BUILD_COMMAND,
        test_command=TEST_COMMAND,
    )

    cmd = [*CLAUDE_CMD, "--dangerously-skip-permissions", "--print", prompt]

    result = run_child_process(
        cmd,
        description=f"Plan creation for {item.slug}",
        timeout=PLAN_CREATION_TIMEOUT_SECONDS,
        show_output=VERBOSE,
    )

    if result.rate_limited:
        return None  # Caller handles rate limit sleep

    if not result.success:
        log(f"Plan creation failed for {item.display_name} (exit {result.exit_code})")
        if result.stderr:
            log(f"  stderr: {result.stderr[:500]}")
        return None

    # Verify the plan was created and is valid
    if not os.path.exists(plan_path):
        log(f"Plan file not created at expected path: {plan_path}")
        return None

    # Dry-run validation
    validate_result = run_child_process(
        ["python", "scripts/plan-orchestrator.py", "--plan", plan_path, "--dry-run"],
        description=f"Plan validation for {item.slug}",
        timeout=30,
    )

    if not validate_result.success:
        log(f"Plan validation failed for {item.slug}")
        if validate_result.stdout:
            log(f"  output: {validate_result.stdout[:500]}")
        return None

    # Count tasks from dry-run output
    task_count = validate_result.stdout.count("Result: SUCCESS")
    log(f"Plan created and validated: {plan_path} ({task_count} tasks)")
    return plan_path


# ─── Dev Server Management ───────────────────────────────────────────

# Track whether we stopped the dev server so we know to restart it
_dev_server_was_running = False


def find_dev_server_pid() -> Optional[int]:
    """Find the PID of the Next.js dev server on DEV_SERVER_PORT. Returns None if not running."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{DEV_SERVER_PORT}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            # lsof may return multiple PIDs (parent + child); take the first
            pids = result.stdout.strip().split("\n")
            return int(pids[0])
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


def stop_dev_server() -> bool:
    """Stop the dev server on DEV_SERVER_PORT if running. Returns True if it was running."""
    global _dev_server_was_running
    pid = find_dev_server_pid()
    if pid is None:
        verbose_log(f"No dev server found on port {DEV_SERVER_PORT}")
        _dev_server_was_running = False
        return False

    log(f"Stopping dev server (PID {pid}) on port {DEV_SERVER_PORT}...")
    try:
        os.kill(pid, signal.SIGTERM)
        # Wait for it to stop
        for _ in range(10):
            time.sleep(1)
            if find_dev_server_pid() is None:
                break
        # Force kill if still running
        if find_dev_server_pid() is not None:
            remaining_pid = find_dev_server_pid()
            if remaining_pid:
                os.kill(remaining_pid, signal.SIGKILL)
                time.sleep(1)
    except OSError as e:
        verbose_log(f"Error stopping dev server: {e}")

    _dev_server_was_running = True
    log("Dev server stopped")
    return True


def start_dev_server() -> None:
    """Restart the dev server if it was running before we stopped it."""
    global _dev_server_was_running
    if not _dev_server_was_running:
        verbose_log("Dev server was not running before - skipping restart")
        return

    # Check it's not already running (e.g. orchestrator started one)
    if find_dev_server_pid() is not None:
        verbose_log("Dev server already running - skipping restart")
        _dev_server_was_running = False
        return

    log(f"Restarting dev server on port {DEV_SERVER_PORT}...")
    try:
        subprocess.Popen(
            DEV_SERVER_COMMAND.split(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.getcwd(),
            start_new_session=True,  # Detach from our process group
        )
        # Wait briefly for startup
        time.sleep(3)
        if find_dev_server_pid() is not None:
            log("Dev server restarted")
        else:
            log("WARNING: Dev server may not have started - check manually")
    except OSError as e:
        log(f"WARNING: Failed to restart dev server: {e}")

    _dev_server_was_running = False


# ─── Plan Execution ───────────────────────────────────────────────────


def execute_plan(plan_path: str, dry_run: bool = False) -> bool:
    """Execute a YAML plan via the plan orchestrator. Returns True on success."""
    if dry_run:
        log(f"[DRY RUN] Would execute plan: {plan_path}")
        return True

    # Stop dev server before orchestrator runs (builds conflict with turbopack cache)
    stop_dev_server()

    try:
        orch_cmd = ["python", "scripts/plan-orchestrator.py", "--plan", plan_path]
        if VERBOSE:
            orch_cmd.append("--verbose")

        result = run_child_process(
            orch_cmd,
            description=f"Orchestrator: {os.path.basename(plan_path)}",
            timeout=None,  # Orchestrator has its own timeouts
            show_output=True,  # Always stream orchestrator output
        )

        if result.rate_limited and result.rate_limit_wait:
            log(f"Rate limited during orchestrator. Waiting {result.rate_limit_wait:.0f}s...")
            try:
                time.sleep(result.rate_limit_wait)
            except KeyboardInterrupt:
                log("Interrupted during rate limit wait")
                return False
            # After rate limit, the orchestrator needs to be re-run
            # It will resume from where it left off (tasks already completed in YAML)
            log("Resuming orchestrator after rate limit...")
            return execute_plan(plan_path, dry_run)

        if not result.success:
            log(f"Orchestrator failed (exit {result.exit_code})")
            # Check for partial completion
            completed = result.stdout.count("Result: SUCCESS")
            failed = result.stdout.count("Result: FAILED")
            log(f"  Tasks completed: {completed}, Tasks failed: {failed}")
            return False

        # Parse summary from orchestrator output
        completed = result.stdout.count("Result: SUCCESS")
        log(f"Orchestrator completed: {completed} tasks")
        return True
    finally:
        # Always restart dev server after orchestrator, even on failure
        start_dev_server()


# ─── Archive ──────────────────────────────────────────────────────────


def find_in_progress_plans() -> list[str]:
    """Find YAML plans that have pending tasks (started but not finished).

    When the pipeline restarts, any plan with remaining pending tasks must
    be completed before new backlog items are processed. This prevents the
    pipeline from starting new work while previous plans are incomplete.
    Excludes the sample-plan.yaml template.
    """
    in_progress: list[str] = []
    plans_dir = Path(PLANS_DIR)

    if not plans_dir.exists():
        return in_progress

    for yaml_file in sorted(plans_dir.glob("*.yaml")):
        if yaml_file.name == "sample-plan.yaml":
            continue

        try:
            with open(yaml_file, "r") as f:
                plan = yaml.safe_load(f)
        except (IOError, yaml.YAMLError):
            continue

        if not plan or "sections" not in plan:
            continue

        has_completed = False
        has_pending = False
        for section in plan.get("sections", []):
            for task in section.get("tasks", []):
                status = task.get("status", "pending")
                if status == "completed":
                    has_completed = True
                elif status in ("pending", "in_progress"):
                    has_pending = True

        # A plan is "in progress" if it has both completed and pending tasks
        # (i.e. it was started but not finished)
        if has_completed and has_pending:
            in_progress.append(str(yaml_file))

    return in_progress


def archive_item(item: BacklogItem, dry_run: bool = False) -> bool:
    """Move a completed backlog item to the top-level archive directory."""
    source = item.path
    dest_dir = COMPLETED_DIRS[item.item_type]
    dest = os.path.join(dest_dir, os.path.basename(item.path))

    if dry_run:
        log(f"[DRY RUN] Would archive: {source} -> {dest}")
        return True

    try:
        os.makedirs(dest_dir, exist_ok=True)
        shutil.move(source, dest)

        # Git commit the move
        subprocess.run(["git", "add", source, dest], capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"chore: archive completed {item.item_type} {item.slug}"],
            capture_output=True, check=True,
        )
        log(f"Archived: {source} -> {dest}")
        return True
    except (OSError, subprocess.CalledProcessError) as e:
        log(f"WARNING: Failed to archive {source}: {e}")
        return False


# ─── Symptom Verification ─────────────────────────────────────────────

VERIFICATION_PROMPT_TEMPLATE = """You are a VERIFIER. Your job is to check whether a defect's
reported symptoms have been fully resolved. You must NOT fix anything. You only observe and report.

## Instructions

1. Read the defect file: {item_path}
2. Read the "Expected Behavior" and "Actual Behavior" sections carefully
3. Read the "Fix Required" section for any commands or checks that should be performed
4. If there is a "## Verification Log" section, read previous verification attempts

## What to check

For each item in "Fix Required" or "Verification" that describes a testable condition:
- Run the command or check the condition
- Record whether it passed or failed
- Record the actual output or observation

Also check:
- Does `{build_command}` pass? (code correctness)
- Do unit tests pass? (`{test_command}`)
- Is the reported symptom actually gone? (the MOST IMPORTANT check)

## What to produce

Append your findings to the defect file at {item_path}.
If no "## Verification Log" section exists, create one at the end of the file.

Use this exact format (the count MUST increment from the last entry, or start at 1):

```
### Verification #{count} - YYYY-MM-DD HH:MM

**Verdict: PASS** or **Verdict: FAIL**

**Checks performed:**
- [ ] or [x] Build passes
- [ ] or [x] Unit tests pass
- [ ] or [x] (each specific symptom check from the defect)

**Findings:**
(describe what you observed for each check - be specific about command outputs)
```

## CRITICAL RULES

- Do NOT modify any code files
- Do NOT fix anything
- Do NOT change the defect's ## Status line
- ONLY read, run verification commands, and append findings to the defect file
- If you need the dev server running for a check, start it with `{dev_server_command}`, wait for it,
  run your check, then stop it
- Git commit the updated defect file with message: "verify: {slug} verification #{count}"
"""

# Maximum number of verify-then-fix cycles before giving up
MAX_VERIFICATION_CYCLES = 3


def count_verification_attempts(item_path: str) -> int:
    """Count how many verification entries exist in the defect file."""
    try:
        with open(item_path, "r") as f:
            content = f.read()
    except IOError:
        return 0

    return len(re.findall(r"### Verification #\d+", content))


def last_verification_passed(item_path: str) -> bool:
    """Check if the most recent verification entry has Verdict: PASS."""
    try:
        with open(item_path, "r") as f:
            content = f.read()
    except IOError:
        return False

    # Find all verdict lines and check the last one
    verdicts = re.findall(r"\*\*Verdict:\s*(PASS|FAIL)\*\*", content, re.IGNORECASE)
    if not verdicts:
        return False
    return verdicts[-1].upper() == "PASS"


def verify_item(item: BacklogItem, dry_run: bool = False) -> bool:
    """Run symptom verification on a completed defect fix.

    Returns True if verification passed, False if it failed.
    The verifier appends findings to the defect file regardless of outcome.
    """
    if item.item_type != "defect":
        # Features don't have symptom verification (yet)
        return True

    attempt_count = count_verification_attempts(item.path) + 1

    if dry_run:
        log(f"[DRY RUN] Would verify symptoms for: {item.display_name} (attempt #{attempt_count})")
        return True

    log(f"Running symptom verification #{attempt_count}...")

    prompt = VERIFICATION_PROMPT_TEMPLATE.format(
        item_path=item.path,
        slug=item.slug,
        count=attempt_count,
        build_command=BUILD_COMMAND,
        test_command=TEST_COMMAND,
        dev_server_command=DEV_SERVER_COMMAND,
    )

    cmd = [*CLAUDE_CMD, "--dangerously-skip-permissions", "--print", prompt]

    result = run_child_process(
        cmd,
        description=f"Verify {item.slug} #{attempt_count}",
        timeout=PLAN_CREATION_TIMEOUT_SECONDS,
        show_output=VERBOSE,
    )

    if result.rate_limited:
        log("Rate limited during verification")
        return False

    if not result.success:
        log(f"Verification process failed (exit {result.exit_code})")
        return False

    # Check if the verifier recorded a PASS
    passed = last_verification_passed(item.path)
    if passed:
        log(f"Verification #{attempt_count}: PASSED")
    else:
        log(f"Verification #{attempt_count}: FAILED - defect stays in queue for next cycle")

    return passed


# ─── Main Pipeline ────────────────────────────────────────────────────


def _read_plan_name(plan_path: str) -> str:
    """Read the plan name from a YAML plan file's meta.name field."""
    try:
        with open(plan_path, "r") as f:
            plan = yaml.safe_load(f)
        return plan.get("meta", {}).get("name", "unknown") if plan else "unknown"
    except (IOError, yaml.YAMLError):
        return "unknown"


def _try_record_usage(
    session_tracker: SessionUsageTracker, plan_path: str, work_item_name: str
) -> None:
    """Try to find and record a usage report after orchestrator execution."""
    plan_name = _read_plan_name(plan_path)
    safe_name = plan_name.lower().replace(" ", "-")[:MAX_PLAN_NAME_LENGTH]
    report_path = Path(".claude/plans/logs") / f"{safe_name}-usage-report.json"
    if report_path.exists():
        session_tracker.record_from_report(str(report_path), work_item_name)


def process_item(
    item: BacklogItem,
    dry_run: bool = False,
    session_tracker: Optional[SessionUsageTracker] = None,
) -> bool:
    """Process a single backlog item through the full pipeline.

    For defects, runs a verify-then-fix cycle:
      Phase 1: Create plan
      Phase 2: Execute plan (orchestrator)
      Phase 3: Verify symptoms resolved (verifier agent, append-only)
        - If PASS: Phase 4 (archive)
        - If FAIL: Delete stale plan, loop back to Phase 1
          (next plan creation sees verification findings in the defect file)
      Phase 4: Archive

    Returns True on success, False on failure or max cycles exceeded.
    """
    slack = SlackNotifier()
    item_start = time.time()
    log(f"{'=' * 60}")
    log(f"Processing {item.display_name}")
    log(f"  Type: {item.item_type}")
    log(f"  File: {item.path}")
    log(f"  Pipeline PID: {_PIPELINE_PID}")
    log(f"{'=' * 60}")

    slack.send_status(
        f"*Pipeline: processing* {item.display_name}\n"
        f"Type: {item.item_type}",
        level="info"
    )

    prior_verifications = count_verification_attempts(item.path)

    for cycle in range(MAX_VERIFICATION_CYCLES):
        cycle_num = prior_verifications + cycle + 1

        if check_stop_requested():
            log("Stop requested during processing.")
            return False

        # Phase 1: Create plan
        log(f"Phase 1: Creating plan (cycle {cycle + 1}/{MAX_VERIFICATION_CYCLES})...")
        plan_path = create_plan(item, dry_run)
        if not plan_path:
            log(f"FAILED: Could not create plan for {item.display_name}")
            slack.send_status(
                f"*Pipeline: failed* {item.display_name}",
                level="error"
            )
            return False

        # Phase 2: Execute plan
        log("Phase 2: Running orchestrator...")
        success = execute_plan(plan_path, dry_run)

        # Record usage from the orchestrator's report (regardless of success)
        if session_tracker and plan_path:
            _try_record_usage(session_tracker, plan_path, item.display_name)

        if not success:
            log(f"FAILED: Orchestrator failed for {item.display_name}")
            slack.send_status(
                f"*Pipeline: failed* {item.display_name}",
                level="error"
            )
            return False

        # Phase 3: Verify symptoms
        log("Phase 3: Verifying symptoms...")
        verified = verify_item(item, dry_run)

        if verified:
            # Phase 4: Archive
            log("Phase 4: Archiving...")
            archive_item(item, dry_run)

            elapsed = time.time() - item_start
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            log(f"Item complete: {item.display_name} ({minutes}m {seconds}s)")
            slack.send_status(
                f"*Pipeline: completed* {item.display_name}\n"
                f"Duration: {minutes}m {seconds}s",
                level="success"
            )
            return True

        # Verification failed - prepare for next cycle
        log(f"Verification failed (cycle {cycle + 1}/{MAX_VERIFICATION_CYCLES})")

        if cycle + 1 < MAX_VERIFICATION_CYCLES:
            # Delete the stale plan so next cycle creates a fresh one
            # that incorporates the verification findings
            if plan_path and os.path.exists(plan_path):
                os.remove(plan_path)
                log(f"Removed stale plan: {plan_path}")
            log("Cycling back to Phase 1 with verification findings...")
        else:
            log(f"Max verification cycles ({MAX_VERIFICATION_CYCLES}) reached for {item.slug}")
            log("Defect stays in queue with accumulated verification findings.")

    return False


def main_loop(dry_run: bool = False, once: bool = False,
              budget_guard: Optional[PipelineBudgetGuard] = None) -> None:
    """Main processing loop with filesystem watching."""
    global VERBOSE, CLAUDE_CMD

    # Save terminal settings at startup (before any child can corrupt them)
    save_terminal_settings()

    # Resolve Claude binary
    CLAUDE_CMD = resolve_claude_binary()
    log(f"Claude binary: {' '.join(CLAUDE_CMD)}")

    # Clear stale stop semaphore
    clear_stop_semaphore()

    # Track items that failed in this session (don't retry)
    failed_items: set[str] = set()

    # Track usage across all work items in this session
    session_tracker = SessionUsageTracker()

    # Event to signal new items detected
    new_item_event = threading.Event()

    def on_new_item():
        new_item_event.set()

    # Set up filesystem watcher
    observer = Observer()
    watcher = BacklogWatcher(on_new_item)

    for watch_dir in [DEFECT_DIR, FEATURE_DIR]:
        if os.path.isdir(watch_dir):
            observer.schedule(watcher, watch_dir, recursive=False)
            verbose_log(f"Watching directory: {watch_dir}")

    if not once:
        observer.start()
        log("Filesystem watcher started")

    slack = SlackNotifier()

    try:
        while True:
            # Check stop semaphore
            if check_stop_requested():
                log("Stop requested via semaphore. Exiting.")
                slack.send_status("*Pipeline stopped:* Graceful stop requested", level="warning")
                break

            # Resume in-progress plans before scanning for new work.
            # This ensures partially-completed plans finish before new items start.
            if not dry_run:
                in_progress_plans = find_in_progress_plans()
                if in_progress_plans:
                    log(f"Found {len(in_progress_plans)} in-progress plan(s) to resume")
                    for plan_path in in_progress_plans:
                        if check_stop_requested():
                            break
                        log(f"  Resuming: {os.path.basename(plan_path)}")
                        success = execute_plan(plan_path, dry_run)
                        # Record usage from the orchestrator's report
                        plan_basename = os.path.basename(plan_path)
                        _try_record_usage(
                            session_tracker, plan_path, f"resumed: {plan_basename}"
                        )
                        if not success:
                            failed_items.add(plan_path)
                            log(f"In-progress plan failed: {plan_path}")
                    # After resuming, re-scan (completed plans may unblock new items)
                    continue

            # Poll for inbound Slack messages at scan checkpoint
            slack.process_inbound()

            # Scan for items (with dependency filtering)
            items = scan_all_backlogs()

            # Filter out previously failed items
            items = [i for i in items if i.path not in failed_items]

            if items:
                log(f"Found {len(items)} item(s) to process")
                for i, item in enumerate(items, 1):
                    log(f"  {i}. [{item.item_type}] {item.slug}")
            else:
                if once:
                    log("No items to process. Exiting (--once mode).")
                    break
                log(f"No items to process. Watching for new items...")
                log(f"  (Ctrl+C or 'touch {STOP_SEMAPHORE_PATH}' to stop)")

                # Poll for inbound Slack messages during idle wait
                slack.process_inbound()

                # Wait for either a filesystem event or the safety scan interval
                new_item_event.clear()
                new_item_event.wait(timeout=SAFETY_SCAN_INTERVAL_SECONDS)
                continue

            # In --once mode, process only the first item then exit
            if once:
                item = items[0]
                if budget_guard and budget_guard.is_enabled:
                    can_go, reason = budget_guard.can_proceed(session_tracker.total_cost_usd)
                    if not can_go:
                        log(f"Budget limit reached: {reason}")
                        log("Stopping pipeline due to budget constraint.")
                        break
                log(f"Processing single item (--once mode): [{item.item_type}] {item.slug}")
                success = process_item(item, dry_run, session_tracker)
                if not success:
                    log(f"Item failed: {item.slug}")
                log("Exiting (--once mode).")
                break

            # Process items one at a time
            for item in items:
                if check_stop_requested():
                    log("Stop requested. Finishing current session.")
                    slack.send_status("*Pipeline stopped:* Graceful stop requested", level="warning")
                    break

                if budget_guard and budget_guard.is_enabled:
                    can_go, reason = budget_guard.can_proceed(session_tracker.total_cost_usd)
                    if not can_go:
                        log(f"Budget limit reached: {reason}")
                        log("Stopping pipeline due to budget constraint.")
                        break

                success = process_item(item, dry_run, session_tracker)
                if not success:
                    failed_items.add(item.path)
                    log(f"Item failed - will not retry in this session: {item.slug}")

                # Poll for inbound Slack messages after processing each item
                slack.process_inbound()

            # Brief pause before next scan
            time.sleep(2)

    except KeyboardInterrupt:
        log("Interrupted by user. Shutting down...")
    finally:
        # Print and write session usage summary
        print(session_tracker.format_session_summary())
        session_report = session_tracker.write_session_report()
        if session_report:
            log(f"[Session usage report: {session_report}]")

        if not once:
            observer.stop()
            observer.join(timeout=5)
        restore_terminal_settings()
        log("Auto-pipeline stopped.")


# ─── Signal Handling ──────────────────────────────────────────────────


def handle_signal(signum, frame):
    """Handle SIGINT/SIGTERM gracefully."""
    sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
    log(f"Received {sig_name}. Shutting down gracefully...")

    # Terminate active child process if any
    if _active_child_process and _active_child_process.poll() is None:
        log(f"Terminating active child process (PID {_active_child_process.pid})...")
        _active_child_process.terminate()
        try:
            _active_child_process.wait(timeout=CHILD_SHUTDOWN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            log("Child process did not exit gracefully. Killing...")
            _active_child_process.kill()
            _active_child_process.wait()

    # Restore terminal settings (child processes like Claude CLI can corrupt them)
    restore_terminal_settings()

    sys.exit(0)


# ─── Entry Point ──────────────────────────────────────────────────────


def main():
    global VERBOSE

    parser = argparse.ArgumentParser(
        description="Auto-Pipeline: automated backlog processing for Claude Code"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be processed without spawning Claude or orchestrator",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Process the first item found then exit (single-item mode)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Stream all child output in detail",
    )
    parser.add_argument(
        "--max-budget-pct", type=float, default=None,
        metavar="N",
        help="Maximum percentage of quota ceiling to use (default: 100)",
    )
    parser.add_argument(
        "--quota-ceiling", type=float, default=None,
        metavar="N.NN",
        help="Weekly quota ceiling in USD (default: 0 = no limit)",
    )
    parser.add_argument(
        "--reserved-budget", type=float, default=None,
        metavar="N.NN",
        help="USD to reserve for interactive use (default: 0)",
    )
    args = parser.parse_args()
    VERBOSE = args.verbose

    # Register signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    log("Starting auto-pipeline")
    log(f"  Defect backlog: {DEFECT_DIR}/")
    log(f"  Feature backlog: {FEATURE_DIR}/")
    log(f"  Mode: {'dry-run' if args.dry_run else 'once' if args.once else 'continuous watch'}")

    budget_guard = PipelineBudgetGuard(
        max_quota_percent=args.max_budget_pct or DEFAULT_MAX_QUOTA_PERCENT,
        quota_ceiling_usd=args.quota_ceiling or DEFAULT_QUOTA_CEILING_USD,
        reserved_budget_usd=args.reserved_budget or DEFAULT_RESERVED_BUDGET_USD,
    )
    if budget_guard.is_enabled:
        log(f"  Budget: ${budget_guard.effective_limit_usd:.2f} limit")

    main_loop(dry_run=args.dry_run, once=args.once, budget_guard=budget_guard)


if __name__ == "__main__":
    main()
