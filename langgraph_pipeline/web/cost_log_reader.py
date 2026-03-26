# langgraph_pipeline/web/cost_log_reader.py
# Reads execution-cost data from SQLite DB or JSON logs and returns pre-aggregated data for the /analysis page.
# Design: docs/plans/2026-03-25-16-tool-call-timing-and-cost-analysis-ui-design.md

"""CostLogReader — loads cost data from SQLite DB (primary) or JSON files (fallback).

Public API:
    CostLogReader().load_all() -> CostData
    svg_bar_chart(labels, values, width, bar_height, title) -> str
"""

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from langgraph_pipeline.web.proxy import DB_DEFAULT_PATH

# ─── Constants ────────────────────────────────────────────────────────────────

_COST_LOGS_DIR = Path("docs/reports/execution-costs")
TOP_FILES_LIMIT = 20

SVG_TEXT_OFFSET_X = 5
SVG_LABEL_MAX_CHARS = 40
SVG_LABEL_TRUNCATE_SUFFIX = "…"
SVG_BAR_LABEL_PADDING = 160
SVG_VALUE_LABEL_PADDING = 80
SVG_FONT_SIZE = 12
SVG_BAR_GAP = 4
SVG_CHART_PADDING_TOP = 30
SVG_CHART_PADDING_BOTTOM = 10
SVG_TITLE_FONT_SIZE = 13
SVG_EMPTY_HEIGHT = 40
SVG_EMPTY_TEXT_Y = 20
MIN_BAR_WIDTH = 1


# ─── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class TaskCost:
    """Per-task cost breakdown from a single agent run."""

    task_id: str
    agent_type: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_s: float


@dataclass
class ItemCost:
    """Aggregated cost metrics for a single pipeline item (feature or defect)."""

    item_slug: str
    item_type: str
    agent_types: list[str]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    num_tasks: int
    num_wasted_reads: int
    tasks: list[TaskCost] = field(default_factory=list)


@dataclass
class WastedRead:
    """A file that was read redundantly across 2+ distinct tasks in one item."""

    item_slug: str
    file_path: str
    task_count: int


@dataclass
class CostData:
    """All pre-aggregated cost data for the /analysis page."""

    top_files: list[tuple[str, int]]
    cost_by_agent: dict[str, int]
    cost_by_item: list[ItemCost]
    wasted_reads: list[WastedRead]
    has_data: bool = False


# ─── Reader ───────────────────────────────────────────────────────────────────


_EMPTY_COST_DATA = CostData(
    top_files=[],
    cost_by_agent={},
    cost_by_item=[],
    wasted_reads=[],
    has_data=False,
)


class CostLogReader:
    """Reads and aggregates execution-cost data on demand.

    Tries the SQLite DB (cost_tasks table) first. Falls back to JSON file glob
    if the DB does not exist or the cost_tasks table is absent.
    """

    def __init__(
        self,
        logs_dir: Optional[Path] = None,
        db_path: Optional[str] = None,
    ) -> None:
        self._logs_dir = logs_dir or _COST_LOGS_DIR
        self._db_path: str = db_path if db_path is not None else DB_DEFAULT_PATH

    def load_all(self) -> CostData:
        """Return aggregated cost data from DB or JSON files.

        Tries the SQLite DB first. Falls back to JSON files if the DB file is
        absent or the cost_tasks table does not exist.

        Returns:
            CostData with pre-computed aggregations. has_data is False when no
            cost records are found in either source.
        """
        db_result = self._try_load_from_db()
        if db_result is not None:
            return db_result
        return self._load_from_json()

    # ─── DB path ──────────────────────────────────────────────────────────────

    def _try_load_from_db(self) -> Optional[CostData]:
        """Query cost_tasks from SQLite. Returns None if DB absent or table missing."""
        db_path = Path(self._db_path).expanduser()
        if not db_path.exists():
            return None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                table_exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cost_tasks'"
                ).fetchone()
                if table_exists is None:
                    return None
                rows = conn.execute(
                    "SELECT * FROM cost_tasks ORDER BY item_slug, id"
                ).fetchall()
            finally:
                conn.close()
        except sqlite3.Error:
            return None

        if not rows:
            return _EMPTY_COST_DATA

        item_types: dict[str, str] = {}
        raw_tasks_by_slug: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            slug: str = row["item_slug"]
            if slug not in item_types:
                item_types[slug] = row["item_type"]
            tool_calls: list[dict] = _deserialise_tool_calls(row["tool_calls_json"])
            raw_tasks_by_slug[slug].append(
                {
                    "task_id": row["task_id"],
                    "agent_type": row["agent_type"],
                    "model": row["model"],
                    "input_tokens": row["input_tokens"],
                    "output_tokens": row["output_tokens"],
                    "cost_usd": row["cost_usd"],
                    "duration_s": row["duration_s"],
                    "tool_calls": tool_calls,
                }
            )

        return self._aggregate(item_types, dict(raw_tasks_by_slug))

    # ─── JSON fallback path ────────────────────────────────────────────────────

    def _load_from_json(self) -> CostData:
        """Load cost data from JSON log files."""
        json_files = self._find_json_files()
        if not json_files:
            return _EMPTY_COST_DATA

        item_types: dict[str, str] = {}
        raw_tasks_by_slug: dict[str, list[dict]] = {}
        for path in json_files:
            data = self._parse_file(path)
            if data is None:
                continue
            item_slug: str = data.get("item_slug", "")
            item_type: str = data.get("item_type", "")
            raw_tasks: list[dict] = data.get("tasks", [])
            if not item_slug or not isinstance(raw_tasks, list):
                continue
            item_types[item_slug] = item_type
            raw_tasks_by_slug[item_slug] = raw_tasks

        return self._aggregate(item_types, raw_tasks_by_slug)

    # ─── Aggregation ──────────────────────────────────────────────────────────

    def _aggregate(
        self,
        item_types: dict[str, str],
        raw_tasks_by_slug: dict[str, list[dict]],
    ) -> CostData:
        """Build CostData from a mapping of item_slug -> (item_type, raw_tasks)."""
        if not raw_tasks_by_slug:
            return _EMPTY_COST_DATA

        read_bytes_by_file: dict[str, int] = defaultdict(int)
        tokens_by_agent: dict[str, int] = defaultdict(int)
        item_costs: list[ItemCost] = []

        for item_slug, raw_tasks in raw_tasks_by_slug.items():
            item_type = item_types.get(item_slug, "")
            item_cost = self._build_item_cost(
                item_slug, item_type, raw_tasks, read_bytes_by_file, tokens_by_agent
            )
            item_costs.append(item_cost)

        wasted_count_by_slug, all_wasted = _compute_wasted_reads(raw_tasks_by_slug)
        for item in item_costs:
            item.num_wasted_reads = wasted_count_by_slug.get(item.item_slug, 0)

        item_costs.sort(key=lambda ic: ic.cost_usd, reverse=True)
        top_files = _top_n_by_value(read_bytes_by_file, TOP_FILES_LIMIT)

        return CostData(
            top_files=top_files,
            cost_by_agent=dict(tokens_by_agent),
            cost_by_item=item_costs,
            wasted_reads=all_wasted,
            has_data=True,
        )

    def _find_json_files(self) -> list[Path]:
        """Return all *.json paths in the logs directory, sorted by name."""
        if not self._logs_dir.exists():
            return []
        return sorted(self._logs_dir.glob("*.json"))

    def _parse_file(self, path: Path) -> Optional[dict]:
        """Load a single JSON log file, returning None on parse errors."""
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _build_item_cost(
        self,
        item_slug: str,
        item_type: str,
        raw_tasks: list[dict],
        read_bytes_by_file: dict[str, int],
        tokens_by_agent: dict[str, int],
    ) -> ItemCost:
        """Aggregate one item's raw task list into an ItemCost.

        Updates read_bytes_by_file and tokens_by_agent in-place as a side effect.
        """
        task_costs: list[TaskCost] = []
        agent_type_set: set[str] = set()

        for raw_task in raw_tasks:
            task_cost = _parse_task(raw_task)
            if task_cost is None:
                continue
            task_costs.append(task_cost)
            agent_type_set.add(task_cost.agent_type)
            tokens_by_agent[task_cost.agent_type] += (
                task_cost.input_tokens + task_cost.output_tokens
            )
            _accumulate_read_bytes(raw_task, read_bytes_by_file)

        return ItemCost(
            item_slug=item_slug,
            item_type=item_type,
            agent_types=sorted(agent_type_set),
            input_tokens=sum(tc.input_tokens for tc in task_costs),
            output_tokens=sum(tc.output_tokens for tc in task_costs),
            cost_usd=sum(tc.cost_usd for tc in task_costs),
            num_tasks=len(task_costs),
            num_wasted_reads=0,  # filled in by the second pass in _aggregate
            tasks=task_costs,
        )


# ─── Module-level helpers ─────────────────────────────────────────────────────


def _deserialise_tool_calls(tool_calls_json: Optional[str]) -> list[dict]:
    """Parse the tool_calls_json column; returns an empty list on any error."""
    if not tool_calls_json:
        return []
    try:
        parsed = json.loads(tool_calls_json)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _parse_task(raw: dict) -> Optional[TaskCost]:
    """Parse one task dict from a cost log file into a TaskCost."""
    try:
        return TaskCost(
            task_id=str(raw.get("task_id", "")),
            agent_type=str(raw.get("agent_type", "")),
            model=str(raw.get("model", "")),
            input_tokens=int(raw.get("input_tokens", 0)),
            output_tokens=int(raw.get("output_tokens", 0)),
            cost_usd=float(raw.get("cost_usd", 0.0)),
            duration_s=float(raw.get("duration_s", 0.0)),
        )
    except (TypeError, ValueError):
        return None


def _accumulate_read_bytes(raw_task: dict, acc: dict[str, int]) -> None:
    """Add result_bytes from Read tool calls in this task to the accumulator."""
    tool_calls: list[dict] = raw_task.get("tool_calls", [])
    if not isinstance(tool_calls, list):
        return
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        if call.get("tool") == "Read":
            file_path: str = call.get("file_path", "")
            result_bytes: int = int(call.get("result_bytes", 0))
            if file_path:
                acc[file_path] += result_bytes


def _top_n_by_value(mapping: dict[str, int], n: int) -> list[tuple[str, int]]:
    """Return the top-n (key, value) pairs sorted by value descending."""
    return sorted(mapping.items(), key=lambda kv: kv[1], reverse=True)[:n]


def _compute_wasted_reads(
    data_by_slug: dict[str, list[dict]],
) -> tuple[dict[str, int], list[WastedRead]]:
    """Detect files read in 2+ distinct tasks within each item.

    A file is 'wasted' if the same file_path appears in Read tool_calls across
    at least two distinct task_ids within the same item_slug.

    Args:
        data_by_slug: Maps item_slug -> list of raw task dicts.

    Returns:
        A tuple of:
          - wasted_count_by_slug: maps item_slug -> count of distinct wasted paths
          - all_wasted: list of WastedRead entries sorted by task_count descending
    """
    wasted_count_by_slug: dict[str, int] = {}
    all_wasted: list[WastedRead] = []

    for item_slug, raw_tasks in data_by_slug.items():
        tasks_per_file: dict[str, set[str]] = defaultdict(set)

        for raw_task in raw_tasks:
            task_id = str(raw_task.get("task_id", ""))
            tool_calls: list[dict] = raw_task.get("tool_calls", [])
            if not isinstance(tool_calls, list):
                continue
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                if call.get("tool") == "Read":
                    file_path: str = call.get("file_path", "")
                    if file_path:
                        tasks_per_file[file_path].add(task_id)

        count = 0
        for file_path, task_ids in tasks_per_file.items():
            if len(task_ids) >= 2:
                all_wasted.append(
                    WastedRead(
                        item_slug=item_slug,
                        file_path=file_path,
                        task_count=len(task_ids),
                    )
                )
                count += 1

        wasted_count_by_slug[item_slug] = count

    all_wasted.sort(key=lambda wr: wr.task_count, reverse=True)
    return wasted_count_by_slug, all_wasted


# ─── SVG Bar Chart ────────────────────────────────────────────────────────────


def _short_path(path: str) -> str:
    """Return the last 3 path components joined by '/'."""
    parts = Path(path).parts
    return "/".join(parts[-3:]) if len(parts) >= 3 else path


def _truncate_label(label: str, max_chars: int = SVG_LABEL_MAX_CHARS) -> str:
    """Shorten a label to max_chars, appending an ellipsis if truncated."""
    if len(label) <= max_chars:
        return label
    return SVG_LABEL_TRUNCATE_SUFFIX + label[-max_chars:]


def svg_bar_chart(
    labels: list[str],
    values: list[float],
    width: int,
    bar_height: int,
    title: str,
    value_formatter: callable = lambda v: f"${v:.2f}",
) -> str:
    """Render a horizontal SVG bar chart as an inline HTML string.

    Each bar represents one label/value pair. The bar width is proportional to
    the maximum value. The full label is stored in the SVG <title> element for
    tooltip display; the visible label is truncated to the last 3 path components.

    Args:
        labels: Ordered list of string labels (e.g. file paths or agent names).
        values: Ordered list of numeric values corresponding to each label.
        width: Total SVG width in pixels.
        bar_height: Height of each bar in pixels.
        title: Chart title shown above the bars.
        value_formatter: Optional callable to format each value as a string.
            Defaults to two-decimal dollar formatting (e.g. "$1.23").

    Returns:
        An inline SVG string starting with '<svg'.
    """
    if not labels or not values or len(labels) != len(values):
        return (
            f'<svg width="{width}" height="{SVG_EMPTY_HEIGHT}" xmlns="http://www.w3.org/2000/svg">'
            f'<text x="10" y="{SVG_EMPTY_TEXT_Y}" font-size="{SVG_FONT_SIZE}" fill="#888">'
            f"No data</text>"
            f"</svg>"
        )

    max_val = max(values)
    bar_area_width = width - SVG_BAR_LABEL_PADDING - SVG_VALUE_LABEL_PADDING
    row_height = bar_height + SVG_BAR_GAP
    chart_height = SVG_CHART_PADDING_TOP + row_height * len(labels) + SVG_CHART_PADDING_BOTTOM

    lines: list[str] = [
        f'<svg width="{width}" height="{chart_height}" xmlns="http://www.w3.org/2000/svg"'
        f' aria-label="{title}">',
        f'<text x="0" y="16" font-size="{SVG_TITLE_FONT_SIZE}" font-weight="bold"'
        f' fill="#333">{title}</text>',
    ]

    for i, (label, value) in enumerate(zip(labels, values)):
        y = SVG_CHART_PADDING_TOP + i * row_height
        bar_width = max(MIN_BAR_WIDTH, int(bar_area_width * value / max_val))
        short = _short_path(label)
        display_label = _truncate_label(short)

        lines.append(
            f'<g transform="translate(0,{y})">'
            f"<title>{label}</title>"
            f'<text x="{SVG_BAR_LABEL_PADDING - SVG_TEXT_OFFSET_X}" y="{bar_height - 2}"'
            f' font-size="{SVG_FONT_SIZE}" text-anchor="end" fill="#555">{display_label}</text>'
            f'<rect x="{SVG_BAR_LABEL_PADDING}" y="0" width="{bar_width}"'
            f' height="{bar_height}" fill="#4e79a7" rx="2"/>'
            f'<text x="{SVG_BAR_LABEL_PADDING + bar_width + SVG_TEXT_OFFSET_X}"'
            f' y="{bar_height - 2}" font-size="{SVG_FONT_SIZE}" fill="#333">{value_formatter(value)}</text>'
            f"</g>"
        )

    lines.append("</svg>")
    return "\n".join(lines)
