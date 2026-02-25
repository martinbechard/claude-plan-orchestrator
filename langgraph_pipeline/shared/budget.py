# langgraph_pipeline/shared/budget.py
# Budget enforcement and usage tracking shared across pipeline scripts.
# Design: docs/plans/2026-02-25-02-extract-shared-modules-design.md

"""Budget guards, usage trackers, and related dataclasses for plan and session scopes."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from langgraph_pipeline.shared.paths import PLANS_DIR, TASK_LOG_DIR

# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_MAX_QUOTA_PERCENT = 100.0
DEFAULT_QUOTA_CEILING_USD = 0.0
DEFAULT_RESERVED_BUDGET_USD = 0.0

# Max chars from plan name used in report filenames
MAX_PLAN_NAME_LENGTH = 50

SCOPE_PLAN = "plan"
SCOPE_SESSION = "session"

# ─── Data Types ───────────────────────────────────────────────────────────────


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
            return float("inf")
        percent_limit = self.quota_ceiling_usd * (self.max_quota_percent / 100.0)
        if self.reserved_budget_usd > 0:
            reserve_limit = self.quota_ceiling_usd - self.reserved_budget_usd
            return min(percent_limit, reserve_limit)
        return percent_limit

    @property
    def is_enabled(self) -> bool:
        """Whether budget enforcement is active."""
        return self.quota_ceiling_usd > 0


# ─── Usage Tracker ────────────────────────────────────────────────────────────


class UsageTracker:
    """Accumulates usage across tasks (scope='plan') or work items (scope='session').

    scope='plan': Tracks per-task TaskUsage objects, supports plan structure
        queries, and writes detailed JSON reports. This is the tracker used by
        plan-orchestrator.py.

    scope='session': Tracks pipeline session totals by reading work-item report
        files. This is the tracker used by auto-pipeline.py.
    """

    def __init__(self, scope: str = SCOPE_PLAN) -> None:
        if scope not in (SCOPE_PLAN, SCOPE_SESSION):
            raise ValueError(f"Invalid scope: {scope!r}. Must be 'plan' or 'session'.")
        self.scope = scope

        # plan scope state
        self.task_usages: dict[str, TaskUsage] = {}
        self.task_models: dict[str, str] = {}

        # session scope state
        self.work_item_costs: list[dict] = []
        self.total_cost_usd: float = 0.0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

    # ─── Plan scope methods ───────────────────────────────────────────────────

    def record(self, task_id: str, usage: TaskUsage, model: str = "") -> None:
        """Record usage for a completed task. (plan scope only)"""
        self.task_usages[task_id] = usage
        self.task_models[task_id] = model

    def get_section_usage(self, plan: dict, section_id: str) -> TaskUsage:
        """Aggregate usage for all tasks in a given section. (plan scope only)"""
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
        """Aggregate usage across all recorded tasks. (plan scope only)"""
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
        """Calculate overall cache hit rate. (plan scope only)

        Cache hit rate measures what fraction of input context was served
        from cache vs. freshly processed. Higher means lower cost per token.
        """
        total = self.get_total_usage()
        denom = total.cache_read_tokens + total.input_tokens
        return total.cache_read_tokens / denom if denom > 0 else 0.0

    def format_summary_line(self, task_id: str) -> str:
        """Format a one-line usage summary for a task. (plan scope only)"""
        u = self.task_usages.get(task_id)
        if not u:
            return ""
        total = self.get_total_usage()
        cache_denom = u.cache_read_tokens + u.input_tokens
        cache_pct = (u.cache_read_tokens / cache_denom * 100) if cache_denom > 0 else 0
        model = self.task_models.get(task_id, "")
        model_str = f" [{model}]" if model else ""
        return (
            f"[Usage] Task {task_id}{model_str}: ~${u.total_cost_usd:.4f} | "
            f"{u.input_tokens:,} in / {u.output_tokens:,} out / "
            f"{u.cache_read_tokens:,} cached ({cache_pct:.0f}% cache hit) | "
            f"Running: ~${total.total_cost_usd:.4f}"
        )

    def format_final_summary(self, plan: dict) -> str:
        """Format the final usage summary printed after all tasks complete. (plan scope only)"""
        total = self.get_total_usage()
        cache_rate = self.get_cache_hit_rate()
        lines = [
            "\n=== Usage Summary (API-Equivalent Estimates) ===",
            "(These are API-equivalent costs reported by Claude CLI, not actual subscription charges)",
            f"Total API-equivalent cost: ~${total.total_cost_usd:.4f}",
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
                lines.append(f"  {sname}: ~${su.total_cost_usd:.4f} ({task_count} tasks)")
        return "\n".join(lines)

    def write_report(self, plan: dict, plan_path: str) -> Optional[Path]:
        """Write a usage report JSON file alongside the plan logs. (plan scope only)

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
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        return report_path

    # ─── Session scope methods ────────────────────────────────────────────────

    def record_from_report(self, report_path: str, work_item_name: str) -> None:
        """Read a usage report JSON and accumulate totals. (session scope only)"""
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
            print(f"[Usage] {work_item_name}: ~${cost:.4f} (API-equivalent)")
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            pass  # Report not available, skip silently

    def format_session_summary(self) -> str:
        """Format session-level usage summary. (session scope only)"""
        lines = ["\n=== Pipeline Session Usage (API-Equivalent Estimates) ==="]
        lines.append(
            "(These are API-equivalent costs reported by Claude CLI, "
            "not actual subscription charges)"
        )
        lines.append(f"Total API-equivalent cost: ~${self.total_cost_usd:.4f}")
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
        """Write a session summary JSON file. (session scope only)"""
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


# ─── Budget Guard ─────────────────────────────────────────────────────────────


class BudgetGuard:
    """Checks cumulative cost against budget limits before each task.

    Wraps a UsageTracker to read current spending. Does not maintain
    its own cost counter; queries the tracker directly to avoid duplicate state.

    The can_proceed() method accepts an optional explicit cost_usd parameter.
    When provided, that value is used instead of querying the tracker. This
    supports both the plan-orchestrator pattern (no argument, tracker-driven)
    and the auto-pipeline pattern (explicit session cost passed in).
    """

    def __init__(self, config: BudgetConfig, usage_tracker: UsageTracker) -> None:
        self.config = config
        self.usage_tracker = usage_tracker

    def _current_cost_usd(self, cost_usd: Optional[float]) -> float:
        """Resolve the current cost: use explicit value if given, else read from tracker."""
        if cost_usd is not None:
            return cost_usd
        if self.usage_tracker.scope == SCOPE_SESSION:
            return self.usage_tracker.total_cost_usd
        return self.usage_tracker.get_total_usage().total_cost_usd

    def can_proceed(self, cost_usd: Optional[float] = None) -> tuple[bool, str]:
        """Check if budget allows another task.

        Args:
            cost_usd: Optional explicit current spend in USD. If None, the
                current spend is read from the usage tracker.

        Returns:
            (can_proceed, reason_if_not) tuple.
        """
        if not self.config.is_enabled:
            return (True, "")
        spent = self._current_cost_usd(cost_usd)
        limit = self.config.effective_limit_usd
        if spent >= limit:
            pct = (
                (spent / self.config.quota_ceiling_usd * 100)
                if self.config.quota_ceiling_usd > 0
                else 0
            )
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
        spent = self._current_cost_usd(None)
        return spent / self.config.quota_ceiling_usd * 100

    def format_status(self) -> str:
        """Format current budget status for display."""
        if not self.config.is_enabled:
            return "[Budget: unlimited]"
        spent = self._current_cost_usd(None)
        limit = self.config.effective_limit_usd
        pct = self.get_usage_percent()
        return f"[Budget: ${spent:.4f} / ${limit:.4f} ({pct:.1f}% of ceiling)]"
