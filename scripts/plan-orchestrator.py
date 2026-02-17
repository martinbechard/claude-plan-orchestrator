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
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import yaml

# Optional Socket Mode support for interactive Slack questions
try:
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    SOCKET_MODE_AVAILABLE = True
except ImportError:
    SOCKET_MODE_AVAILABLE = False

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
TASK_LOG_DIR = Path(".claude/plans/logs")
STOP_SEMAPHORE_PATH = ".claude/plans/.stop"
DEFAULT_MAX_ATTEMPTS = 3
CLAUDE_TIMEOUT_SECONDS = 600  # 10 minutes per task
MAX_PLAN_NAME_LENGTH = 50  # Max chars from plan name used in report filenames

# Budget enforcement defaults
DEFAULT_MAX_QUOTA_PERCENT = 100.0
DEFAULT_QUOTA_CEILING_USD = 0.0
DEFAULT_RESERVED_BUDGET_USD = 0.0

# Model escalation defaults
MODEL_TIERS: list[str] = ["haiku", "sonnet", "opus"]
DEFAULT_ESCALATE_AFTER_FAILURES = 2
DEFAULT_MAX_MODEL = "opus"
DEFAULT_VALIDATION_MODEL = "sonnet"
DEFAULT_STARTING_MODEL = "sonnet"

# Slack notification configuration
SLACK_CONFIG_PATH = ".claude/slack.local.yaml"
SLACK_QUESTION_PATH = ".claude/slack-pending-question.json"
SLACK_ANSWER_PATH = ".claude/slack-answer.json"
SLACK_POLL_INTERVAL_SECONDS = 30
SLACK_LEVEL_EMOJI = {
    "info": ":large_blue_circle:",
    "success": ":white_check_mark:",
    "error": ":x:",
    "warning": ":warning:",
    "question": ":question:",
}
SLACK_LAST_READ_PATH = ".claude/slack-last-read.json"
SLACK_INBOUND_POLL_LIMIT = 20


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

# Keywords indicating a design/architecture task.
# When infer_agent_for_task() matches any of these, it selects "systems-designer".
DESIGNER_KEYWORDS = [
    "design", "wireframe", "layout", "architecture", "mockup"
]

# Keywords indicating a plan-generation task.
# When infer_agent_for_task() matches any of these, it selects "planner".
PLANNER_KEYWORDS = [
    "extend plan", "create tasks", "create phases", "plan sections",
    "append implementation"
]

# Keywords indicating a QA audit task.
# When infer_agent_for_task() matches any of these, it selects "qa-auditor".
QA_AUDITOR_KEYWORDS = [
    "qa audit", "test plan", "checklist audit", "coverage matrix",
    "qa-auditor", "functional spec verification"
]

# Keywords indicating a spec verification task.
# When infer_agent_for_task() matches any of these, it selects "spec-verifier".
SPEC_VERIFIER_KEYWORDS = [
    "spec verifier", "spec verification", "functional spec",
    "spec-verifier", "spec compliance"
]

# Keywords indicating a UX review task.
# When infer_agent_for_task() matches any of these, it selects "ux-reviewer".
UX_REVIEWER_KEYWORDS = [
    "ux review", "ux-reviewer", "usability review",
    "accessibility review", "ui quality"
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
    """Infer which agent should execute a task based on name and description keywords.

    Combines the task name and description, then scans for keywords in priority order:
    1. PLANNER_KEYWORDS (multi-word phrases, checked before single-word keywords
       to avoid false matches on words like "design") -> "planner"
    2. QA_AUDITOR_KEYWORDS (multi-word phrases, checked before single-word keywords
       to avoid false matches) -> "qa-auditor"
    3. SPEC_VERIFIER_KEYWORDS (multi-word phrases, checked before REVIEWER_KEYWORDS
       to avoid false matches on "verification") -> "spec-verifier"
    4. UX_REVIEWER_KEYWORDS (multi-word phrases, checked before REVIEWER_KEYWORDS
       to avoid false matches on "review") -> "ux-reviewer"
    5. REVIEWER_KEYWORDS -> "code-reviewer"
    6. DESIGNER_KEYWORDS -> "systems-designer"
    7. Default -> "coder"

    Returns None if the agents directory (AGENTS_DIR) does not exist, which
    preserves backward compatibility for projects that have not adopted agents.
    """
    if not os.path.isdir(AGENTS_DIR):
        return None

    text = (task.get("name", "") + " " + task.get("description", "")).lower()

    for keyword in PLANNER_KEYWORDS:
        if keyword in text:
            return "planner"

    for keyword in QA_AUDITOR_KEYWORDS:
        if keyword in text:
            return "qa-auditor"

    for keyword in SPEC_VERIFIER_KEYWORDS:
        if keyword in text:
            return "spec-verifier"

    for keyword in UX_REVIEWER_KEYWORDS:
        if keyword in text:
            return "ux-reviewer"

    for keyword in REVIEWER_KEYWORDS:
        if keyword in text:
            return "code-reviewer"

    for keyword in DESIGNER_KEYWORDS:
        if keyword in text:
            return "systems-designer"

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
class TaskUsage:
    """Token usage and cost data from a single Claude CLI invocation."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    total_cost_usd: float = 0.0
    num_turns: int = 0
    duration_api_ms: int = 0


@dataclass
class TaskResult:
    """Result of a task execution."""
    success: bool
    message: str
    duration_seconds: float
    plan_modified: bool = False
    rate_limited: bool = False
    rate_limit_reset_time: Optional[datetime] = None
    usage: Optional[TaskUsage] = None


def parse_task_usage(result_data: dict) -> TaskUsage:
    """Extract token usage from a Claude CLI result JSON object.

    Args:
        result_data: The parsed JSON result from Claude CLI, containing
             usage, total_cost_usd, num_turns, and duration_api_ms fields.

    Returns:
        A TaskUsage populated from the result data, with zeros for missing fields.
    """
    usage = result_data.get("usage", {})
    return TaskUsage(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read_tokens=usage.get("cache_read_input_tokens", 0),
        cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
        total_cost_usd=result_data.get("total_cost_usd", 0.0),
        num_turns=result_data.get("num_turns", 0),
        duration_api_ms=result_data.get("duration_api_ms", 0),
    )


class PlanUsageTracker:
    """Accumulates token usage across all tasks in a plan run."""

    def __init__(self) -> None:
        self.task_usages: dict[str, TaskUsage] = {}
        self.task_models: dict[str, str] = {}

    def record(self, task_id: str, usage: TaskUsage, model: str = "") -> None:
        """Record usage for a completed task."""
        self.task_usages[task_id] = usage
        self.task_models[task_id] = model

    def get_section_usage(self, plan: dict, section_id: str) -> TaskUsage:
        """Aggregate usage for all tasks in a given section."""
        total = TaskUsage()
        for section in plan.get("sections", []):
            if section.get("id") == section_id:
                for task in section.get("tasks", []):
                    tid = task.get("id", "")
                    if tid in self.task_usages:
                        u = self.task_usages[tid]
                        total.input_tokens += u.input_tokens
                        total.output_tokens += u.output_tokens
                        total.cache_read_tokens += u.cache_read_tokens
                        total.cache_creation_tokens += u.cache_creation_tokens
                        total.total_cost_usd += u.total_cost_usd
                        total.num_turns += u.num_turns
                        total.duration_api_ms += u.duration_api_ms
        return total

    def get_total_usage(self) -> TaskUsage:
        """Aggregate usage across all recorded tasks."""
        total = TaskUsage()
        for u in self.task_usages.values():
            total.input_tokens += u.input_tokens
            total.output_tokens += u.output_tokens
            total.cache_read_tokens += u.cache_read_tokens
            total.cache_creation_tokens += u.cache_creation_tokens
            total.total_cost_usd += u.total_cost_usd
            total.num_turns += u.num_turns
            total.duration_api_ms += u.duration_api_ms
        return total

    def get_cache_hit_rate(self) -> float:
        """Calculate overall cache hit rate.

        Cache hit rate measures what fraction of input context was served
        from cache vs. freshly processed. Higher means lower cost per token.
        """
        total = self.get_total_usage()
        denom = total.cache_read_tokens + total.input_tokens
        return total.cache_read_tokens / denom if denom > 0 else 0.0

    def format_summary_line(self, task_id: str) -> str:
        """Format a one-line usage summary for a task."""
        u = self.task_usages.get(task_id)
        if not u:
            return ""
        total = self.get_total_usage()
        cache_denom = u.cache_read_tokens + u.input_tokens
        cache_pct = (u.cache_read_tokens / cache_denom * 100) if cache_denom > 0 else 0
        model = self.task_models.get(task_id, "")
        model_str = f" [{model}]" if model else ""
        return (
            f"[Usage] Task {task_id}{model_str}: ${u.total_cost_usd:.4f} | "
            f"{u.input_tokens:,} in / {u.output_tokens:,} out / "
            f"{u.cache_read_tokens:,} cached ({cache_pct:.0f}% cache hit) | "
            f"Running: ${total.total_cost_usd:.4f}"
        )

    def format_final_summary(self, plan: dict) -> str:
        """Format the final usage summary printed after all tasks complete."""
        total = self.get_total_usage()
        cache_rate = self.get_cache_hit_rate()
        lines = [
            "\n=== Usage Summary ===",
            f"Total cost: ${total.total_cost_usd:.4f}",
            f"Total tokens: {total.input_tokens:,} input / {total.output_tokens:,} output",
            f"Cache: {total.cache_read_tokens:,} read / {total.cache_creation_tokens:,} created ({cache_rate:.0%} hit rate)",
            f"API time: {total.duration_api_ms / 1000:.1f}s across {total.num_turns} turns",
            "Per-section breakdown:",
        ]
        for section in plan.get("sections", []):
            sid = section.get("id", "")
            sname = section.get("name", sid)
            su = self.get_section_usage(plan, sid)
            task_count = sum(
                1 for t in section.get("tasks", []) if t.get("id") in self.task_usages
            )
            if task_count > 0:
                lines.append(f"  {sname}: ${su.total_cost_usd:.4f} ({task_count} tasks)")
        return "\n".join(lines)

    def write_report(self, plan: dict, plan_path: str) -> Optional[Path]:
        """Write a usage report JSON file alongside the plan logs.

        Produces a structured JSON report with per-task and per-section usage
        breakdowns. The report file is written to TASK_LOG_DIR with a filename
        derived from the plan name.

        Args:
            plan: The parsed plan dict containing meta, sections, and tasks.
            plan_path: The filesystem path to the plan YAML file.

        Returns:
            The report file path, or None if no usage data was recorded.
        """
        if not self.task_usages:
            return None
        total = self.get_total_usage()
        plan_name = plan.get("meta", {}).get("name", "unknown")
        safe_name = plan_name.lower().replace(" ", "-")[:MAX_PLAN_NAME_LENGTH]
        report_path = TASK_LOG_DIR / f"{safe_name}-usage-report.json"
        report = {
            "plan_name": plan_name,
            "plan_path": plan_path,
            "completed_at": datetime.now().isoformat(),
            "total": {
                "cost_usd": total.total_cost_usd,
                "input_tokens": total.input_tokens,
                "output_tokens": total.output_tokens,
                "cache_read_tokens": total.cache_read_tokens,
                "cache_creation_tokens": total.cache_creation_tokens,
                "cache_hit_rate": self.get_cache_hit_rate(),
                "num_turns": total.num_turns,
                "duration_api_ms": total.duration_api_ms,
            },
            "sections": [],
            "tasks": [],
        }
        for section in plan.get("sections", []):
            sid = section.get("id", "")
            su = self.get_section_usage(plan, sid)
            task_count = sum(
                1 for t in section.get("tasks", [])
                if t.get("id") in self.task_usages
            )
            if task_count > 0:
                report["sections"].append({
                    "id": sid,
                    "name": section.get("name", sid),
                    "cost_usd": su.total_cost_usd,
                    "task_count": task_count,
                })
        for tid, u in self.task_usages.items():
            report["tasks"].append({
                "id": tid,
                "cost_usd": u.total_cost_usd,
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "cache_read_tokens": u.cache_read_tokens,
                "cache_creation_tokens": u.cache_creation_tokens,
                "num_turns": u.num_turns,
                "duration_api_ms": u.duration_api_ms,
                "model": self.task_models.get(tid, ""),
            })
        TASK_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        return report_path


@dataclass
class BudgetConfig:
    """Budget limits for plan execution.

    Configuration for the budget guard that enforces spending limits.
    A ceiling of 0.0 (the default) disables budget enforcement entirely.
    """
    max_quota_percent: float = DEFAULT_MAX_QUOTA_PERCENT
    quota_ceiling_usd: float = DEFAULT_QUOTA_CEILING_USD
    reserved_budget_usd: float = DEFAULT_RESERVED_BUDGET_USD

    @property
    def effective_limit_usd(self) -> float:
        """Calculate effective spending limit in USD."""
        if self.quota_ceiling_usd <= 0:
            return float('inf')
        percent_limit = self.quota_ceiling_usd * (self.max_quota_percent / 100.0)
        if self.reserved_budget_usd > 0:
            reserve_limit = self.quota_ceiling_usd - self.reserved_budget_usd
            return min(percent_limit, reserve_limit)
        return percent_limit

    @property
    def is_enabled(self) -> bool:
        """Whether budget enforcement is active."""
        return self.quota_ceiling_usd > 0


class BudgetGuard:
    """Checks cumulative cost against budget limits before each task.

    Wraps a PlanUsageTracker to read current spending. Does not maintain
    its own cost counter; queries the tracker directly to avoid duplicate state.
    """

    def __init__(self, config: BudgetConfig, usage_tracker: PlanUsageTracker) -> None:
        self.config = config
        self.usage_tracker = usage_tracker

    def can_proceed(self) -> tuple[bool, str]:
        """Check if budget allows another task.
        Returns (can_proceed, reason_if_not).
        """
        if not self.config.is_enabled:
            return (True, "")
        total = self.usage_tracker.get_total_usage()
        spent = total.total_cost_usd
        limit = self.config.effective_limit_usd
        if spent >= limit:
            pct = (spent / self.config.quota_ceiling_usd * 100) if self.config.quota_ceiling_usd > 0 else 0
            reason = (
                f"Budget limit reached: ${spent:.4f} / ${limit:.4f} "
                f"({pct:.1f}% of ${self.config.quota_ceiling_usd:.2f} ceiling)"
            )
            return (False, reason)
        return (True, "")

    def get_usage_percent(self) -> float:
        """Current spending as percentage of ceiling."""
        if not self.config.is_enabled:
            return 0.0
        total = self.usage_tracker.get_total_usage()
        return (total.total_cost_usd / self.config.quota_ceiling_usd * 100)

    def format_status(self) -> str:
        """Format current budget status for display."""
        if not self.config.is_enabled:
            return "[Budget: unlimited]"
        total = self.usage_tracker.get_total_usage()
        spent = total.total_cost_usd
        limit = self.config.effective_limit_usd
        pct = self.get_usage_percent()
        return f"[Budget: ${spent:.4f} / ${limit:.4f} ({pct:.1f}% of ceiling)]"


def parse_budget_config(plan: dict, args: argparse.Namespace) -> BudgetConfig:
    """Parse budget configuration from plan YAML and CLI overrides.

    Priority: CLI flags > plan YAML meta.budget > defaults.
    A ceiling of 0.0 means no budget enforcement.
    """
    budget_meta = plan.get("meta", {}).get("budget", {})
    config = BudgetConfig(
        max_quota_percent=budget_meta.get("max_quota_percent", DEFAULT_MAX_QUOTA_PERCENT),
        quota_ceiling_usd=budget_meta.get("quota_ceiling_usd", DEFAULT_QUOTA_CEILING_USD),
        reserved_budget_usd=budget_meta.get("reserved_budget_usd", DEFAULT_RESERVED_BUDGET_USD),
    )
    if hasattr(args, 'max_budget_pct') and args.max_budget_pct is not None:
        config.max_quota_percent = args.max_budget_pct
    if hasattr(args, 'quota_ceiling') and args.quota_ceiling is not None:
        config.quota_ceiling_usd = args.quota_ceiling
    if hasattr(args, 'reserved_budget') and args.reserved_budget is not None:
        config.reserved_budget_usd = args.reserved_budget
    return config


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


@dataclass
class EscalationConfig:
    """Model escalation configuration for cost-aware tier promotion.

    Controls automatic model upgrades when tasks fail repeatedly.
    When disabled, models are unchanged (backwards compatible).
    """
    enabled: bool = False
    escalate_after: int = DEFAULT_ESCALATE_AFTER_FAILURES
    max_model: str = DEFAULT_MAX_MODEL
    validation_model: str = DEFAULT_VALIDATION_MODEL
    starting_model: str = DEFAULT_STARTING_MODEL

    def get_effective_model(self, agent_model: str, attempt: int) -> str:
        """Compute the effective model for a given agent and attempt number.

        Uses the MODEL_TIERS ladder to determine escalation. Attempts 1 through
        escalate_after use the base model. Each subsequent batch of escalate_after
        attempts promotes one tier, capped at max_model.

        Args:
            agent_model: The agent's starting model from frontmatter.
            attempt: The current attempt number (1-based).

        Returns:
            The model string to use for this attempt.
        """
        if not self.enabled:
            return agent_model
        base = agent_model or self.starting_model
        if base not in MODEL_TIERS:
            return base
        base_idx = MODEL_TIERS.index(base)
        max_idx = MODEL_TIERS.index(self.max_model) if self.max_model in MODEL_TIERS else len(MODEL_TIERS) - 1
        steps = max(0, (attempt - 1) // self.escalate_after)
        effective_idx = min(base_idx + steps, max_idx)
        return MODEL_TIERS[effective_idx]


def parse_escalation_config(plan: dict) -> EscalationConfig:
    """Parse model escalation configuration from plan YAML meta.

    Reads meta.model_escalation from the plan dict. When the block
    is absent, returns a disabled EscalationConfig (backwards compatible).

    Args:
        plan: The full plan dict loaded from YAML.

    Returns:
        An EscalationConfig populated from plan meta or defaults.
    """
    esc_meta = plan.get("meta", {}).get("model_escalation", {})
    if not esc_meta:
        return EscalationConfig()
    return EscalationConfig(
        enabled=esc_meta.get("enabled", False),
        escalate_after=esc_meta.get("escalate_after", DEFAULT_ESCALATE_AFTER_FAILURES),
        max_model=esc_meta.get("max_model", DEFAULT_MAX_MODEL),
        validation_model=esc_meta.get("validation_model", DEFAULT_VALIDATION_MODEL),
        starting_model=esc_meta.get("starting_model", DEFAULT_STARTING_MODEL),
    )


def build_validation_prompt(
    task: dict,
    section: dict,
    task_result: "TaskResult",
    validator_name: str,
) -> str:
    """Build the prompt for a validation agent to verify a completed task.

    Loads the validator agent definition and constructs a prompt that includes
    the agent body, original task context, task result details, and validation
    instructions with structured output format.

    Args:
        task: The task dict from the plan YAML.
        section: The section dict containing this task.
        task_result: The TaskResult from the completed task execution.
        validator_name: Name of the validator agent to load (e.g. 'validator').

    Returns:
        The fully assembled validation prompt string.
    """
    agent_def = load_agent_definition(validator_name)
    agent_body = agent_def["body"] if agent_def else ""

    task_id = task.get("id", "unknown")
    task_name = task.get("name", "Unnamed task")
    task_description = task.get("description", "No description")
    result_message = task_result.message
    duration = task_result.duration_seconds

    return f"""{agent_body}

---

You are validating the results of task {task_id}: {task_name}

## Original Task Description

{task_description}

## Task Result

Status: completed

Message: {result_message}

Duration: {duration:.1f}s

## Validation Checks

1. Run: {BUILD_COMMAND}

2. Run: {TEST_COMMAND}

3. Verify the task description requirements are met

4. Check for regressions in related code

## Output Format

Produce your verdict in this exact format:

**Verdict: PASS** or **Verdict: WARN** or **Verdict: FAIL**

**Findings:**

- [PASS|WARN|FAIL] Description with file:line references

IMPORTANT: You MUST write .claude/plans/task-status.json when done.
"""


# Default verdict when parsing fails — conservative approach treats
# an unparseable validator output as a failure.
DEFAULT_VERDICT = "FAIL"


def parse_validation_verdict(output: str) -> ValidationVerdict:
    """Parse a validation verdict from validator agent output.

    Scans the output for a structured verdict line matching VERDICT_PATTERN
    (e.g. '**Verdict: PASS**') and extracts individual findings matching
    FINDING_PATTERN (e.g. '- [FAIL] Build failed at file:line').

    If no verdict pattern is found in the output, defaults to FAIL. This
    conservative approach ensures that a validator which crashes, times out,
    or produces malformed output is treated as a validation failure rather
    than silently passing.

    Args:
        output: The raw text output from the validator agent.

    Returns:
        A ValidationVerdict with the parsed verdict, findings list, and
        the original raw output preserved for debugging.
    """
    verdict_match = VERDICT_PATTERN.search(output)
    verdict = verdict_match.group(1).upper() if verdict_match else DEFAULT_VERDICT

    finding_matches = FINDING_PATTERN.findall(output)
    findings = [f"[{severity.upper()}] {description}" for severity, description in finding_matches]

    return ValidationVerdict(verdict=verdict, findings=findings, raw_output=output)


# Log file section delimiter used to extract stdout from task logs.
LOG_STDOUT_SECTION = "=== STDOUT ==="
LOG_STDERR_SECTION = "=== STDERR ==="
# Fallback agent name when no agent is specified or inferred for a task.
FALLBACK_AGENT_NAME = "coder"
# Prefix for validation log messages printed to the console.
VALIDATION_LOG_PREFIX = "[VALIDATION]"
# Maximum characters from the validation prompt to show in dry-run preview.
DRY_RUN_PROMPT_PREVIEW_LENGTH = 500


def get_most_recent_log_file() -> Optional[Path]:
    """Return the most recently modified log file from the task log directory.

    Scans TASK_LOG_DIR for files matching the task-*.log pattern and returns
    the one with the latest modification time. Returns None if no log files
    exist or the directory does not exist.
    """
    if not TASK_LOG_DIR.exists():
        return None

    log_files = sorted(TASK_LOG_DIR.glob("task-*.log"), key=lambda p: p.stat().st_mtime)
    return log_files[-1] if log_files else None


def read_log_stdout(log_path: Path) -> str:
    """Extract the STDOUT section from a task log file.

    Task log files are written by run_claude_task() with delimited sections
    (=== STDOUT === and === STDERR ===). This function extracts only the
    content between the STDOUT and STDERR delimiters.

    Returns the extracted stdout text, or an empty string if the section
    is not found or the file cannot be read.
    """
    try:
        content = log_path.read_text()
    except IOError:
        return ""

    stdout_start = content.find(LOG_STDOUT_SECTION)
    if stdout_start < 0:
        return ""

    stdout_start += len(LOG_STDOUT_SECTION)
    stderr_start = content.find(LOG_STDERR_SECTION, stdout_start)

    if stderr_start < 0:
        return content[stdout_start:].strip()

    return content[stdout_start:stderr_start].strip()


def run_validation(
    task: dict,
    section: dict,
    task_result: "TaskResult",
    validation_config: ValidationConfig,
    dry_run: bool = False,
    escalation_config: Optional[EscalationConfig] = None,
) -> ValidationVerdict:
    """Execute validation on a completed task using configured validator agents.

    Spawns each validator agent defined in validation_config.validators to
    independently verify the task result. Uses build_validation_prompt() to
    construct the validation prompt and parse_validation_verdict() to interpret
    the validator's output.

    Short-circuits on the first FAIL verdict — remaining validators are skipped.
    Returns a PASS verdict immediately (without running validators) when the
    task's agent type is not in validation_config.run_after.

    Args:
        task: The task dict from the plan YAML.
        section: The section dict containing the task.
        task_result: The TaskResult from the task's execution.
        validation_config: Validation settings from the plan meta.
        dry_run: If True, print a prompt preview and return PASS without executing.
        escalation_config: Model escalation settings. When provided and enabled,
            uses escalation_config.validation_model for the validator CLI call.

    Returns:
        A ValidationVerdict with the aggregate result of all validators.
    """
    task_id = task.get("id", "unknown")

    # 1. Determine the agent that executed the task
    agent_name = task.get("agent") or infer_agent_for_task(task) or FALLBACK_AGENT_NAME

    # 2. Check if validation should run for this agent type
    if agent_name not in validation_config.run_after:
        return ValidationVerdict(verdict="PASS")

    # 3. Run each validator
    final_verdict = ValidationVerdict(verdict="PASS")

    for validator in validation_config.validators:
        print(f"{VALIDATION_LOG_PREFIX} Running validator '{validator}' on task {task_id}")

        # 3a. Build the validation prompt
        prompt = build_validation_prompt(task, section, task_result, validator)

        # 3b. Dry-run: preview and return PASS
        if dry_run:
            print(f"{VALIDATION_LOG_PREFIX} [DRY RUN] Prompt preview:")
            print(prompt[:DRY_RUN_PROMPT_PREVIEW_LENGTH])
            if len(prompt) > DRY_RUN_PROMPT_PREVIEW_LENGTH:
                print(f"... ({len(prompt) - DRY_RUN_PROMPT_PREVIEW_LENGTH} more chars)")
            return ValidationVerdict(verdict="PASS")

        # 3c. Clear the status file so the validator writes a fresh one
        clear_status_file()

        # 3d. Execute the validator via Claude CLI
        validation_model = ""
        if escalation_config and escalation_config.enabled:
            validation_model = escalation_config.validation_model
        validator_result = run_claude_task(prompt, model=validation_model)

        # 3e. If the validator process itself failed, treat as FAIL
        if not validator_result.success:
            print(f"{VALIDATION_LOG_PREFIX} Validator '{validator}' failed to execute: "
                  f"{validator_result.message}")
            return ValidationVerdict(
                verdict="FAIL",
                findings=[f"Validator '{validator}' failed to execute: {validator_result.message}"],
            )

        # 3f. Read the most recent log file for the validator's full output
        log_path = get_most_recent_log_file()
        if log_path:
            validator_output = read_log_stdout(log_path)
        else:
            # Fallback: use the status file message as output
            validator_output = validator_result.message

        # 3g. Parse the verdict
        verdict = parse_validation_verdict(validator_output)
        print(f"{VALIDATION_LOG_PREFIX} Validator '{validator}' verdict: {verdict.verdict}")

        if verdict.findings:
            for finding in verdict.findings:
                print(f"  {finding}")

        # 3h. Short-circuit on FAIL
        if verdict.verdict == "FAIL":
            return verdict

        # Keep track of the last non-FAIL verdict (could be WARN)
        final_verdict = verdict

    return final_verdict


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
    dry_run: bool = False,
    model: str = ""
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
        if model:
            cmd.extend(["--model", model])

        verbose_log(f"[PARALLEL] Task {task_id} using model: {model or 'default'}", "PARALLEL")
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

    # Prepend validation findings from previous failed validation
    validation_findings = task.get("validation_findings", "")
    validation_header = ""
    if validation_findings:
        validation_header = f"""## PREVIOUS VALIDATION FAILED

The previous attempt at this task was completed but failed validation.
You must address these findings:

{validation_findings}

---

"""

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

    return f"""{agent_content}{validation_header}{subagent_header}Run task {task['id']} from the implementation plan.

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


def stream_json_output(pipe, collector: OutputCollector, result_capture: dict) -> None:
    """Stream output from Claude CLI in stream-json format, showing tool use and text in real-time.

    Args:
        pipe: The stdout pipe from the Claude CLI subprocess.
        collector: OutputCollector that accumulates raw output lines.
        result_capture: A mutable dict that will be populated with the full result event data
            when the 'result' event is received. The caller reads this after thread join.
    """
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
                result_capture.update(event)

    except Exception as e:
        if VERBOSE:
            verbose_log(f"Error streaming JSON: {e}", "ERROR")


def run_claude_task(prompt: str, dry_run: bool = False, model: str = "") -> TaskResult:
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
    if model:
        cmd.extend(["--model", model])
    # In verbose mode, use stream-json for real-time tool/text streaming
    # In non-verbose mode, use json to capture structured output with usage data
    if VERBOSE:
        cmd.extend(["--output-format", "stream-json", "--verbose"])
    else:
        cmd.extend(["--output-format", "json"])
    verbose_log(f"Command: {' '.join(CLAUDE_CMD)} --dangerously-skip-permissions --print <prompt>", "EXEC")
    verbose_log(f"Prompt length: {len(prompt)} chars", "EXEC")
    if model:
        verbose_log(f"Model override: {model}", "EXEC")
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

        # Shared dict to capture result event data from CLI output
        result_capture: dict = {}

        # Start threads to stream/collect stdout and stderr
        if VERBOSE:
            stdout_thread = threading.Thread(
                target=stream_json_output,
                args=(process.stdout, stdout_collector, result_capture)
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

        # Extract usage data from CLI output (before log write so it's available for headers)
        # Verbose mode: result_capture already populated by stream_json_output thread
        # Non-verbose mode: parse entire stdout as JSON
        if not VERBOSE:
            try:
                result_json = json.loads(stdout_collector.get_output())
                result_capture.update(result_json)
            except (json.JSONDecodeError, ValueError):
                pass  # Non-JSON output, no usage data available

        task_usage = parse_task_usage(result_capture) if result_capture else None

        # Save output to log file for debugging
        TASK_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = TASK_LOG_DIR / f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
        with open(log_file, "w") as f:
            f.write(f"=== Claude Task Output ===\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Duration: {duration:.1f}s\n")
            f.write(f"Return code: {returncode}\n")
            f.write(f"Stdout lines: {stdout_collector.line_count}\n")
            f.write(f"Stderr lines: {stderr_collector.line_count}\n")
            if result_capture:
                cost = result_capture.get("total_cost_usd", 0)
                usage_data = result_capture.get("usage", {})
                f.write(f"Cost: ${cost:.4f}\n")
                f.write(f"Tokens: {usage_data.get('input_tokens', 0)} input / "
                        f"{usage_data.get('output_tokens', 0)} output / "
                        f"{usage_data.get('cache_read_input_tokens', 0)} cache_read / "
                        f"{usage_data.get('cache_creation_input_tokens', 0)} cache_create\n")
                f.write(f"Turns: {result_capture.get('num_turns', 0)}\n")
                f.write(f"API time: {result_capture.get('duration_api_ms', 0)}ms\n")
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
                    rate_limit_reset_time=reset_time,
                    usage=task_usage
                )

            error_msg = stderr_collector.get_output()[:500] if stderr_collector.bytes_received > 0 else "Unknown error"
            return TaskResult(
                success=False,
                message=f"Claude exited with code {returncode}: {error_msg}",
                duration_seconds=duration,
                usage=task_usage
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
                plan_modified=plan_modified,
                usage=task_usage
            )
        elif status and status.get("status") == "failed":
            verbose_log("Task status: FAILED", "STATUS")
            return TaskResult(
                success=False,
                message=status.get("message", "Task failed"),
                duration_seconds=duration,
                plan_modified=plan_modified,
                usage=task_usage
            )
        else:
            verbose_log("Task status: UNKNOWN (no status file)", "STATUS")
            # No status file or unclear status - check if build passes
            return TaskResult(
                success=False,
                message="No status file written by Claude",
                duration_seconds=duration,
                usage=task_usage
            )

    except subprocess.TimeoutExpired:
        verbose_log(f"TIMEOUT after {CLAUDE_TIMEOUT_SECONDS}s", "ERROR")
        return TaskResult(
            success=False,
            message=f"Task timed out after {CLAUDE_TIMEOUT_SECONDS} seconds",
            duration_seconds=CLAUDE_TIMEOUT_SECONDS,
            usage=None
        )
    except Exception as e:
        verbose_log(f"Exception: {type(e).__name__}: {e}", "ERROR")
        return TaskResult(
            success=False,
            message=f"Error running Claude: {str(e)}",
            duration_seconds=time.time() - start_time,
            usage=None
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


class SlackNotifier:
    """Sends messages to Slack via Slack Web API.

    Reads .claude/slack.local.yaml on init. If the file is missing or
    slack.enabled is false, all methods are no-ops (silent, no errors).
    Uses urllib.request (stdlib only) for HTTP POST with Bearer token auth.
    Requires bot_token and channel_id from config.

    Reference: docs/plans/2026-02-16-14-slack-app-migration-design.md
    """

    def __init__(self, config_path: str = SLACK_CONFIG_PATH):
        """Initialize SlackNotifier from config file.

        Args:
            config_path: Path to slack.local.yaml config file
        """
        self._enabled = False
        self._bot_token = ""
        self._app_token = ""
        self._channel_id = ""
        self._notify_config = {}
        self._question_config = {}
        self._socket_handler = None
        self._pending_answer = None  # threading.Event set when answer received
        self._last_answer = None     # stores the answer value

        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            if not isinstance(config, dict):
                return

            slack_config = config.get("slack", {})
            if not isinstance(slack_config, dict):
                return

            self._enabled = slack_config.get("enabled", False)
            if not self._enabled:
                return

            self._bot_token = slack_config.get("bot_token", "")
            self._app_token = slack_config.get("app_token", "")
            self._channel_id = slack_config.get("channel_id", "")
            self._notify_config = slack_config.get("notify", {})
            self._question_config = slack_config.get("questions", {})

        except (IOError, yaml.YAMLError):
            # Config file missing or invalid - remain disabled
            pass

    def is_enabled(self) -> bool:
        """Check if Slack notifications are enabled.

        Returns:
            True if enabled and configured, False otherwise
        """
        return self._enabled

    def _should_notify(self, event: str) -> bool:
        """Check if a specific event type is enabled in config.

        Args:
            event: Event name (e.g., "on_task_complete")

        Returns:
            True if enabled and event is configured for notification
        """
        return self._enabled and self._notify_config.get(event, False)

    def _ensure_socket_mode(self) -> bool:
        """Start Socket Mode handler if available and not already running.

        Returns:
            True if Socket Mode is available and started, False otherwise
        """
        if not SOCKET_MODE_AVAILABLE:
            return False
        if self._socket_handler is not None:
            return True
        if not self._app_token:
            return False
        try:
            app = App(token=self._bot_token)
            @app.action(re.compile(r"orchestrator_answer_.*"))
            def handle_answer(ack, action, body):
                ack()
                self._last_answer = action.get("value", "")
                if self._pending_answer:
                    self._pending_answer.set()
            handler = SocketModeHandler(app, self._app_token)
            handler.connect()  # non-blocking WebSocket connect
            self._socket_handler = handler
            return True
        except Exception as e:
            print(f"[SLACK] Socket Mode failed to start: {e}")
            return False

    def _post_message(self, payload: dict) -> bool:
        """POST a message to Slack via chat.postMessage API.

        Uses urllib.request with Bearer token auth. Returns True on success.
        Catches all exceptions and logs errors without raising.

        Args:
            payload: Slack Block Kit payload dict

        Returns:
            True if API returns ok: true, False otherwise
        """
        if not self._bot_token or not self._channel_id:
            return False

        payload["channel"] = self._channel_id

        try:
            req = urllib.request.Request(
                "https://slack.com/api/chat.postMessage",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"Bearer {self._bot_token}"
                }
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                return result.get("ok", False)

        except Exception as e:
            print(f"[SLACK] Failed to post message: {e}")
            return False

    def _build_status_block(self, message: str, level: str) -> dict:
        """Build a Slack Block Kit payload for a status message.

        Args:
            message: Message text (supports Slack markdown)
            level: Message level (info, success, error, warning, question)

        Returns:
            Slack Block Kit payload dict
        """
        emoji = SLACK_LEVEL_EMOJI.get(level, ":large_blue_circle:")
        return {
            "blocks": [{
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"{emoji} {message}"}
            }]
        }

    def send_status(self, message: str, level: str = "info") -> None:
        """Send a status update to Slack. No-op if disabled.

        Args:
            message: Status message text
            level: Message level (info, success, error, warning)
        """
        if not self._enabled or not self._bot_token or not self._channel_id:
            return

        payload = self._build_status_block(message, level)
        self._post_message(payload)

    def send_question(
        self,
        question: str,
        options: list[str],
        timeout_minutes: int = 0
    ) -> Optional[str]:
        """Send a question to Slack and wait for answer.

        Uses Socket Mode for interactive buttons if available, otherwise falls
        back to file-based polling. Posts question to Slack with Block Kit action
        buttons (Socket Mode) or text instructions (file-based).

        Args:
            question: Question text
            options: List of valid answer options
            timeout_minutes: Timeout in minutes (0 = use config default)

        Returns:
            Answer string if received, fallback value on timeout, None on error
        """
        if not self._should_notify("on_question"):
            return None
        if not self._question_config.get("enabled", False):
            return None

        effective_timeout = timeout_minutes or self._question_config.get("timeout_minutes", 60)
        fallback = self._question_config.get("fallback", "skip")

        # Try to use Socket Mode if available
        use_socket = self._ensure_socket_mode()

        # Build question payload
        if use_socket:
            # Block Kit action buttons for interactive response
            actions = [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": opt},
                    "action_id": f"orchestrator_answer_{i}",
                    "value": opt
                }
                for i, opt in enumerate(options)
            ]
            payload = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f":question: *{question}*"}
                    },
                    {
                        "type": "actions",
                        "elements": actions
                    }
                ]
            }
        else:
            # Text-based question with file polling instructions
            options_text = " | ".join(f"`{opt}`" for opt in options)
            msg = f":question: *{question}*\nOptions: {options_text}\n_Reply by creating `.claude/slack-answer.json` with `{{\"answer\": \"your_choice\"}}`_"
            payload = self._build_status_block(msg, "question")

        # Post the question
        self._post_message(payload)

        # Wait for answer via Socket Mode or file polling
        if use_socket:
            # Socket Mode: wait for button click via threading.Event
            self._pending_answer = threading.Event()
            self._last_answer = None
            answered = self._pending_answer.wait(timeout=effective_timeout * 60)
            if answered and self._last_answer:
                return self._last_answer
            return fallback
        else:
            # File-based polling: write pending question file and poll for answer
            question_data = {
                "question": question,
                "options": options,
                "asked_at": datetime.now(ZoneInfo("UTC")).isoformat(),
                "timeout_minutes": effective_timeout
            }

            try:
                with open(SLACK_QUESTION_PATH, "w") as f:
                    json.dump(question_data, f, indent=2)
            except IOError as e:
                print(f"[SLACK] Failed to write question file: {e}")
                return None

            # Poll for answer
            start_time = time.time()
            timeout_seconds = effective_timeout * 60

            while time.time() - start_time < timeout_seconds:
                try:
                    if os.path.exists(SLACK_ANSWER_PATH):
                        with open(SLACK_ANSWER_PATH, "r") as f:
                            answer_data = json.load(f)

                        answer = answer_data.get("answer", "")

                        # Clean up files
                        try:
                            os.remove(SLACK_ANSWER_PATH)
                        except OSError:
                            pass
                        try:
                            os.remove(SLACK_QUESTION_PATH)
                        except OSError:
                            pass

                        return answer

                except (IOError, json.JSONDecodeError) as e:
                    print(f"[SLACK] Error reading answer file: {e}")

                time.sleep(SLACK_POLL_INTERVAL_SECONDS)

            # Timeout - clean up and return fallback
            try:
                os.remove(SLACK_QUESTION_PATH)
            except OSError:
                pass

            return fallback

    def send_defect(self, title: str, description: str, file_path: str = "") -> None:
        """Send a defect report to Slack.

        Args:
            title: Defect title
            description: Defect description
            file_path: Optional file path where defect was found
        """
        if not self._should_notify("on_defect_found"):
            return

        msg = f":beetle: *Defect found:* {title}"
        if file_path:
            msg += f"\n`{file_path}`"
        if description:
            msg += f"\n{description}"

        self._post_message(self._build_status_block(msg, "error"))

    def send_idea(self, title: str, description: str) -> None:
        """Send a feature idea to Slack.

        Args:
            title: Idea title
            description: Idea description
        """
        if not self._should_notify("on_idea_found"):
            return

        msg = f":bulb: *Idea:* {title}"
        if description:
            msg += f"\n{description}"

        self._post_message(self._build_status_block(msg, "info"))

    def process_agent_messages(self, status: dict) -> None:
        """Process slack_messages from a task-status.json dict.

        Args:
            status: Task status dict potentially containing slack_messages field
        """
        messages = status.get("slack_messages", [])
        for msg in messages:
            msg_type = msg.get("type", "")
            title = msg.get("title", "")
            desc = msg.get("description", "")

            if msg_type == "defect":
                self.send_defect(title, desc, msg.get("file_path", ""))
            elif msg_type == "idea":
                self.send_idea(title, desc)

    def _load_last_read(self) -> str:
        """Load the last-read message timestamp from disk.

        Returns '0' if no prior state exists (will only process messages
        from this session forward by using current time on first poll).
        """
        try:
            with open(SLACK_LAST_READ_PATH, "r") as f:
                data = json.load(f)
            return data.get("last_ts", "0")
        except (IOError, json.JSONDecodeError):
            return "0"

    def _save_last_read(self, ts: str) -> None:
        """Persist the last-read timestamp to disk."""
        try:
            data = {"channel_id": self._channel_id, "last_ts": ts}
            with open(SLACK_LAST_READ_PATH, "w") as f:
                json.dump(data, f)
        except IOError as e:
            print(f"[SLACK] Failed to save last-read state: {e}")

    def poll_messages(self) -> list:
        """Fetch unread messages since last poll from the Slack channel.

        Uses conversations.history API with oldest parameter.
        Filters out bot messages. Updates last-read timestamp.
        Returns empty list if disabled, no new messages, or on error.
        """
        if not self._enabled or not self._bot_token or not self._channel_id:
            return []

        last_ts = self._load_last_read()
        # On first run, use current time to avoid processing history
        if last_ts == "0":
            import time as _time
            current_ts = str(_time.time())
            self._save_last_read(current_ts)
            return []

        try:
            params = urllib.parse.urlencode({
                "channel": self._channel_id,
                "oldest": last_ts,
                "limit": SLACK_INBOUND_POLL_LIMIT,
                "inclusive": "false"
            })
            url = f"https://slack.com/api/conversations.history?{params}"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {self._bot_token}"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())

            if not result.get("ok", False):
                print(f"[SLACK] conversations.history error: {result.get('error', 'unknown')}")
                return []

            messages = result.get("messages", [])
            if not messages:
                return []

            # Filter out bot messages (our own posts and other bots)
            human_messages = [
                m for m in messages
                if not m.get("bot_id") and m.get("subtype") is None
            ]

            # Update last-read to the newest message timestamp
            # messages are returned newest-first by the API
            newest_ts = messages[0].get("ts", last_ts)
            self._save_last_read(newest_ts)

            return human_messages

        except Exception as e:
            print(f"[SLACK] Failed to poll messages: {e}")
            return []

    def classify_message(self, text: str) -> tuple:
        """Classify a Slack message by its text content.

        Returns (classification, title, body) where:
        - classification: one of 'new_feature', 'new_defect', 'control_stop',
          'control_skip', 'info_request', 'question', 'acknowledgement'
        - title: extracted title (first line after prefix removal)
        - body: remaining text (lines after the first)
        """
        if not text or not text.strip():
            return ("acknowledgement", "", "")

        text = text.strip()
        lower = text.lower()
        lines = text.split("\n", 1)
        first_line = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""

        # Feature request
        for prefix in ("feature:", "enhancement:"):
            if lower.startswith(prefix):
                title = first_line[len(prefix):].strip()
                return ("new_feature", title, body)

        # Defect report
        for prefix in ("defect:", "bug:"):
            if lower.startswith(prefix):
                title = first_line[len(prefix):].strip()
                return ("new_defect", title, body)

        # Control commands
        if lower.startswith("stop") or lower.startswith("pause"):
            return ("control_stop", first_line, "")
        if lower.startswith("skip"):
            return ("control_skip", first_line, "")

        # Status request
        if lower.startswith("status"):
            return ("info_request", first_line, "")

        # Question detection
        question_words = ("what", "how", "where", "when", "why", "which", "can", "is", "are", "do", "does", "will", "should")
        if text.rstrip().endswith("?") or any(lower.startswith(w) for w in question_words):
            return ("question", first_line, body)

        return ("acknowledgement", first_line, body)

    def create_backlog_item(self, item_type: str, title: str, body: str,
                           user: str = "", ts: str = "") -> str:
        """Create a backlog markdown file from a Slack message.

        Args:
            item_type: 'feature' or 'defect'
            title: Item title
            body: Item description
            user: Slack user ID who sent the message
            ts: Message timestamp

        Returns:
            Created file path, or empty string on error
        """
        if item_type == "feature":
            backlog_dir = "docs/feature-backlog"
        elif item_type == "defect":
            backlog_dir = "docs/defect-backlog"
        else:
            return ""

        # Find next available number
        try:
            existing = [f for f in os.listdir(backlog_dir)
                       if f.endswith(".md") and f[0].isdigit()]
            numbers = []
            for f in existing:
                parts = f.split("-", 1)
                if parts[0].isdigit():
                    numbers.append(int(parts[0]))
            next_num = max(numbers) + 1 if numbers else 1
        except (OSError, ValueError):
            next_num = 1

        # Create slug from title
        slug = title.lower().strip()
        slug = slug.replace(" ", "-")
        # Remove non-alphanumeric chars except hyphens
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        slug = slug.strip("-")
        if not slug:
            slug = "untitled"

        filename = f"{next_num}-{slug}.md"
        filepath = os.path.join(backlog_dir, filename)

        # Build markdown content
        source_line = "Created from Slack message"
        if user:
            source_line += f" by {user}"
        if ts:
            source_line += f" at {ts}"
        source_line += "."

        content = (
            f"# {title}\n\n"
            f"## Status: Open\n\n"
            f"## Priority: Medium\n\n"
            f"## Summary\n\n"
            f"{body if body else title}\n\n"
            f"## Source\n\n"
            f"{source_line}\n"
        )

        try:
            os.makedirs(backlog_dir, exist_ok=True)
            with open(filepath, "w") as f:
                f.write(content)
            # Confirm in Slack
            item_label = "feature" if item_type == "feature" else "defect"
            self.send_status(
                f"*Created {item_label} backlog item:* {filename}",
                level="success"
            )
            return filepath
        except IOError as e:
            print(f"[SLACK] Failed to create backlog item: {e}")
            return ""

    def handle_control_command(self, command: str, classification: str) -> None:
        """Handle a control command from Slack.

        Args:
            command: The original message text
            classification: One of 'control_stop', 'control_skip', 'info_request'
        """
        if classification == "control_stop":
            # Write stop semaphore to signal graceful stop
            try:
                with open(STOP_SEMAPHORE_PATH, "w") as f:
                    f.write(f"stop requested via Slack: {command}\n")
                self.send_status(
                    "*Stop requested* via Slack. Pipeline will stop after current task.",
                    level="warning"
                )
            except IOError as e:
                print(f"[SLACK] Failed to write stop semaphore: {e}")

        elif classification == "control_skip":
            self.send_status(
                "*Skip requested* via Slack. (Note: skip is not yet implemented "
                "in the orchestrator. Use 'stop' to halt the pipeline.)",
                level="warning"
            )

        elif classification == "info_request":
            # Post a basic status response
            # Full pipeline state is not available inside SlackNotifier,
            # so we post what we can determine
            self.send_status(
                "*Pipeline Status*\nState: running\n"
                "_Use the terminal for detailed status._",
                level="info"
            )

    def answer_question(self, question: str) -> None:
        """Respond to a question from Slack.

        For now, acknowledges the question and suggests using the terminal
        for detailed answers. A future enhancement could use an LLM call.

        Args:
            question: The question text
        """
        self.send_status(
            f"*Question received:* {question}\n"
            "_Detailed answers are not yet available via Slack. "
            "Check the terminal session for full pipeline context._",
            level="info"
        )


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
    skip_smoke: bool = False,
    cli_args: Optional[argparse.Namespace] = None
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

    # Parse per-task validation configuration from plan meta
    validation_config = parse_validation_config(plan)

    # Parse model escalation configuration
    escalation_config = parse_escalation_config(plan)

    # Resolve the claude binary path
    global CLAUDE_CMD
    CLAUDE_CMD = resolve_claude_binary()

    # Clear any stale stop semaphore from a previous run
    clear_stop_semaphore()

    # Initialize usage tracking and budget guard before header prints
    usage_tracker = PlanUsageTracker()

    # Parse budget configuration from plan YAML + CLI overrides
    budget_config = parse_budget_config(plan, cli_args) if cli_args else BudgetConfig()
    budget_guard = BudgetGuard(budget_config, usage_tracker)

    # Initialize Slack notifier
    slack = SlackNotifier()

    print(f"=== Plan Orchestrator (PID {os.getpid()}) ===")
    print(f"Plan: {meta.get('name', 'Unknown')}")
    print(f"Claude binary: {' '.join(CLAUDE_CMD)}")
    print(f"Max attempts per task: {default_max_attempts}")
    print(f"Circuit breaker threshold: {circuit_breaker.threshold} consecutive failures")
    print(f"Parallel mode: {parallel}")
    print(f"Dry run: {dry_run}")
    print(f"Graceful stop: touch {STOP_SEMAPHORE_PATH}")
    if validation_config.enabled:
        print(f"Validation: enabled (run_after={validation_config.run_after}, "
              f"validators={validation_config.validators})")
    if budget_config.is_enabled:
        print(f"Budget: {budget_guard.format_status()}")
        print(f"  Ceiling: ${budget_config.quota_ceiling_usd:.2f}, Limit: ${budget_config.effective_limit_usd:.2f}")
    else:
        print("Budget: unlimited (no --quota-ceiling configured)")
    if escalation_config.enabled:
        print(f"Model escalation: enabled (escalate_after={escalation_config.escalate_after}, "
              f"max_model={escalation_config.max_model}, "
              f"validation_model={escalation_config.validation_model})")
    else:
        print("Model escalation: disabled (using agent default models)")

    # Slack notification setup
    if slack.is_enabled():
        print(f"Slack: enabled (webhook configured)")
        # Count total tasks across all sections
        total_tasks = sum(len(s.get("tasks", [])) for s in plan.get("sections", []))
        total_sections = len(plan.get("sections", []))
        slack.send_status(
            f"*Plan started:* {meta.get('name', 'Unknown')}\n"
            f"{total_tasks} tasks across {total_sections} phases",
            level="info"
        )
    else:
        print("Slack: disabled (no .claude/slack.local.yaml)")
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

        # Check budget before starting next task
        can_proceed, budget_reason = budget_guard.can_proceed()
        if not can_proceed:
            print(f"\n=== Budget limit reached ===")
            print(f"{budget_reason}")
            print(f"Plan paused. Resume with --resume-from when more budget is available.")

            # Send Slack notification for budget threshold
            slack.send_status(
                f"*Budget threshold reached*\n{budget_reason}",
                level="warning"
            )

            # Mark plan as paused
            plan.setdefault("meta", {})["status"] = "paused_quota"
            plan["meta"]["pause_reason"] = budget_reason
            if not dry_run:
                save_plan(plan_path, plan, commit=True,
                         commit_message="plan: Paused due to budget limit")
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

                # Mark all tasks as in_progress and compute effective models
                for section, task, _ in parallel_tasks:
                    task["status"] = "in_progress"
                    task["attempts"] = task.get("attempts", 0) + 1
                    task["last_attempt"] = datetime.now().isoformat()

                    # Compute effective model for this parallel task
                    par_agent_name = task.get("agent") or infer_agent_for_task(task) or FALLBACK_AGENT_NAME
                    par_agent_def = load_agent_definition(par_agent_name)
                    par_agent_model = par_agent_def.get("model", "") if par_agent_def else ""
                    par_attempt = task.get("attempts", 1)
                    par_effective_model = escalation_config.get_effective_model(par_agent_model, par_attempt)
                    task["model_used"] = par_effective_model

                    # Log model selection for parallel tasks
                    if escalation_config.enabled:
                        par_task_id = task.get("id")
                        if par_effective_model != par_agent_model:
                            print(f"Task {par_task_id} attempt {par_attempt}: escalating from {par_agent_model} to {par_effective_model}")
                        else:
                            print(f"Task {par_task_id} attempt {par_attempt}: using {par_effective_model}")
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
                            group_name, sibling_task_ids, dry_run,
                            model=task.get("model_used", "")
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

                # Validate successful parallel tasks sequentially
                if validation_config.enabled:
                    for section, task, _ in parallel_tasks:
                        task_id = task.get("id")
                        task_result = results.get(task_id)
                        if task_result and task_result.success:
                            validation_attempts = task.get("validation_attempts", 0)
                            if validation_attempts < validation_config.max_validation_attempts:
                                verdict = run_validation(
                                    task, section, task_result, validation_config, dry_run,
                                    escalation_config=escalation_config,
                                )
                                if verdict.verdict == "FAIL":
                                    print(f"  [{task_id}] VALIDATION FAIL")
                                    task_result = TaskResult(
                                        success=False,
                                        message=f"Validation failed: {', '.join(verdict.findings[:3])}",
                                        duration_seconds=task_result.duration_seconds
                                    )
                                    results[task_id] = task_result
                                    task["validation_findings"] = "\n".join(verdict.findings)
                                    task["validation_attempts"] = validation_attempts + 1
                                elif verdict.verdict == "WARN":
                                    print(f"  [{task_id}] VALIDATION WARN")
                                else:
                                    print(f"  [{task_id}] VALIDATION PASS")

                # Update task statuses in plan
                for section, task, _ in parallel_tasks:
                    task_id = task.get("id")
                    task_result = results.get(task_id)
                    if task_result and task_result.usage:
                        usage_tracker.record(task_id, task_result.usage, model=task.get("model_used", ""))
                        print(usage_tracker.format_summary_line(task_id))
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

                if budget_config.is_enabled:
                    print(budget_guard.format_status())

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

            # Send Slack notification before smoke tests
            slack.send_status(
                f"*Plan completed:* {meta.get('name', 'Unknown')}\n"
                f"Completed: {tasks_completed}, Failed: {tasks_failed}",
                level="success" if tasks_failed == 0 else "warning"
            )

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

            # Send Slack notification for task failure
            slack.send_status(
                f"*Task {task_id} failed* ({task.get('name', '')})\n"
                f"Failed after {max_attempts} attempts. Manual intervention required.",
                level="error"
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

        # Compute effective model for this task attempt
        agent_name = task.get("agent") or infer_agent_for_task(task) or FALLBACK_AGENT_NAME
        agent_def = load_agent_definition(agent_name)
        agent_model = agent_def.get("model", "") if agent_def else ""
        current_attempt = task.get("attempts", 1)
        effective_model = escalation_config.get_effective_model(agent_model, current_attempt)

        # Log model selection
        if escalation_config.enabled:
            if effective_model != agent_model:
                print(f"Task {task_id} attempt {current_attempt}: escalating from {agent_model} to {effective_model}")
            else:
                print(f"Task {task_id} attempt {current_attempt}: using {effective_model}")

        # Record model used for observability
        task["model_used"] = effective_model

        verbose_log("Executing Claude task...", "TASK")
        task_result = run_claude_task(prompt, dry_run=dry_run, model=effective_model)
        verbose_log(f"Task result: success={task_result.success}, message={task_result.message}", "TASK")

        print(f"Result: {'SUCCESS' if task_result.success else 'FAILED'}")
        print(f"Duration: {task_result.duration_seconds:.1f}s")
        print(f"Message: {task_result.message}")

        if task_result.usage:
            usage_tracker.record(task_id, task_result.usage, model=effective_model)
            print(usage_tracker.format_summary_line(task_id))

        if budget_config.is_enabled:
            print(budget_guard.format_status())

        # Process agent-initiated Slack messages from status file
        status = read_status_file()
        if status:
            slack.process_agent_messages(status)

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
            # Run validation if enabled
            if validation_config.enabled:
                validation_attempts = task.get("validation_attempts", 0)
                if validation_attempts < validation_config.max_validation_attempts:
                    verdict = run_validation(
                        task, section, task_result, validation_config, dry_run,
                        escalation_config=escalation_config,
                    )

                    if verdict.verdict == "FAIL":
                        print(f"[VALIDATION] FAIL - {len(verdict.findings)} findings")
                        for finding in verdict.findings:
                            print(f"  {finding}")
                        task["status"] = "pending"
                        task["validation_findings"] = "\n".join(verdict.findings)
                        task["validation_attempts"] = validation_attempts + 1
                        if not dry_run:
                            save_plan(plan_path, plan)
                        continue  # Retry the task

                    elif verdict.verdict == "WARN":
                        print(f"[VALIDATION] WARN - {len(verdict.findings)} findings (proceeding)")
                        for finding in verdict.findings:
                            print(f"  {finding}")
                        # Fall through to normal completion

                    else:
                        print(f"[VALIDATION] PASS")

            # Original completion logic
            task["status"] = "completed"
            task["completed_at"] = datetime.now().isoformat()
            task["result_message"] = task_result.message
            tasks_completed += 1
            circuit_breaker.record_success()

            # Send Slack notification for task success
            slack.send_status(
                f"*Task {task_id} completed* ({task.get('name', '')})\n"
                f"Attempt {task.get('attempts', 1)}, "
                f"{task_result.duration_seconds:.0f}s",
                level="success"
            )

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

    print(usage_tracker.format_final_summary(plan))

    print(f"\n=== Summary ===")
    print(f"Tasks completed: {tasks_completed}")
    print(f"Tasks failed: {tasks_failed}")

    report_path = usage_tracker.write_report(plan, plan_path)
    if report_path:
        print(f"[Usage report written to: {report_path}]")

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
    parser.add_argument(
        "--max-budget-pct",
        type=float,
        default=None,
        metavar="N",
        help="Maximum percentage of quota ceiling to use (default: 100, unlimited)"
    )
    parser.add_argument(
        "--quota-ceiling",
        type=float,
        default=None,
        metavar="N.NN",
        help="Weekly quota ceiling in USD (default: 0 = no budget enforcement)"
    )
    parser.add_argument(
        "--reserved-budget",
        type=float,
        default=None,
        metavar="N.NN",
        help="USD amount to reserve for interactive use (default: 0)"
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
        skip_smoke=args.skip_smoke,
        cli_args=args
    )


if __name__ == "__main__":
    main()
