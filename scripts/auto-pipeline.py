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
import collections
import hashlib
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
from typing import Optional, TextIO
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
AgentIdentity = _po_mod.AgentIdentity
load_agent_identity = _po_mod.load_agent_identity
AGENT_ROLE_PIPELINE = _po_mod.AGENT_ROLE_PIPELINE
is_item_suspended = _po_mod.is_item_suspended
read_suspension_marker = _po_mod.read_suspension_marker
get_suspension_answer = _po_mod.get_suspension_answer
clear_suspension_marker = _po_mod.clear_suspension_marker
create_suspension_marker = _po_mod.create_suspension_marker
SUSPENDED_DIR = _po_mod.SUSPENDED_DIR
SUSPENSION_TIMEOUT_MINUTES = _po_mod.SUSPENSION_TIMEOUT_MINUTES

# ─── Configuration ────────────────────────────────────────────────────

ORCHESTRATOR_CONFIG_PATH = ".claude/orchestrator-config.yaml"
DEFAULT_DEV_SERVER_PORT = 3000
DEFAULT_BUILD_COMMAND = "pnpm run build"
DEFAULT_TEST_COMMAND = "pnpm test"
DEFAULT_DEV_SERVER_COMMAND = "pnpm dev"
DEFAULT_AGENTS_DIR = ".claude/agents/"

DEFECT_DIR = "docs/defect-backlog"
FEATURE_DIR = "docs/feature-backlog"
ANALYSIS_DIR = "docs/analysis-backlog"
COMPLETED_DEFECTS_DIR = "docs/completed-backlog/defects"
COMPLETED_FEATURES_DIR = "docs/completed-backlog/features"
COMPLETED_ANALYSES_DIR = "docs/completed-backlog/analyses"
REPORTS_DIR = "docs/reports"
COMPLETED_DIRS = {
    "defect": COMPLETED_DEFECTS_DIR,
    "feature": COMPLETED_FEATURES_DIR,
    "analysis": COMPLETED_ANALYSES_DIR,
}
PLANS_DIR = ".claude/plans"
DESIGN_DIR = "docs/plans"
IDEAS_DIR = "docs/ideas"
IDEAS_PROCESSED_DIR = "docs/ideas/processed"
VERIFICATION_EXHAUSTED_STATUS = "Archived (verification failed)"
STOP_SEMAPHORE_PATH = ".claude/plans/.stop"
PID_FILE_PATH = ".claude/plans/.pipeline.pid"
LOGS_DIR = "logs"
SUMMARY_LOG_FILENAME = "pipeline.log"

REQUIRED_DIRS = [
    PLANS_DIR,
    os.path.join(PLANS_DIR, "logs"),
    LOGS_DIR,
    DEFECT_DIR,
    FEATURE_DIR,
    ANALYSIS_DIR,
    COMPLETED_FEATURES_DIR,
    COMPLETED_DEFECTS_DIR,
    COMPLETED_ANALYSES_DIR,
    REPORTS_DIR,
    IDEAS_DIR,
    IDEAS_PROCESSED_DIR,
    ".claude/suspended",
]


def ensure_directories() -> None:
    """Create all directories the pipeline depends on.

    Called once at startup so that no downstream code needs to worry
    about missing directories. Logs a message for each directory that
    had to be created.
    """
    for d in REQUIRED_DIRS:
        if not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
            print(f"[INIT] Created missing directory: {d}")


def write_pid_file() -> None:
    """Write the current process PID to the PID file.

    Allows external tools to identify and stop this specific pipeline
    instance without accidentally killing pipelines running in other
    project directories.
    """
    try:
        with open(PID_FILE_PATH, "w") as f:
            f.write(str(os.getpid()))
    except IOError as e:
        log(f"Warning: could not write PID file: {e}")


def remove_pid_file() -> None:
    """Remove the PID file on shutdown."""
    try:
        os.remove(PID_FILE_PATH)
    except FileNotFoundError:
        pass
    except IOError as e:
        log(f"Warning: could not remove PID file: {e}")


SAFETY_SCAN_INTERVAL_SECONDS = 60
PLAN_CREATION_TIMEOUT_SECONDS = 600
CHILD_SHUTDOWN_TIMEOUT_SECONDS = 10
RATE_LIMIT_BUFFER_SECONDS = 30
RATE_LIMIT_DEFAULT_WAIT_SECONDS = 3600
CODE_CHANGE_POLL_INTERVAL_SECONDS = 10
DEFAULT_MAX_QUOTA_PERCENT = 100.0
DEFAULT_QUOTA_CEILING_USD = 0.0
DEFAULT_RESERVED_BUDGET_USD = 0.0
PROGRESS_REPORT_INTERVAL_SECONDS = int(os.environ.get("PIPELINE_REPORT_INTERVAL", "900"))
COMPLETION_HISTORY_WINDOW_SECONDS = 7200
PROGRESS_REPORT_MAX_PREVIEW_ITEMS = 5

# Source files to monitor for hot-reload
HOT_RELOAD_WATCHED_FILES = [
    "scripts/auto-pipeline.py",
    "scripts/plan-orchestrator.py",
]


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

# Sandboxing: when True, Claude tasks receive per-profile --allowedTools flags.
# Set ORCHESTRATOR_SANDBOX_ENABLED=false to fall back to --dangerously-skip-permissions.
SANDBOX_ENABLED = os.environ.get("ORCHESTRATOR_SANDBOX_ENABLED", "true").lower() != "false"

# Per-task permission profiles for the pipeline (planner and verifier tasks only).
PIPELINE_PERMISSION_PROFILES: dict = {
    "planner": {
        "tools": ["Read", "Grep", "Glob", "Write", "Bash"],
        "description": "Plan creation and idea intake",
    },
    "verifier": {
        "tools": ["Read", "Grep", "Glob", "Bash"],
        "description": "Symptom verification (read + test commands)",
    },
}

ANALYSIS_TYPE_TO_AGENT: dict = {
    "code-review": "code-reviewer",
    "codebase-analysis": "code-explorer",
    "test-coverage": "qa-auditor",
    "test-results": "e2e-analyzer",
    "spec-compliance": "spec-verifier",
}
DEFAULT_ANALYSIS_AGENT = "code-reviewer"

# Global state
VERBOSE = False
CLAUDE_CMD: list[str] = ["claude"]
_saved_terminal_settings = None  # Saved termios settings for restoration
_startup_file_hashes: dict[str, str] = {}  # Populated at startup by snapshot_source_hashes()
_item_log_file: Optional[TextIO] = None  # Detail log for current item

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


def _open_item_log(slug: str, item_name: str, item_type: str) -> None:
    """Open a per-item detail log file in logs/<slug>.log (append mode).

    Writes a session-start header so multiple pipeline runs are clearly
    separated in the log file. The logs/ directory must already exist
    (created by ensure_directories() at startup).

    Args:
        slug: Backlog item slug used as the log filename (e.g. '1-feature-slug').
        item_name: Human-readable item name for the session header.
        item_type: Item type string ('defect' or 'feature').
    """
    global _item_log_file
    log_path = os.path.join(LOGS_DIR, f"{slug}.log")
    _item_log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = (
        "=" * 80 + "\n"
        f"SESSION START  {ts}  PID={_PIPELINE_PID}\n"
        f"Item: {slug}\n"
        f"Name: {item_name}\n"
        f"Type: {item_type}\n"
        + "=" * 80 + "\n"
    )
    _item_log_file.write(header)
    _item_log_file.flush()


def _close_item_log(result: str) -> None:
    """Write a session-end footer and close the current item detail log.

    Safe to call even if no log is open (no-op in that case).

    Args:
        result: Short result string written into the footer (e.g. 'success',
                'failed', 'verification-exhausted').
    """
    global _item_log_file
    if _item_log_file is None:
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    footer = (
        "=" * 80 + "\n"
        f"SESSION END  {ts}  result={result}\n"
        + "=" * 80 + "\n"
    )
    _item_log_file.write(footer)
    _item_log_file.flush()
    _item_log_file.close()
    _item_log_file = None


def _log_summary(level: str, event: str, slug: str, detail: str = "") -> None:
    """Append a single structured line to logs/pipeline.log.

    Each line has the format:
      YYYY-MM-DD HH:MM:SS [LEVEL]  EVENT  slug  detail

    The logs/ directory must already exist (created by ensure_directories()
    at startup).

    Args:
        level: One of 'INFO', 'WARN', 'ERROR'.
        event: Event keyword (e.g. 'STARTED', 'COMPLETED', 'FAILED').
        slug: Backlog item slug.
        detail: Optional extra detail appended after the slug.
    """
    summary_path = os.path.join(LOGS_DIR, SUMMARY_LOG_FILENAME)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [ts, f"[{level}]", event, slug]
    if detail:
        parts.append(detail)
    line = "  ".join(parts) + "\n"
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write(line)


def log(message: str) -> None:
    """Print a timestamped log message with PID for process tracking.

    Also writes to the currently-open item detail log file (if any).
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] [AUTO-PIPELINE:{_PIPELINE_PID}] {message}"
    print(line, flush=True)
    if _item_log_file is not None:
        _item_log_file.write(line + "\n")
        _item_log_file.flush()


def verbose_log(message: str) -> None:
    """Print a verbose log message if verbose mode is enabled.

    Also writes to the currently-open item detail log file (if any).
    """
    if VERBOSE:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] [VERBOSE:{_PIPELINE_PID}] {message}"
        print(line, flush=True)
        if _item_log_file is not None:
            _item_log_file.write(line + "\n")
            _item_log_file.flush()


def compact_plan_label(plan_path: str) -> str:
    """Produce a compact label from a plan filename for log prefixes.

    Strips the .yaml extension and truncates to MAX_LOG_PREFIX_LENGTH chars
    with ellipsis if the basename exceeds the limit.

    Examples:
        "long-filename-here.yaml" -> "long-filename-here..."
        "short.yaml" -> "short"
    """
    stem = Path(plan_path).stem
    if len(stem) <= MAX_LOG_PREFIX_LENGTH:
        return stem
    return stem[:MAX_LOG_PREFIX_LENGTH - 3] + "..."


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


def build_permission_flags(profile_name: str) -> list[str]:
    """Build CLI permission flags for a pipeline task profile.

    Returns a list of CLI arguments. Falls back to
    --dangerously-skip-permissions when SANDBOX_ENABLED is False.
    """
    if not SANDBOX_ENABLED:
        return ["--dangerously-skip-permissions"]

    profile = PIPELINE_PERMISSION_PROFILES.get(profile_name)
    if not profile:
        log(f"Unknown permission profile '{profile_name}', using --dangerously-skip-permissions")
        return ["--dangerously-skip-permissions"]

    tools = profile["tools"]
    flags = ["--allowedTools"] + tools
    flags.extend(["--add-dir", os.getcwd()])
    # Required for headless operation: suppresses interactive approval prompts
    flags.extend(["--permission-mode", "acceptEdits"])

    log(f"Permission profile '{profile_name}': tools={tools}")
    return flags


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


# ─── Stop Semaphore & Emergency Exit ─────────────────────────────────

# Module-level reference to the active SlackNotifier (set by entry points).
# Allows force_pipeline_exit() to send a notification without threading
# a slack parameter through every call site.
_active_slack: Optional["SlackNotifier"] = None


def check_stop_requested() -> bool:
    """Check if a graceful stop has been requested via semaphore file."""
    return os.path.exists(STOP_SEMAPHORE_PATH)


def clear_stop_semaphore() -> None:
    """Remove the stop semaphore file if it exists."""
    if os.path.exists(STOP_SEMAPHORE_PATH):
        os.remove(STOP_SEMAPHORE_PATH)
        log(f"Cleared stale stop semaphore: {STOP_SEMAPHORE_PATH}")


def force_pipeline_exit(reason: str, exit_code: int = 1) -> None:
    """Create the stop semaphore, notify Slack, log, and exit.

    This is the single exit point for unrecoverable errors such as
    infinite-loop detection or archive failures that would otherwise
    spin the pipeline forever.
    """
    log(f"FORCED EXIT: {reason}")

    # Create stop file so a concurrent or restarted pipeline also stops
    try:
        Path(STOP_SEMAPHORE_PATH).parent.mkdir(parents=True, exist_ok=True)
        Path(STOP_SEMAPHORE_PATH).touch()
    except OSError as e:
        log(f"WARNING: Could not create stop semaphore: {e}")

    # Notify Slack if available
    if _active_slack is not None:
        try:
            _active_slack.send_status(
                f"*Pipeline forced exit:* {reason}", level="error"
            )
        except Exception as e:
            log(f"WARNING: Slack notification failed during forced exit: {e}")

    sys.exit(exit_code)


# ─── Hot-Reload Detection ────────────────────────────────────────────


def _compute_file_hash(filepath: str) -> str:
    """Compute SHA-256 hash of a file. Returns empty string if file not found."""
    try:
        with open(filepath, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except (IOError, OSError):
        return ""


def snapshot_source_hashes() -> dict[str, str]:
    """Capture SHA-256 hashes of all watched source files.

    Called at startup to establish a baseline. Later calls to
    check_code_changed() compare current hashes against this snapshot.
    """
    hashes: dict[str, str] = {}
    for filepath in HOT_RELOAD_WATCHED_FILES:
        h = _compute_file_hash(filepath)
        if h:
            hashes[filepath] = h
            verbose_log(f"Snapshot hash: {filepath} -> {h[:12]}...")
    return hashes


def check_code_changed() -> bool:
    """Check if any watched source file has changed since startup.

    Compares current file hashes against _startup_file_hashes.
    Returns True if any file has changed.
    """
    for filepath, original_hash in _startup_file_hashes.items():
        current_hash = _compute_file_hash(filepath)
        if current_hash and current_hash != original_hash:
            log(f"Code change detected in {filepath}")
            return True
    return False


class CodeChangeMonitor:
    """Background thread that periodically checks for source code changes.

    Uses the existing check_code_changed() function which compares current
    file hashes against _startup_file_hashes. When a change is detected,
    sets the restart_pending event so the main loop can initiate a restart.
    """

    def __init__(self, poll_interval: float = CODE_CHANGE_POLL_INTERVAL_SECONDS):
        self.poll_interval = poll_interval
        self.restart_pending = threading.Event()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the background monitoring thread."""
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="code-change-monitor"
        )
        self._thread.start()
        verbose_log(f"CodeChangeMonitor started (polling every {self.poll_interval}s)")

    def stop(self) -> None:
        """Signal the monitoring thread to stop."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _monitor_loop(self) -> None:
        """Periodically check for source code changes."""
        while not self._stop_event.is_set():
            try:
                if check_code_changed():
                    log("CodeChangeMonitor: source code change detected")
                    self.restart_pending.set()
                    return  # Stop monitoring once change detected
            except Exception as e:
                verbose_log(f"CodeChangeMonitor error: {e}")
            self._stop_event.wait(timeout=self.poll_interval)


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
            item = BacklogItem(
                path=str(md_file),
                name=md_file.stem.replace("-", " ").title(),
                slug=md_file.stem,
                item_type=item_type,
            )
            if not archive_item(item):
                log(f"WARNING: Failed to auto-archive completed item: {md_file.name}")
            continue

        slug = md_file.stem  # filename without .md
        if is_item_suspended(slug):
            verbose_log(f"Skipping suspended item: {slug}")
            continue
        items.append(BacklogItem(
            path=str(md_file),
            name=md_file.stem.replace("-", " ").title(),
            slug=slug,
            item_type=item_type,
        ))

    return items


def parse_analysis_metadata(filepath: str) -> dict:
    """Parse analysis-specific metadata from a backlog .md file.

    Extracts:
      - analysis_type: value from '## Analysis Type: <type>' header
      - output_format: value from '## Output Format: <format>' header (default: 'both')
      - scope: lines from the '## Scope' section (as a list)
      - instructions: text from the '## Instructions' section
    Returns a dict with these keys.
    """
    try:
        with open(filepath, "r") as f:
            content = f.read()
    except IOError:
        return {"analysis_type": "", "output_format": "both", "scope": [], "instructions": ""}

    metadata: dict = {
        "analysis_type": "",
        "output_format": "both",
        "scope": [],
        "instructions": "",
    }

    # Extract analysis type
    type_match = re.search(r"^##\s*Analysis Type:\s*(.+)$", content, re.MULTILINE)
    if type_match:
        metadata["analysis_type"] = type_match.group(1).strip().lower()

    # Extract output format
    format_match = re.search(r"^##\s*Output Format:\s*(.+)$", content, re.MULTILINE)
    if format_match:
        metadata["output_format"] = format_match.group(1).strip().lower()

    # Extract scope section
    scope_match = re.search(r"^##\s*Scope\s*\n(.*?)(?=^##|\Z)", content, re.MULTILINE | re.DOTALL)
    if scope_match:
        scope_lines = [line.strip().lstrip("- ") for line in scope_match.group(1).strip().splitlines() if line.strip()]
        metadata["scope"] = scope_lines

    # Extract instructions section
    instructions_match = re.search(r"^##\s*Instructions\s*\n(.*?)(?=^##|\Z)", content, re.MULTILINE | re.DOTALL)
    if instructions_match:
        metadata["instructions"] = instructions_match.group(1).strip()

    return metadata


def parse_step_notifications_override(filepath: str) -> Optional[bool]:
    """Parse step_notifications: true/false from a backlog .md file.

    Looks for a line matching 'step_notifications: true' or
    'step_notifications: false' (case-insensitive) anywhere in the document.
    Returns None if the field is absent.
    """
    try:
        with open(filepath, "r") as f:
            content = f.read()
    except (IOError, OSError):
        return None

    match = re.search(r"^\s*step_notifications:\s*(true|false)\s*$", content, re.MULTILINE | re.IGNORECASE)
    if match:
        return match.group(1).lower() == "true"
    return None


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
    """Scan all backlog directories with dependency filtering.

    Returns defects first, then features, then analysis items. Items whose
    dependencies are not all present in the completed/ directories are filtered out.
    """
    defects = scan_directory(DEFECT_DIR, "defect")
    features = scan_directory(FEATURE_DIR, "feature")
    analyses = scan_directory(ANALYSIS_DIR, "analysis")
    all_items = defects + features + analyses

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


def scan_ideas() -> list[str]:
    """Scan docs/ideas/ for unprocessed .md idea files.

    Returns file paths (strings) for files that:
    - Are non-empty .md files in IDEAS_DIR (non-recursive)
    - Have not already been processed (basename not in IDEAS_PROCESSED_DIR)

    Returns an empty list if IDEAS_DIR does not exist.
    """
    if not os.path.isdir(IDEAS_DIR):
        return []

    unprocessed: list[str] = []
    for entry in os.scandir(IDEAS_DIR):
        if not entry.is_file():
            continue
        if entry.name.startswith("."):
            continue
        if not entry.name.endswith(".md"):
            continue
        if os.path.getsize(entry.path) == 0:
            continue
        processed_path = os.path.join(IDEAS_PROCESSED_DIR, entry.name)
        if os.path.exists(processed_path):
            continue
        unprocessed.append(entry.path)

    return unprocessed


def process_idea(idea_path: str, dry_run: bool = False) -> bool:
    """Classify a raw idea file into formatted backlog items via a Claude session.

    Spawns Claude with IDEA_INTAKE_PROMPT_TEMPLATE to read the idea, write
    properly formatted backlog .md files to the correct directories, and move
    the original to IDEAS_PROCESSED_DIR.

    Returns True on success, False on failure (including rate limiting).
    """
    idea_filename = os.path.basename(idea_path)

    if dry_run:
        log(f"[dry-run] Would classify idea: {idea_filename}")
        return True

    prompt = IDEA_INTAKE_PROMPT_TEMPLATE.format(
        idea_path=idea_path,
        idea_filename=idea_filename,
        feature_dir=FEATURE_DIR,
        defect_dir=DEFECT_DIR,
        processed_dir=IDEAS_PROCESSED_DIR,
    )

    cmd = [*CLAUDE_CMD, *build_permission_flags("planner"), "--print", prompt]

    result = run_child_process(
        cmd,
        description=f"Intake: {idea_filename}",
        timeout=PLAN_CREATION_TIMEOUT_SECONDS,
        show_output=VERBOSE,
    )

    if result.rate_limited:
        log(f"Rate limited during idea intake for {idea_filename}")
        return False

    if not result.success:
        log(f"Idea intake failed for {idea_filename} (exit {result.exit_code})")
        if result.stderr:
            log(f"  stderr: {result.stderr[:500]}")
        return False

    processed_path = os.path.join(IDEAS_PROCESSED_DIR, idea_filename)
    if not os.path.exists(processed_path):
        log(f"Idea intake completed but original not moved to processed/: {idea_filename}")
        return False

    log(f"Idea classified and archived: {idea_filename}")
    return True


def intake_ideas(dry_run: bool = False) -> int:
    """Process all raw idea files from IDEAS_DIR into formatted backlog items.

    Scans IDEAS_DIR for unprocessed .md files, processes each one sequentially
    via process_idea(), and returns the count of successfully processed ideas.
    """
    idea_paths = scan_ideas()
    if not idea_paths:
        return 0

    log(f"Found {len(idea_paths)} idea(s) to process")
    success_count = 0
    for idea_path in idea_paths:
        idea_filename = os.path.basename(idea_path)
        success = process_idea(idea_path, dry_run)
        if success:
            log(f"Idea processed successfully: {idea_filename}")
            success_count += 1
        else:
            log(f"Idea processing failed: {idea_filename}")
    return success_count


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

# Max chars from plan filename used in log prefixes (prevents line wrapping)
MAX_LOG_PREFIX_LENGTH = 30


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
            log(f"[Usage] {work_item_name}: ~${cost:.4f} (API-equivalent)")
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            pass  # Report not available, skip silently

    def format_session_summary(self) -> str:
        """Format session-level usage summary."""
        lines = ["\n=== Pipeline Session Usage (API-Equivalent Estimates) ==="]
        lines.append("(These are API-equivalent costs reported by Claude CLI, not actual subscription charges)")
        lines.append(f"Total API-equivalent cost: ${self.total_cost_usd:.4f}")
        lines.append(
            f"Total tokens: {self.total_input_tokens:,} input / "
            f"{self.total_output_tokens:,} output"
        )
        if self.work_item_costs:
            lines.append("Per work item:")
            for item in self.work_item_costs:
                lines.append(f"  {item['name']}: ~${item['cost_usd']:.4f}")
        return "\n".join(lines)

    def write_session_report(self) -> Optional[str]:
        """Write a session summary JSON file."""
        if not self.work_item_costs:
            return None
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_path = Path(PLANS_DIR) / "logs" / f"pipeline-session-{timestamp}.json"
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


class CompletionTracker:
    """Records work item completions for velocity and ETA calculations.

    Design reference: docs/plans/2026-02-19-18-periodic-progress-reporter-design.md
    """

    def __init__(self) -> None:
        self._entries: collections.deque[tuple[float, str, str, float]] = collections.deque()
        self._lock = threading.Lock()

    def record_completion(self, item_type: str, slug: str, duration_seconds: float) -> None:
        """Record a completed work item with its wall-clock duration."""
        with self._lock:
            self._entries.append((time.time(), item_type, slug, duration_seconds))

    def prune_old_entries(self) -> None:
        """Remove entries older than COMPLETION_HISTORY_WINDOW_SECONDS."""
        cutoff = time.time() - COMPLETION_HISTORY_WINDOW_SECONDS
        with self._lock:
            while self._entries and self._entries[0][0] < cutoff:
                self._entries.popleft()

    def completions_since(self, since_timestamp: float) -> list[tuple[float, str, str, float]]:
        """Return all entries recorded after since_timestamp."""
        with self._lock:
            return [e for e in self._entries if e[0] >= since_timestamp]

    def average_duration_seconds(self) -> float:
        """Return the mean duration of all entries in the current window, or 0.0."""
        with self._lock:
            if not self._entries:
                return 0.0
            return sum(e[3] for e in self._entries) / len(self._entries)


class ProgressReporter:
    """Background thread that periodically sends pipeline progress reports to Slack.

    Wakes every interval seconds and sends a snapshot of queue depth, completions
    since the last report, velocity, ETA, and the next queued items. Stays silent
    when the pipeline is idle (no item in progress and empty queue).

    Design reference: docs/plans/2026-02-19-18-periodic-progress-reporter-design.md
    """

    def __init__(
        self,
        slack: SlackNotifier,
        completion_tracker: CompletionTracker,
        item_in_progress: threading.Event,
        interval: float = PROGRESS_REPORT_INTERVAL_SECONDS,
    ) -> None:
        self._slack = slack
        self._completion_tracker = completion_tracker
        self._item_in_progress = item_in_progress
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_report_time: float = time.time()

    def start(self) -> None:
        """Start the background reporting thread."""
        self._thread = threading.Thread(
            target=self._reporter_loop, daemon=True, name="progress-reporter"
        )
        self._thread.start()
        verbose_log(f"ProgressReporter started (interval: {self._interval}s)")

    def stop(self) -> None:
        """Signal the reporting thread to stop."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _reporter_loop(self) -> None:
        """Wake every interval, check silence conditions, and send a report."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._interval)
            if self._stop_event.is_set():
                break
            try:
                if self._should_report():
                    self._send_report()
            except Exception as e:
                verbose_log(f"ProgressReporter error: {e}")

    def _should_report(self) -> bool:
        """Return False only when no task is running and the queue is empty."""
        if self._item_in_progress.is_set():
            return True
        return len(scan_all_backlogs()) > 0

    def _build_report(self, queue: list[BacklogItem]) -> str:
        """Build the formatted progress report string."""
        self._completion_tracker.prune_old_entries()

        defect_count = sum(1 for i in queue if i.item_type == "defect")
        feature_count = sum(1 for i in queue if i.item_type == "feature")
        analysis_count = sum(1 for i in queue if i.item_type == "analysis")
        queue_size = len(queue)

        since_entries = self._completion_tracker.completions_since(self._last_report_time)
        completions_count = len(since_entries)
        completed_defects = sum(1 for e in since_entries if e[1] == "defect")
        completed_features = sum(1 for e in since_entries if e[1] == "feature")
        completed_analyses = sum(1 for e in since_entries if e[1] == "analysis")

        avg_duration = self._completion_tracker.average_duration_seconds()
        if avg_duration > 0:
            avg_fmt = self._format_duration(avg_duration)
            eta_fmt = self._format_duration(queue_size * avg_duration)
        else:
            avg_fmt = "n/a"
            eta_fmt = "n/a"

        preview = queue[:PROGRESS_REPORT_MAX_PREVIEW_ITEMS]
        lines = [
            "*Pipeline Progress Report*",
            "",
            (
                f"*Queue:* {queue_size} items"
                f" — defects: {defect_count}"
                f", features: {feature_count}"
                f", analyses: {analysis_count}"
            ),
            (
                f"*Completions since last report:* {completions_count}"
                f" — defects: {completed_defects}"
                f", features: {completed_features}"
                f", analyses: {completed_analyses}"
            ),
            f"*Avg completion time:* {avg_fmt}",
            f"*ETA (remaining queue):* {eta_fmt}",
        ]
        if preview:
            lines.append("*Next up:*")
            for item in preview:
                lines.append(f"  \u2022 [{item.item_type}] {item.name}")
        return "\n".join(lines)

    def _send_report(self) -> None:
        """Build and send the progress report to Slack."""
        queue = scan_all_backlogs()
        report = self._build_report(queue)
        self._slack.send_status(report)
        self._last_report_time = time.time()

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format a duration in seconds as a human-readable string."""
        if seconds < 60:
            return f"{int(seconds)}s"
        if seconds < 3600:
            minutes = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"


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


# ─── Idea Intake ──────────────────────────────────────────────────────

IDEA_INTAKE_PROMPT_TEMPLATE = """You are an intake classifier for a software project backlog.

## Your Task

Read the raw idea file at: {idea_path}

Analyze the content and classify it into one or more actionable backlog items.

## Classification Rules

1. Determine if each item describes a **feature** (new capability or enhancement) or a
   **defect** (something broken or not working as intended). A single idea file may produce
   multiple items of different types.

2. Assess priority based on content signals:
   - **High**: Critical path, blocking users, data loss risk, or explicitly urgent
   - **Medium**: Important but not blocking, clear user value
   - **Low**: Nice-to-have, minor improvement, or vague benefit

3. If the idea is too vague to act on, write a single item with `## Status: Needs Clarification`
   instead of Open.

## Output Format

For each backlog item, create a markdown file with exactly these sections:

```
## Status: Open
## Priority: <High|Medium|Low>
## Summary
<Clear one-paragraph description of the item — what it is and why it matters>

## Scope
<What areas of the codebase or system are affected>

## Files Affected
<Bulleted list of files likely needing changes, or "Unknown - needs investigation">
```

## Output Locations

- Feature items go to: {feature_dir}/<slug>.md
- Defect items go to: {defect_dir}/<slug>.md

The slug must be derived from the idea content: lowercase, words separated by hyphens,
descriptive of the item (e.g., `add-dark-mode-toggle.md`, `fix-login-redirect-loop.md`).

## After Writing Output Files

1. Move the original idea file to: {processed_dir}/{idea_filename}
   (use `git mv` or `mv` then `git add`)
2. Git commit with message: `intake: classify idea {idea_filename}`

Commit all new backlog files and the move of the original in a single commit.
"""

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
   - The task description should reference the work item file path -- agents read it directly
   - Do NOT rewrite or summarize the work item requirements into the task description
   - Do NOT add separate verification, review, or code-review tasks
   - The orchestrator runs a validator automatically after each task

3. Validate the plan: python scripts/plan-orchestrator.py --plan .claude/plans/{slug}.yaml --dry-run
   - If validation fails, fix the YAML format and retry

4. Git commit both files with message: "plan: add {slug} design and YAML plan"

## Backlog item type: {item_type}

## Agent Selection

Tasks can specify which agent should execute them via the optional "agent" field.
Available agents are in {agents_dir}:

- **coder**: Implementation specialist. Use for coding, implementation, and
  modification tasks. This is the default if no agent is specified.
- **frontend-coder**: Frontend implementation specialist for UI components,
  pages, and forms. Use for tasks mentioning frontend, component, UI
  implementation, form, dialog, or modal.
- **e2e-test-agent**: E2E test specialist for Playwright tests. Use for ALL tasks
  that create or fix E2E test files (.spec.ts).
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
-> systems-designer, plan extension -> planner, frontend/component/UI ->
frontend-coder, everything else -> coder).

## Validation

Plans MUST enable per-task validation and include the source work item path.
The validator reads the work item file for validation expectations.

  meta:
    source_item: "{item_path}"
    validation:
      enabled: true
      run_after:
        - coder
        - e2e-test-agent
        - frontend-coder
      validators:
        - validator
      max_validation_attempts: 2

Task descriptions reference the work item -- do NOT rewrite requirements:

  - id: '1.1'
    name: Implement work item
    agent: coder
    description: "Implement the work item: {item_path}"

Do NOT add code-reviewer or verification tasks -- validation handles that.

## Important
- Always set meta.source_item to the backlog file path
- For E2E tests: use agent: e2e-test-agent
- For code tasks: use agent: coder
- Task descriptions reference the work item file, not rewrite it
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


def is_plan_fully_completed(plan_path: str) -> bool:
    """Check if all tasks in a YAML plan are completed (no pending tasks remain).

    Returns True only if the plan has at least one completed task and zero
    pending/in_progress tasks. Returns False for invalid, missing, or failed plans.
    A plan with meta.status: "failed" is not considered fully completed -- it is
    deadlocked and must not proceed to archiving.
    """
    try:
        with open(plan_path, "r") as f:
            plan = yaml.safe_load(f)
        if not plan or "sections" not in plan:
            return False
        meta = plan.get("meta", {})
        if isinstance(meta, dict) and meta.get("status") == "failed":
            return False
        done = 0
        for section in plan.get("sections", []):
            for task in section.get("tasks", []):
                status = task.get("status", "pending")
                if status == "completed":
                    done += 1
                elif status in ("pending", "in_progress"):
                    return False
        return done > 0
    except (IOError, yaml.YAMLError):
        return False


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

    cmd = [*CLAUDE_CMD, *build_permission_flags("planner"), "--print", prompt]

    result = run_child_process(
        cmd,
        description=f"Plan: {compact_plan_label(item.slug)}",
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

    # Inject step_notifications override from backlog item into plan meta
    step_notifications_override = parse_step_notifications_override(item.path)
    if step_notifications_override is not None:
        try:
            with open(plan_path, "r") as f:
                plan = yaml.safe_load(f)
            plan.setdefault("meta", {})["step_notifications"] = step_notifications_override
            with open(plan_path, "w") as f:
                yaml.dump(plan, f, default_flow_style=False, sort_keys=False)
            log(f"Injected step_notifications={step_notifications_override} into plan meta")
        except (IOError, OSError) as e:
            log(f"WARNING: Could not inject step_notifications override: {e}")

    # Dry-run validation
    validate_result = run_child_process(
        ["python", "scripts/plan-orchestrator.py", "--plan", plan_path, "--dry-run"],
        description=f"Validate: {compact_plan_label(item.slug)}",
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
    label = compact_plan_label(plan_path)
    if dry_run:
        log(f"[DRY RUN] Would execute plan: {plan_path}")
        return True

    log(f"Executing plan: {plan_path}")

    # Stop dev server before orchestrator runs (builds conflict with turbopack cache)
    stop_dev_server()

    try:
        orch_cmd = ["python", "scripts/plan-orchestrator.py", "--plan", plan_path]
        if VERBOSE:
            orch_cmd.append("--verbose")

        result = run_child_process(
            orch_cmd,
            description=f"Orch: {label}",
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

        meta = plan.get("meta", {})
        if isinstance(meta, dict) and meta.get("status") == "failed":
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


def _resolve_item_path(item: "BacklogItem") -> Optional[str]:
    """Locate the actual file path for a backlog item at archive time.

    Returns item.path if the file exists there. Falls back to checking
    <backlog_dir>/completed/<filename> in case an external process relocated
    the file mid-pipeline. Returns None if the file cannot be found at either
    location.
    """
    if os.path.exists(item.path):
        return item.path
    candidate = os.path.join(
        os.path.dirname(item.path), "completed", os.path.basename(item.path)
    )
    if os.path.exists(candidate):
        log(f"WARNING: [ARCHIVE] Item relocated to completed/ subfolder — unexpected mid-pipeline move: {candidate}")
        return candidate
    return None


def archive_item(item: BacklogItem, dry_run: bool = False) -> bool:
    """Move a completed backlog item to the top-level archive directory."""
    dest_dir = COMPLETED_DIRS[item.item_type]
    dest = os.path.join(dest_dir, os.path.basename(item.path))

    if dry_run:
        log(f"[DRY RUN] Would archive: {item.path} -> {dest}")
        return True

    if os.path.exists(dest):
        # Destination exists but source may still be in backlog (e.g. prior archive
        # copied but failed to remove source, or manual copy).  Remove the source
        # to prevent the scanner from re-discovering the item in an infinite loop.
        source = _resolve_item_path(item)
        if source is not None and os.path.exists(source):
            try:
                os.remove(source)
                subprocess.run(["git", "add", source], capture_output=True, check=True)
                subprocess.run(
                    ["git", "commit", "-m", f"chore: remove stale backlog source for {item.slug}"],
                    capture_output=True, check=True,
                )
                log(f"[ARCHIVE] Already archived, removed stale source: {source}")
            except (OSError, subprocess.CalledProcessError) as e:
                force_pipeline_exit(
                    f"Cannot remove stale backlog source {source} "
                    f"(already archived at {dest}): {e}"
                )
        else:
            log(f"[ARCHIVE] Already archived, skipping: {dest}")
        return True

    source = _resolve_item_path(item)
    if source is None:
        log(f"WARNING: Cannot archive {item.path}: file not found at original path or completed/ subfolder")
        return False

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

ANALYSIS_PROMPT_TEMPLATE = """You are an analysis agent. Your job is to perform a read-only analysis
of the codebase and produce a structured report. You MUST NOT modify any files.

## Analysis Request
- Item: {item_path}
- Type: {analysis_type}
- Scope: {scope}

## Instructions
{instructions}

## What to produce

Write a structured markdown report to: {report_path}

The report must include:
1. An executive summary (3-5 bullet points)
2. Detailed findings organized by category
3. Recommendations (if applicable)
4. A severity/priority classification for each finding

## CRITICAL RULES
- Do NOT modify any project source files
- Do NOT create or modify any code
- ONLY read files and write the report to the specified path
- Be thorough but concise in your analysis
"""

# Maximum number of verify-then-fix cycles before giving up
MAX_VERIFICATION_CYCLES = 3

# Maximum characters for the completion summary appended to Slack notifications
MAX_SUMMARY_LENGTH = 300


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

    cmd = [*CLAUDE_CMD, *build_permission_flags("verifier"), "--print", prompt]

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


def _perform_restart(
    reason: str,
    slack: "SlackNotifier",
    session_tracker: SessionUsageTracker,
    observer: Optional["Observer"] = None,
    code_monitor: Optional["CodeChangeMonitor"] = None,
) -> None:
    """Perform a graceful pipeline restart via os.execv().

    Handles cleanup: Slack notification, session summary, stopping
    background threads, and restoring terminal settings.

    Args:
        reason: Human-readable reason for the restart (for logs/Slack).
        slack: SlackNotifier instance for sending notifications.
        session_tracker: Session usage tracker for summary output.
        observer: Watchdog observer to stop (None in --once mode).
        code_monitor: CodeChangeMonitor to stop before restart.
    """
    log(f"Restarting pipeline: {reason}")
    slack.send_status(
        f"*Pipeline: restarting* {reason}",
        level="info"
    )
    if session_tracker.work_item_costs:
        print(session_tracker.format_session_summary())
        session_tracker.write_session_report()
    if code_monitor:
        code_monitor.stop()
    slack.stop_background_polling()
    if observer:
        observer.stop()
        observer.join(timeout=5)
    restore_terminal_settings()
    os.execv(sys.executable, [sys.executable] + sys.argv)


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


def _extract_completion_summary(item_path: str) -> str:
    """Extract a concise root cause and fix summary from a completed item file.

    Reads the markdown file and extracts up to 2 sentences covering what was
    wrong and what was changed. Returns empty string if the file cannot be read
    or has no extractable sections.

    Priority for "what was wrong":
    1. First sentence of ## Root Cause section
    2. **Root Need:** line from 5 Whys analysis
    3. First sentence of ## Summary section

    Priority for "what was fixed":
    1. Lines from last ## Verification Log entry's **Findings:** that mention "fix" or "commit"
    2. **Verdict:** line from last verification entry
    """
    try:
        with open(item_path, "r", encoding="utf-8") as f:
            content = f.read()
    except IOError:
        return ""

    cause = ""

    root_cause_match = re.search(
        r"##\s+Root Cause\s*\n+(.*?)(?:\n\n|\n##|\Z)",
        content, re.MULTILINE | re.DOTALL
    )
    if root_cause_match:
        first_sentence = root_cause_match.group(1).strip().split(".")[0]
        cause = first_sentence.strip() + "." if first_sentence else ""

    if not cause:
        root_need_match = re.search(r"\*\*Root Need:\*\*\s*(.+)", content)
        if root_need_match:
            cause = root_need_match.group(1).strip()

    if not cause:
        summary_match = re.search(
            r"##\s+Summary\s*\n+(.*?)(?:\n\n|\n##|\Z)",
            content, re.MULTILINE | re.DOTALL
        )
        if summary_match:
            first_sentence = summary_match.group(1).strip().split(".")[0]
            cause = first_sentence.strip() + "." if first_sentence else ""

    fix = ""

    all_verifications = list(re.finditer(
        r"###\s+Verification\s+#\d+.*?(?=###\s+Verification\s+#|\Z)",
        content, re.MULTILINE | re.DOTALL
    ))
    if all_verifications:
        last_entry = all_verifications[-1].group(0)
        findings_match = re.search(r"\*\*Findings:\*\*\s*(.*?)(?=\*\*|\Z)", last_entry, re.DOTALL)
        if findings_match:
            findings_text = findings_match.group(1).strip()
            for line in findings_text.splitlines():
                if re.search(r"\bfix\b|\bcommit\b", line, re.IGNORECASE):
                    fix = line.strip().lstrip("- ").strip()
                    break
        if not fix:
            verdict_match = re.search(r"\*\*Verdict:\s*(PASS|FAIL)\*\*", last_entry, re.IGNORECASE)
            if verdict_match:
                fix = f"Verdict: {verdict_match.group(1).upper()}"

    parts = [p for p in [cause, fix] if p]
    summary = " ".join(parts)
    return summary[:MAX_SUMMARY_LENGTH] if summary else ""


def _archive_and_report(
    item: BacklogItem, slack: "SlackNotifier",
    item_start: float, dry_run: bool,
) -> bool:
    """Archive a completed item and send Slack status. Returns True on success."""
    log("Phase 4: Archiving...")
    summary = _extract_completion_summary(item.path)
    archived = archive_item(item, dry_run)

    elapsed = time.time() - item_start
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    if not archived:
        log(f"WARNING: Archive failed for {item.display_name} - "
            "item will not be retried this session")
        slack.send_status(
            f"*Pipeline: archive failed* {item.display_name}\n"
            "Item completed but could not be moved to completed-backlog.",
            level="warning"
        )
        _log_summary("WARN", "ARCHIVE_FAILED", item.slug,
                     f"duration={minutes}m{seconds}s")
        return False

    log(f"Item complete: {item.display_name} ({minutes}m {seconds}s)")
    summary_block = f"\n{summary}" if summary else ""
    slack.send_status(
        f"*Pipeline: completed* {item.display_name}\n"
        f"Duration: {minutes}m {seconds}s{summary_block}",
        level="success"
    )
    # Cross-post to type-specific channel (orchestrator-features or orchestrator-defects)
    type_channel_id = slack.get_type_channel_id(item.item_type)
    if type_channel_id:
        slack.send_status(
            f"*Completed:* {item.display_name}\n"
            f"Duration: {minutes}m {seconds}s{summary_block}",
            level="success",
            channel_id=type_channel_id,
        )
    _log_summary("INFO", "COMPLETED", item.slug,
                 f"duration={minutes}m{seconds}s")
    return True


def _mark_as_verification_exhausted(item_path: str) -> None:
    """Update Status line in defect markdown to indicate verification was exhausted."""
    try:
        with open(item_path, "r", encoding="utf-8") as f:
            content = f.read()

        updated_content = content.replace(
            "## Status: Open",
            f"## Status: {VERIFICATION_EXHAUSTED_STATUS}"
        )

        with open(item_path, "w", encoding="utf-8") as f:
            f.write(updated_content)

        log(f"Updated status to '{VERIFICATION_EXHAUSTED_STATUS}': {item_path}")
    except IOError as e:
        log(f"WARNING: Could not update status in {item_path}: {e}")


def process_analysis_item(
    item: BacklogItem,
    dry_run: bool = False,
    item_in_progress: Optional[threading.Event] = None,
    completion_tracker: Optional[CompletionTracker] = None,
) -> bool:
    """Process an analysis backlog item through the lightweight analysis workflow.

    Unlike feature/defect items, analysis items:
    - Use a single Claude session with a read-only agent
    - Produce a report instead of code changes
    - Skip the plan creation and verification loop
    - Deliver results via Slack and/or markdown file

    Returns True on success, False on failure.
    """
    if item_in_progress is not None:
        item_in_progress.set()
    slack = SlackNotifier()
    slack.set_identity(load_agent_identity(_config), AGENT_ROLE_PIPELINE)
    item_start = time.time()
    _open_item_log(item.slug, item.display_name, item.item_type)
    _log_summary("INFO", "STARTED", item.slug, f"type={item.item_type}")

    try:
        success = _process_analysis_inner(item, slack, item_start, dry_run)
        if success and completion_tracker is not None:
            elapsed = time.time() - item_start
            completion_tracker.record_completion(item.item_type, item.slug, elapsed)
        return success
    except Exception as e:
        log(f"UNEXPECTED ERROR in process_analysis_item: {e}")
        _log_summary("ERROR", "CRASHED", item.slug, str(e))
        return False
    finally:
        _close_item_log("done")
        if item_in_progress is not None:
            item_in_progress.clear()


def _process_analysis_inner(
    item: BacklogItem,
    slack: SlackNotifier,
    item_start: float,
    dry_run: bool,
) -> bool:
    """Inner implementation of process_analysis_item()."""
    log(f"{'=' * 60}")
    log(f"Analyzing: {item.display_name}")
    log(f"  Type: {item.item_type}")
    log(f"  File: {item.path}")
    log(f"{'=' * 60}")

    # Parse analysis metadata
    metadata = parse_analysis_metadata(item.path)
    analysis_type = metadata["analysis_type"] or "code-review"
    output_format = metadata["output_format"] or "both"
    scope = ", ".join(metadata["scope"]) if metadata["scope"] else "entire project"
    instructions = metadata["instructions"] or "Perform a thorough analysis."

    # Resolve agent
    agent_name = ANALYSIS_TYPE_TO_AGENT.get(analysis_type, DEFAULT_ANALYSIS_AGENT)
    log(f"  Analysis type: {analysis_type} -> agent: {agent_name}")
    log(f"  Output format: {output_format}")
    log(f"  Scope: {scope}")

    slack.send_status(
        f"*Pipeline: analyzing* {item.display_name}\n"
        f"Agent: {agent_name} | Scope: {scope}",
        level="info"
    )

    report_path = os.path.join(REPORTS_DIR, f"{item.slug}.md")

    if dry_run:
        log(f"[DRY RUN] Would run analysis: {item.display_name}")
        log(f"  Agent: {agent_name}")
        log(f"  Report: {report_path}")
        return True

    # Build the analysis prompt
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        item_path=item.path,
        analysis_type=analysis_type,
        scope=scope,
        instructions=instructions,
        report_path=report_path,
    )

    # All analysis agents use the READ_ONLY permission profile.
    # The verifier profile (Read, Grep, Glob, Bash) matches this requirement.
    cmd = [*CLAUDE_CMD, *build_permission_flags("verifier"), "--print", prompt]

    result = run_child_process(
        cmd,
        description=f"Analysis: {compact_plan_label(item.slug)}",
        timeout=PLAN_CREATION_TIMEOUT_SECONDS,
        show_output=VERBOSE,
    )

    if result.rate_limited:
        log("Rate limited during analysis")
        _log_summary("WARN", "RATE_LIMITED", item.slug, "analysis")
        return False

    if not result.success:
        log(f"Analysis failed for {item.display_name} (exit {result.exit_code})")
        if result.stderr:
            log(f"  stderr: {result.stderr[:500]}")
        slack.send_status(
            f"*Pipeline: analysis failed* {item.display_name}",
            level="error"
        )
        _log_summary("ERROR", "FAILED", item.slug, "phase=analysis")
        return False

    # Deliver report
    _deliver_analysis_report(item, slack, report_path, output_format)

    # Archive
    elapsed = time.time() - item_start
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    log(f"Analysis complete: {item.display_name} ({minutes}m {seconds}s)")
    archived = archive_item(item, dry_run=False)
    if archived:
        _log_summary("INFO", "COMPLETED", item.slug, f"duration={minutes}m{seconds}s")
    else:
        _log_summary("WARN", "ARCHIVE_FAILED", item.slug, f"duration={minutes}m{seconds}s")
    return True


def _deliver_analysis_report(
    item: BacklogItem,
    slack: SlackNotifier,
    report_path: str,
    output_format: str,
) -> None:
    """Deliver the analysis report via Slack and/or verify the markdown file."""
    report_exists = os.path.exists(report_path)

    if output_format in ("slack", "both"):
        # Read the report and post a summary to Slack
        summary = ""
        if report_exists:
            try:
                with open(report_path, "r") as f:
                    content = f.read()
                # Extract executive summary (first section after the title)
                lines = content.split("\n")
                summary_lines: list[str] = []
                in_summary = False
                for line in lines:
                    if "executive summary" in line.lower() or (
                        "summary" in line.lower() and line.startswith("#")
                    ):
                        in_summary = True
                        continue
                    if in_summary and line.startswith("#"):
                        break
                    if in_summary and line.strip():
                        summary_lines.append(line)
                summary = "\n".join(summary_lines[:10])
            except IOError:
                pass
        if not summary:
            summary = f"Analysis completed for {item.display_name}"

        # Post to orchestrator-reports channel
        reports_channel = slack.get_type_channel_id("analysis")
        if reports_channel:
            slack.send_status(
                f"*Analysis Report:* {item.display_name}\n{summary}",
                level="success",
                channel_id=reports_channel,
            )
        else:
            # Fall back to notifications channel
            slack.send_status(
                f"*Analysis Report:* {item.display_name}\n{summary}",
                level="success",
            )

    if output_format in ("markdown", "both"):
        if report_exists:
            log(f"Report saved: {report_path}")
        else:
            log(f"WARNING: Expected report not found at {report_path}")


def _process_item_inner(
    item: BacklogItem,
    dry_run: bool,
    session_tracker: Optional[SessionUsageTracker],
) -> bool:
    """Inner implementation of process_item() - called within a try/finally wrapper.

    All return paths here have already had _log_summary() called where appropriate.
    The outer wrapper guarantees _close_item_log() runs regardless of outcome.
    """
    slack = SlackNotifier()
    slack.set_identity(load_agent_identity(_config), AGENT_ROLE_PIPELINE)
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

    # Fast path: if verification already passed, skip straight to archive
    if last_verification_passed(item.path):
        log("Prior verification PASSED - skipping to archive")
        return _archive_and_report(item, slack, item_start, dry_run)

    # Subtract prior verification attempts from the cycle budget
    prior_verifications = count_verification_attempts(item.path)
    remaining_cycles = max(0, MAX_VERIFICATION_CYCLES - prior_verifications)

    if remaining_cycles == 0:
        log(f"Max verification cycles ({MAX_VERIFICATION_CYCLES}) already reached "
            f"({prior_verifications} prior attempts). Archiving {item.slug}.")
        # Clean up leftover plan YAML to prevent re-processing on restart
        plan_path = f"{PLANS_DIR}/{item.slug}.yaml"
        if os.path.exists(plan_path):
            os.remove(plan_path)
            log(f"Cleaned up stale plan: {plan_path}")
        _mark_as_verification_exhausted(item.path)
        slack.send_status(
            f"*Pipeline: verification exhausted* {item.display_name}\n"
            f"Archived after {MAX_VERIFICATION_CYCLES} failed verification cycles.",
            level="warning"
        )
        _log_summary("WARN", "VERIFICATION_EXHAUSTED", item.slug,
                     f"cycles={MAX_VERIFICATION_CYCLES}")
        _archive_and_report(item, slack, item_start, dry_run)
        return False

    plan_path = None

    for cycle in range(remaining_cycles):
        cycle_label = f"{prior_verifications + cycle + 1}/{MAX_VERIFICATION_CYCLES}"

        if check_stop_requested():
            log("Stop requested during processing.")
            _log_summary("WARN", "STOPPED", item.slug, "stop-requested")
            return False

        # Phase 1: Create plan
        log(f"Phase 1: Creating plan (cycle {cycle_label})...")
        plan_path = create_plan(item, dry_run)
        if not plan_path:
            log(f"FAILED: Could not create plan for {item.display_name}")
            slack.send_status(
                f"*Pipeline: failed* {item.display_name}",
                level="error"
            )
            _log_summary("ERROR", "FAILED", item.slug, "phase=plan-creation")
            return False

        # Phase 2: Execute plan (skip if all tasks already completed)
        if is_plan_fully_completed(plan_path):
            log("Phase 2: Plan already fully completed - skipping orchestrator")
        else:
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
                _log_summary("ERROR", "FAILED", item.slug, "phase=orchestrator")
                return False

            # Check if any task was suspended by an agent (e.g. ux-designer)
            suspended_tasks = _get_plan_suspended_tasks(plan_path)
            if suspended_tasks:
                return _handle_suspension(item, plan_path, slack)

        # Phase 3: Verify symptoms
        log("Phase 3: Verifying symptoms...")
        verified = verify_item(item, dry_run)

        if verified:
            return _archive_and_report(item, slack, item_start, dry_run)

        # Verification failed - prepare for next cycle
        log(f"Verification failed (cycle {cycle_label})")

        if cycle + 1 < remaining_cycles:
            # Delete the stale plan so next cycle creates a fresh one
            # that incorporates the verification findings
            if plan_path and os.path.exists(plan_path):
                os.remove(plan_path)
                log(f"Removed stale plan: {plan_path}")
            log("Cycling back to Phase 1 with verification findings...")
        else:
            log(f"Max verification cycles ({MAX_VERIFICATION_CYCLES}) reached for {item.slug}")

    # Clean up plan YAML after max cycles
    if plan_path and os.path.exists(plan_path):
        os.remove(plan_path)
        log(f"Cleaned up plan after max cycles: {plan_path}")
    _mark_as_verification_exhausted(item.path)
    slack.send_status(
        f"*Pipeline: verification exhausted* {item.display_name}\n"
        f"Archived after {MAX_VERIFICATION_CYCLES} failed verification cycles.",
        level="warning"
    )
    _log_summary("WARN", "VERIFICATION_EXHAUSTED", item.slug,
                 f"cycles={MAX_VERIFICATION_CYCLES}")
    _archive_and_report(item, slack, item_start, dry_run)
    log("Defect archived with accumulated verification findings.")

    return False


def process_item(
    item: BacklogItem,
    dry_run: bool = False,
    session_tracker: Optional[SessionUsageTracker] = None,
    item_in_progress: Optional[threading.Event] = None,
    completion_tracker: Optional[CompletionTracker] = None,
) -> bool:
    """Process a single backlog item through the full pipeline.

    For defects, runs a verify-then-fix cycle:
      Phase 1: Create plan
      Phase 2: Execute plan (orchestrator) -- skipped if plan already completed
      Phase 3: Verify symptoms resolved (verifier agent, append-only)
        - If PASS: Phase 4 (archive)
        - If FAIL: Delete stale plan, loop back to Phase 1
          (next plan creation sees verification findings in the defect file)
      Phase 4: Archive

    Optimizations to avoid wasting credits:
    - If verification already passed (PASS verdict exists), skips to archive
    - Prior verification attempts count against MAX_VERIFICATION_CYCLES
    - Fully-completed plans skip the orchestrator (Phase 2)
    - Plan YAML is cleaned up after max cycles to prevent loops on restart

    Returns True on success, False on failure or max cycles exceeded.
    """
    if item_in_progress is not None:
        item_in_progress.set()
    if item.item_type == "analysis":
        return process_analysis_item(item, dry_run, item_in_progress, completion_tracker)
    item_start = time.time()
    _open_item_log(item.slug, item.display_name, item.item_type)
    _log_summary("INFO", "STARTED", item.slug, f"type={item.item_type}")
    try:
        success = _process_item_inner(item, dry_run, session_tracker)
        if success and completion_tracker is not None:
            elapsed = time.time() - item_start
            completion_tracker.record_completion(item.item_type, item.slug, elapsed)
        return success
    except Exception as e:
        log(f"UNEXPECTED ERROR in process_item: {e}")
        _log_summary("ERROR", "CRASHED", item.slug, str(e))
        return False
    finally:
        _close_item_log("done")
        if item_in_progress is not None:
            item_in_progress.clear()


def _get_plan_suspended_tasks(plan_path: str) -> list[dict]:
    """Return all tasks with status 'suspended' from a plan YAML."""
    try:
        with open(plan_path, "r") as f:
            plan = yaml.safe_load(f)
        suspended = []
        for section in plan.get("sections", []):
            for task in section.get("tasks", []):
                if task.get("status") == "suspended":
                    suspended.append(task)
        return suspended
    except (IOError, yaml.YAMLError):
        return []


def _handle_suspension(item: BacklogItem, plan_path: str, slack: SlackNotifier) -> bool:
    """Handle a work item whose orchestrator suspended a task.

    Reads or creates the suspension marker, posts the question to Slack if not
    already posted, and returns True (suspended is not a failure).
    """
    slug = item.slug
    marker = read_suspension_marker(slug)

    if marker is None:
        create_suspension_marker(
            slug=slug,
            item_type=item.item_type,
            item_path=item.path,
            plan_path=plan_path,
            task_id="",
            question="Please provide additional information to continue processing.",
            question_context=f"Work item {slug} is suspended pending human input.",
        )
        marker = read_suspension_marker(slug)

    if marker and not marker.get("slack_thread_ts"):
        thread_ts = slack.post_suspension_question(
            slug=slug,
            item_type=item.item_type,
            question=marker.get("question", "No question available."),
            question_context=marker.get("question_context", ""),
        )
        if thread_ts:
            marker["slack_thread_ts"] = thread_ts
            marker["slack_channel_id"] = slack.get_type_channel_id(item.item_type) or ""
            marker_path = os.path.join(SUSPENDED_DIR, f"{slug}.json")
            with open(marker_path, "w") as f:
                json.dump(marker, f, indent=2)
            log(f"[SUSPENDED] Question posted to Slack for {slug}")

    log(f"[SUSPENDED] {slug} is suspended - checking for answers on next cycle")
    _log_summary("INFO", "SUSPENDED", slug, "waiting-for-human-input")
    return True


def _check_suspended_items(slack: SlackNotifier) -> None:
    """Check all suspended items for Slack answers and reinstate them.

    Lists all marker files in SUSPENDED_DIR, checks each for a threaded Slack
    reply, and clears the marker when an answer is found (allowing the item to
    be picked up on the next scan cycle). Times out markers that have exceeded
    their timeout window.
    """
    suspended_dir = Path(SUSPENDED_DIR)
    if not suspended_dir.exists():
        return

    for marker_file in sorted(suspended_dir.glob("*.json")):
        slug = marker_file.stem
        marker = read_suspension_marker(slug)
        if marker is None:
            continue

        # Timeout check (clear and reinstate without waiting for an answer)
        try:
            suspended_at = datetime.fromisoformat(marker["suspended_at"])
            timeout = timedelta(minutes=marker.get("timeout_minutes", SUSPENSION_TIMEOUT_MINUTES))
            if datetime.now(tz=ZoneInfo("UTC")) >= suspended_at + timeout:
                log(f"WARNING: Suspension timed out for {slug} - reinstating")
                clear_suspension_marker(slug)
                continue
        except (KeyError, ValueError):
            pass

        # If the marker already carries an answer (from a prior partial run),
        # reinstate immediately without another Slack round-trip.
        if marker.get("answer", "").strip():
            log(f"[REINSTATE] {slug} already has an answer - clearing suspension")
            clear_suspension_marker(slug)
            continue

        thread_ts = marker.get("slack_thread_ts", "")
        channel_id = marker.get("slack_channel_id", "")
        if not thread_ts or not channel_id:
            verbose_log(f"Suspended item {slug} has no Slack thread yet - skipping")
            continue

        answer = slack.check_suspension_reply(channel_id, thread_ts)
        if answer:
            log(f"[REINSTATE] Answer received for {slug}: {answer[:80]}")
            marker["answer"] = answer
            with open(str(marker_file), "w") as f:
                json.dump(marker, f, indent=2)
            clear_suspension_marker(slug)


def main_loop(dry_run: bool = False, once: bool = False,
              budget_guard: Optional[PipelineBudgetGuard] = None) -> None:
    """Main processing loop with filesystem watching."""
    global VERBOSE, CLAUDE_CMD

    # Save terminal settings at startup (before any child can corrupt them)
    save_terminal_settings()

    # Resolve Claude binary
    CLAUDE_CMD = resolve_claude_binary()
    log(f"Claude binary: {' '.join(CLAUDE_CMD)}")

    # Capture baseline hashes of source files for hot-reload detection
    global _startup_file_hashes
    _startup_file_hashes = snapshot_source_hashes()
    log(f"Watching {len(_startup_file_hashes)} source file(s) for hot-reload")

    # Clear stale stop semaphore
    clear_stop_semaphore()

    # Track items that failed in this session (don't retry)
    failed_items: set[str] = set()

    # Circuit breaker: track items that completed successfully this session.
    # Prevents infinite loops when archive fails to remove the source file
    # from the backlog directory -- without this, the scanner re-discovers
    # the item and process_item returns True again endlessly.
    completed_items: set[str] = set()

    # Track usage across all work items in this session
    session_tracker = SessionUsageTracker()

    # Track active processing and item completions for progress reporting
    item_in_progress = threading.Event()
    completion_tracker = CompletionTracker()

    # Event to signal new items detected
    new_item_event = threading.Event()

    def on_new_item():
        new_item_event.set()

    # Set up filesystem watcher
    observer = Observer()
    watcher = BacklogWatcher(on_new_item)

    for watch_dir in [DEFECT_DIR, FEATURE_DIR, ANALYSIS_DIR, IDEAS_DIR]:
        if os.path.isdir(watch_dir):
            observer.schedule(watcher, watch_dir, recursive=False)
            verbose_log(f"Watching directory: {watch_dir}")

    if not once:
        observer.start()
        log("Filesystem watcher started")

    # Set up code change monitor (runs in both continuous and --once modes)
    code_monitor = CodeChangeMonitor()
    code_monitor.start()

    global _active_slack
    slack = SlackNotifier()
    slack.set_identity(load_agent_identity(_config), AGENT_ROLE_PIPELINE)
    _active_slack = slack
    slack.start_background_polling()
    reporter = ProgressReporter(slack, completion_tracker, item_in_progress)
    reporter.start()

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
                    # Hot-reload check after resuming in-progress plans
                    if code_monitor.restart_pending.is_set():
                        _perform_restart(
                            "Code change detected after resuming plans",
                            slack, session_tracker, observer, code_monitor
                        )
                    # After resuming, re-scan (completed plans may unblock new items)
                    continue

            # Check suspended items for Slack answers and reinstate them
            _check_suspended_items(slack)

            # Process any raw ideas before scanning backlogs
            intake_count = intake_ideas(dry_run)
            if intake_count > 0:
                log(f"Intake: processed {intake_count} idea(s) into backlog items")

            # Scan for items (with dependency filtering)
            items = scan_all_backlogs()

            # Filter out previously failed or already-completed items
            items = [i for i in items if i.path not in failed_items
                     and i.path not in completed_items]

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

                # Wait for either a filesystem event or the safety scan interval
                new_item_event.clear()
                new_item_event.wait(timeout=SAFETY_SCAN_INTERVAL_SECONDS)
                if code_monitor.restart_pending.is_set():
                    _perform_restart(
                        "Code change detected while idle",
                        slack, session_tracker, observer, code_monitor
                    )
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
                success = process_item(item, dry_run, session_tracker, item_in_progress, completion_tracker)
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

                success = process_item(item, dry_run, session_tracker, item_in_progress, completion_tracker)
                if success:
                    completed_items.add(item.path)
                else:
                    failed_items.add(item.path)
                    log(f"Item failed - will not retry in this session: {item.slug}")

                # Hot-reload: check if source code changed between work items
                if code_monitor.restart_pending.is_set():
                    _perform_restart(
                        "Code change detected between work items",
                        slack, session_tracker,
                        observer if not once else None,
                        code_monitor
                    )

            # Brief pause before next scan
            time.sleep(2)

    except KeyboardInterrupt:
        log("Interrupted by user. Shutting down...")
    finally:
        # Print and write session usage summary
        if session_tracker.work_item_costs:
            print(session_tracker.format_session_summary())
            session_report = session_tracker.write_session_report()
            if session_report:
                log(f"[Session usage report: {session_report}]")

        code_monitor.stop()
        reporter.stop()
        slack.stop_background_polling()
        if not once:
            observer.stop()
            observer.join(timeout=5)
        remove_pid_file()
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

    # Clean up PID file and restore terminal settings
    remove_pid_file()
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
    log(f"  Analysis backlog: {ANALYSIS_DIR}/")
    log(f"  Mode: {'dry-run' if args.dry_run else 'once' if args.once else 'continuous watch'}")
    ensure_directories()
    write_pid_file()

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
