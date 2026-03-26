# langgraph_pipeline/shared/item_trace.py
# ItemTraceWriter — writes a per-item Markdown trace file recording each task execution.
# Design: docs/plans/2026-03-26-43-capture-agent-traces-per-item-for-review-design.md

"""ItemTraceWriter appends a Markdown section to docs/reports/item-traces/<slug>.md
after each task and finalizes the file with a summary table on archival."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph_pipeline.shared.claude_cli import ToolCallRecord

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

ITEM_TRACES_DIR = Path("docs/reports/item-traces")
SKILL_TOOL_NAME = "Skill"
COST_DISPLAY_FORMAT = "${:.4f}"
TOKEN_GROUP_SIZE = 3  # digits per group when formatting token counts


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _format_tokens(count: int) -> str:
    """Return token count with space-separated thousands groups (e.g. '8 420')."""
    s = str(count)
    groups: list[str] = []
    while len(s) > TOKEN_GROUP_SIZE:
        groups.append(s[-TOKEN_GROUP_SIZE:])
        s = s[:-TOKEN_GROUP_SIZE]
    groups.append(s)
    return " ".join(reversed(groups))


def _extract_skills(tool_calls: "list[ToolCallRecord]") -> list[str]:
    """Return the list of skill names invoked during a task."""
    return [
        tc["tool_input"].get("skill", "")
        for tc in tool_calls
        if tc.get("tool_name") == SKILL_TOOL_NAME
    ]


# ─── ItemTraceWriter ─────────────────────────────────────────────────────────


class TaskTraceRecord:
    """Holds the data captured for a single task execution."""

    def __init__(
        self,
        task_id: str,
        task_name: str,
        agent: str,
        model: str,
        skills: list[str],
        cost_usd: float,
        input_tokens: int,
        output_tokens: int,
        status: str,
        duration_s: float,
    ) -> None:
        self.task_id = task_id
        self.task_name = task_name
        self.agent = agent
        self.model = model
        self.skills = skills
        self.cost_usd = cost_usd
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.status = status
        self.duration_s = duration_s


class ItemTraceWriter:
    """Writes a Markdown trace file to docs/reports/item-traces/<slug>.md.

    record_task() appends a section after each task completes.
    finalize() appends the summary table and outcome on archival.
    The trace directory is created on first write if it does not exist.
    """

    def __init__(self, slug: str, item_path: str) -> None:
        self._slug = slug
        self._item_path = item_path
        self._trace_path = ITEM_TRACES_DIR / f"{slug}.md"
        self._records: list[TaskTraceRecord] = []
        self._initialized = False

    # ── Public API ────────────────────────────────────────────────────────────

    def record_task(
        self,
        task_id: str,
        task_name: str,
        agent: str,
        model: str,
        tool_calls: "list[ToolCallRecord]",
        cost_usd: float,
        input_tokens: int,
        output_tokens: int,
        status: str,
        duration_s: float,
    ) -> None:
        """Append a task execution section to the trace file."""
        skills = _extract_skills(tool_calls)
        record = TaskTraceRecord(
            task_id=task_id,
            task_name=task_name,
            agent=agent,
            model=model,
            skills=skills,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            status=status,
            duration_s=duration_s,
        )
        self._records.append(record)
        self._write_task_section(record)

    def finalize(self, outcome: str) -> None:
        """Append the summary table and outcome to the trace file."""
        if not self._records:
            logger.warning("finalize called on ItemTraceWriter with no recorded tasks: slug=%s", self._slug)
            return
        content = self._build_summary(outcome)
        self._append(content)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _ensure_header(self) -> None:
        """Write the file header on the first call."""
        if self._initialized:
            return
        ITEM_TRACES_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        header = (
            f"# Agent Trace: {self._slug}\n\n"
            f"**Item:** {self._item_path}\n"
            f"**Generated:** {timestamp}\n\n"
            "---\n\n"
        )
        self._trace_path.write_text(header, encoding="utf-8")
        self._initialized = True

    def _append(self, content: str) -> None:
        """Append content to the trace file, initializing header if needed."""
        self._ensure_header()
        with self._trace_path.open("a", encoding="utf-8") as fh:
            fh.write(content)

    def _write_task_section(self, record: TaskTraceRecord) -> None:
        """Format and append a single task section."""
        skills_display = ", ".join(record.skills) if record.skills else "_(none)_"
        cost_display = COST_DISPLAY_FORMAT.format(record.cost_usd)
        section = (
            f"## Task {record.task_id} \u2014 {record.task_name}\n\n"
            f"- **Agent:** {record.agent}\n"
            f"- **Model:** {record.model}\n"
            f"- **Status:** {record.status}\n"
            f"- **Duration:** {record.duration_s:.1f} s\n"
            f"- **Cost:** {cost_display}"
            f"  |  Input: {_format_tokens(record.input_tokens)} tok"
            f"  |  Output: {_format_tokens(record.output_tokens)} tok\n"
            f"- **Skills invoked:** {skills_display}\n\n"
            "---\n\n"
        )
        self._append(section)

    def _build_summary(self, outcome: str) -> str:
        """Return the summary table Markdown block."""
        rows = "\n".join(
            f"| {r.task_id} | {r.agent} | {r.model} | "
            f"{', '.join(r.skills) if r.skills else ''} | "
            f"{r.status} | {COST_DISPLAY_FORMAT.format(r.cost_usd)} |"
            for r in self._records
        )
        return (
            "## Summary\n\n"
            "| Task | Agent | Model | Skills | Status | Cost |\n"
            "|------|-------|-------|--------|--------|------|\n"
            f"{rows}\n\n"
            f"**Outcome:** {outcome}\n"
        )
