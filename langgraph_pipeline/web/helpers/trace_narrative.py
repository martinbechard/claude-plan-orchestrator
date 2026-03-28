# langgraph_pipeline/web/helpers/trace_narrative.py
# Maps raw trace rows to an item-centric execution narrative view model.
# Design: docs/plans/2026-03-28-69-traces-page-complete-redesign-design.md

"""Build ExecutionView from raw TracingProxy run dicts.

Public API:
    build_execution_view(run, children, grandchildren) -> ExecutionView
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

# Maps run name substrings (lower-cased) to canonical phase labels.
# Checked in order; first match wins.  More-specific patterns must come first.
_PHASE_PATTERNS: list[tuple[str, str]] = [
    ("intake", "Intake"),
    ("execute_plan", "Execution"),
    ("execute", "Execution"),
    ("plan_creation", "Planning"),
    ("plan", "Planning"),
    ("validate", "Validation"),
    ("verification", "Validation"),
    ("verify_fix", "Verification"),
    ("verify", "Verification"),
    ("archive", "Archival"),
]

_PHASE_ORDER: list[str] = [
    "Intake",
    "Planning",
    "Execution",
    "Validation",
    "Verification",
    "Archival",
]

_UNKNOWN_PHASE = "Unknown"

# Tool name -> human verb used in activity summaries.
_TOOL_VERB: dict[str, str] = {
    "Read": "read",
    "Edit": "edited",
    "Write": "wrote",
    "Bash": "ran bash",
    "Grep": "searched",
    "Glob": "globbed",
    "TodoWrite": "updated todos",
    "Agent": "dispatched agent",
    "WebSearch": "searched web",
    "WebFetch": "fetched URL",
}

_COST_DISPLAY_FORMAT = "${:.4f}"
_DURATION_MINUTE_THRESHOLD = 60
_DURATION_SECONDS_FORMAT = "{:.2f}s"
_DURATION_MINUTES_FORMAT = "{}m {:02d}s"
_DURATION_UNKNOWN = "—"

# Runs with no end_time but whose children all ended more than this many minutes
# ago are treated as completed rather than still-running.
_STATUS_STALE_THRESHOLD_MINUTES = 5


# ─── Data Types ───────────────────────────────────────────────────────────────


@dataclass
class PhaseArtifact:
    """A linkable output artifact produced during a pipeline phase."""

    label: str
    path: str  # filesystem path or URL


@dataclass
class PhaseView:
    """Item-centric summary of a single pipeline phase."""

    phase_name: str
    run_name: str
    run_id: str
    agent: str
    status: str              # "success" | "error" | "running" | "unknown"
    duration: str            # human-readable, e.g. "12.34s"
    cost: str                # human-readable, e.g. "$0.0123"
    activity_summary: str    # e.g. "Read 5 files, edited 2, ran 8 bash commands"
    artifacts: list[PhaseArtifact] = field(default_factory=list)


@dataclass
class ExecutionView:
    """Full item-centric execution narrative for one pipeline run."""

    item_slug: str
    total_duration: str
    total_cost: str
    phases: list[PhaseView]
    overall_status: str = "unknown"  # "completed" | "running" | "error" | "unknown"


# ─── Public API ───────────────────────────────────────────────────────────────


def build_execution_view(
    run: dict,
    children: list[dict],
    grandchildren: dict[str, list[dict]],
) -> ExecutionView:
    """Build an ExecutionView from raw TracingProxy run dicts.

    Args:
        run: Root run dict (the top-level pipeline run).
        children: Direct child run dicts, ordered by start_time.
        grandchildren: Maps child run_id -> list of grandchild run dicts.

    Returns:
        ExecutionView with merged phases ordered by pipeline stage.
    """
    meta = _parse_json(run.get("metadata_json"))
    item_slug = meta.get("slug") or meta.get("item_slug") or ""

    # Fallback: scan children metadata if root has no slug or only "LangGraph"
    if not item_slug or item_slug == "LangGraph":
        item_slug = _scan_children_for_slug(children) or run.get("name", "")

    # Group children by phase name to merge duplicates (P3, P13)
    phase_groups: dict[str, dict] = {}
    for child in children:
        child_id = child.get("run_id", "")
        child_grandchildren = grandchildren.get(child_id, [])
        phase_name = _classify_phase(child.get("name", ""))
        if phase_name not in phase_groups:
            phase_groups[phase_name] = {"children": [], "grandchildren": []}
        phase_groups[phase_name]["children"].append(child)
        phase_groups[phase_name]["grandchildren"].extend(child_grandchildren)

    phases: list[PhaseView] = []
    for phase_name, group in phase_groups.items():
        group_children = group["children"]
        group_grandchildren = group["grandchildren"]
        if len(group_children) == 1:
            phase = _build_phase_view(group_children[0], group_grandchildren)
        else:
            phase = _build_merged_phase_view(phase_name, group_children, group_grandchildren)
        phases.append(phase)

    phases.sort(key=_phase_sort_key)

    # Total duration from child span (P11, P12); fall back to run timestamps
    total_duration = _duration_from_children(children)
    if total_duration == _DURATION_UNKNOWN:
        total_duration = _format_duration(run.get("start_time"), run.get("end_time"))

    # Cost: prefer root metadata; aggregate from descendants when absent (P4)
    total_cost = _extract_cost_display(meta)
    if not total_cost:
        all_gc = [gc for gcs in grandchildren.values() for gc in gcs]
        total_cost = _aggregate_cost_display(children + all_gc)

    overall_status = _compute_overall_status(run, children)

    return ExecutionView(
        item_slug=item_slug,
        total_duration=total_duration,
        total_cost=total_cost,
        phases=phases,
        overall_status=overall_status,
    )


# ─── Phase building ───────────────────────────────────────────────────────────


def _build_phase_view(child: dict, grandchildren: list[dict]) -> PhaseView:
    """Build a PhaseView for one child run and its grandchildren."""
    run_name = child.get("name", "")
    run_id = child.get("run_id", "")
    phase_name = _classify_phase(run_name)
    agent = _extract_agent(child)
    status = _extract_status(child)
    duration = _format_duration(child.get("start_time"), child.get("end_time"))
    cost = _aggregate_cost_display([child] + grandchildren)
    tool_counts = _count_tools(child, grandchildren)
    activity_summary = _format_activity_summary(tool_counts)
    artifacts = _extract_artifacts(child, grandchildren)

    return PhaseView(
        phase_name=phase_name,
        run_name=run_name,
        run_id=run_id,
        agent=agent,
        status=status,
        duration=duration,
        cost=cost,
        activity_summary=activity_summary,
        artifacts=artifacts,
    )


def _build_merged_phase_view(
    phase_name: str,
    children: list[dict],
    all_grandchildren: list[dict],
) -> PhaseView:
    """Merge multiple child runs with the same phase name into one PhaseView.

    Uses earliest start_time and latest end_time to compute real duration.
    Costs and tool counts are summed across all children and grandchildren.
    """
    sorted_children = sorted(children, key=lambda c: c.get("start_time") or "")
    primary = sorted_children[0]
    run_id = primary.get("run_id", "")
    agent = _extract_agent(primary)

    statuses = [_extract_status(c) for c in children]
    if "error" in statuses:
        status = "error"
    elif "running" in statuses:
        status = "running"
    else:
        status = "success"

    starts = [c.get("start_time") for c in children]
    ends = [c.get("end_time") for c in children]
    earliest_start = min((s for s in starts if s), default=None)
    latest_end = max((e for e in ends if e), default=None)
    duration = _format_duration(earliest_start, latest_end)

    cost = _aggregate_cost_display(children + all_grandchildren)

    tool_counts: dict[str, int] = {}
    for run in children + all_grandchildren:
        _accumulate_tool_counts(run, tool_counts)
    activity_summary = _format_activity_summary(tool_counts)

    # Treat non-primary children as extra grandchildren for artifact scanning
    other_children = [c for c in children if c is not primary]
    artifacts = _extract_artifacts(primary, other_children + all_grandchildren)

    return PhaseView(
        phase_name=phase_name,
        run_name=phase_name,
        run_id=run_id,
        agent=agent,
        status=status,
        duration=duration,
        cost=cost,
        activity_summary=activity_summary,
        artifacts=artifacts,
    )


def _phase_sort_key(phase: PhaseView) -> int:
    """Return a sort index based on canonical phase order."""
    try:
        return _PHASE_ORDER.index(phase.phase_name)
    except ValueError:
        return len(_PHASE_ORDER)


# ─── Phase classification ─────────────────────────────────────────────────────


def _classify_phase(run_name: str) -> str:
    """Map a run name to a canonical pipeline phase label."""
    lower = run_name.lower()
    for pattern, label in _PHASE_PATTERNS:
        if pattern in lower:
            return label
    return _UNKNOWN_PHASE


# ─── Agent extraction ─────────────────────────────────────────────────────────


def _extract_agent(run: dict) -> str:
    """Extract the agent type from run metadata or model field."""
    meta = _parse_json(run.get("metadata_json"))
    agent = meta.get("agent_type") or meta.get("agent") or run.get("model") or ""
    return agent


# ─── Status extraction ────────────────────────────────────────────────────────


def _extract_status(run: dict) -> str:
    """Determine run status: error, running, success, or unknown."""
    if run.get("error"):
        return "error"
    if run.get("end_time"):
        return "success"
    if run.get("start_time"):
        return "running"
    return "unknown"


# ─── Tool call counting ───────────────────────────────────────────────────────


def _count_tools(child: dict, grandchildren: list[dict]) -> dict[str, int]:
    """Aggregate tool call counts across a child run and its grandchildren."""
    counts: dict[str, int] = {}
    for run in [child, *grandchildren]:
        _accumulate_tool_counts(run, counts)
    return counts


def _accumulate_tool_counts(run: dict, counts: dict[str, int]) -> None:
    """Add tool call counts from one run dict into the accumulator.

    Tool calls are stored in outputs_json under the 'messages' key for LLM runs,
    or in inputs_json for tool runs. We inspect both and count by tool name.
    """
    for field_name in ("inputs_json", "outputs_json"):
        raw = run.get(field_name)
        if not raw:
            continue
        parsed = _parse_json(raw)
        _collect_from_messages(parsed.get("messages", []), counts)
        _collect_from_tool_use(parsed, counts)


def _collect_from_messages(messages: object, counts: dict[str, int]) -> None:
    """Count tool_use blocks embedded in message content lists."""
    if not isinstance(messages, list):
        return
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                tool_name = block.get("name", "unknown")
                counts[tool_name] = counts.get(tool_name, 0) + 1


def _collect_from_tool_use(parsed: dict, counts: dict[str, int]) -> None:
    """Count tool name from a tool-run dict that has a top-level 'name' field."""
    name = parsed.get("name")
    if isinstance(name, str) and name:
        counts[name] = counts.get(name, 0) + 1


# ─── Activity summary ─────────────────────────────────────────────────────────


def _format_activity_summary(tool_counts: dict[str, int]) -> str:
    """Convert tool call counts to a human-readable activity summary.

    Example: "Read 5 files, edited 2, ran 8 bash commands, committed"
    """
    if not tool_counts:
        return ""

    parts: list[str] = []
    for tool_name, verb in _TOOL_VERB.items():
        count = tool_counts.get(tool_name, 0)
        if count == 0:
            continue
        if tool_name == "Read":
            parts.append(f"Read {count} file{'s' if count != 1 else ''}")
        elif tool_name == "Edit":
            parts.append(f"edited {count}")
        elif tool_name == "Write":
            parts.append(f"wrote {count}")
        elif tool_name == "Bash":
            parts.append(f"ran {count} bash command{'s' if count != 1 else ''}")
        elif tool_name == "Grep":
            parts.append(f"searched {count} time{'s' if count != 1 else ''}")
        elif tool_name == "Glob":
            parts.append(f"globbed {count} time{'s' if count != 1 else ''}")
        elif tool_name == "TodoWrite":
            parts.append("updated todos")
        elif tool_name == "Agent":
            parts.append(f"dispatched {count} agent{'s' if count != 1 else ''}")
        elif tool_name == "WebSearch":
            parts.append(f"searched web {count} time{'s' if count != 1 else ''}")
        elif tool_name == "WebFetch":
            parts.append(f"fetched {count} URL{'s' if count != 1 else ''}")

    # Include any tools not in the verb map
    known = set(_TOOL_VERB.keys())
    for tool_name, count in sorted(tool_counts.items()):
        if tool_name not in known:
            parts.append(f"{tool_name} x{count}")

    return ", ".join(parts)


# ─── Artifact extraction ──────────────────────────────────────────────────────


_ARTIFACT_PATTERNS: list[tuple[str, str]] = [
    ("docs/plans/", "Design doc"),
    ("tmp/plans/", "Plan YAML"),
    ("tmp/plans/.claimed/", "Work item"),
    ("docs/completed-backlog/", "Completed item"),
    ("logs/", "Log file"),
]


def _extract_artifacts(child: dict, grandchildren: list[dict]) -> list[PhaseArtifact]:
    """Extract linkable artifacts from run metadata and tool call outputs."""
    artifacts: list[PhaseArtifact] = []
    seen_paths: set[str] = set()

    for run in [child, *grandchildren]:
        meta = _parse_json(run.get("metadata_json"))
        _collect_metadata_artifacts(meta, artifacts, seen_paths)
        _collect_file_artifacts(run, artifacts, seen_paths)

    return artifacts


def _collect_metadata_artifacts(
    meta: dict,
    artifacts: list[PhaseArtifact],
    seen_paths: set[str],
) -> None:
    """Extract artifacts from well-known metadata keys."""
    for key in ("design_doc", "plan_file", "source_item", "validation_report"):
        value = meta.get(key)
        if value and isinstance(value, str) and value not in seen_paths:
            seen_paths.add(value)
            label = _artifact_label(value)
            artifacts.append(PhaseArtifact(label=label, path=value))


def _collect_file_artifacts(
    run: dict,
    artifacts: list[PhaseArtifact],
    seen_paths: set[str],
) -> None:
    """Extract Write/Edit targets that look like notable artifacts."""
    for field_name in ("inputs_json", "outputs_json"):
        raw = run.get(field_name)
        if not raw:
            continue
        parsed = _parse_json(raw)
        messages = parsed.get("messages", [])
        if not isinstance(messages, list):
            continue
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_use":
                    continue
                if block.get("name") not in ("Write", "Edit"):
                    continue
                path = block.get("input", {}).get("file_path", "")
                if path and path not in seen_paths and _is_notable_artifact(path):
                    seen_paths.add(path)
                    artifacts.append(PhaseArtifact(label=_artifact_label(path), path=path))


def _is_notable_artifact(path: str) -> bool:
    """Return True if the path matches any known artifact pattern."""
    return any(pattern in path for pattern, _ in _ARTIFACT_PATTERNS)


def _artifact_label(path: str) -> str:
    """Return a human-readable label for an artifact path."""
    for pattern, label in _ARTIFACT_PATTERNS:
        if pattern in path:
            return label
    # Fall back to the last path component
    return path.split("/")[-1] if "/" in path else path


# ─── Formatting helpers ───────────────────────────────────────────────────────


def _scan_children_for_slug(children: list[dict]) -> str:
    """Return the first non-empty, non-LangGraph slug found in children metadata."""
    for child in children:
        meta = _parse_json(child.get("metadata_json"))
        slug = meta.get("slug") or meta.get("item_slug") or ""
        if slug and slug != "LangGraph":
            return slug
    return ""


def _aggregate_cost_display(runs: list[dict]) -> str:
    """Sum cost values from all run metadata dicts; return formatted string or empty."""
    total = 0.0
    found = False
    for run in runs:
        meta = _parse_json(run.get("metadata_json"))
        cost = meta.get("cost") or meta.get("total_cost")
        if cost is not None:
            try:
                total += float(cost)
                found = True
            except (TypeError, ValueError):
                pass
    return _COST_DISPLAY_FORMAT.format(total) if found else ""


def _duration_from_children(children: list[dict]) -> str:
    """Compute total duration as the span from first child start to last child end."""
    valid_starts = [_parse_iso(c.get("start_time")) for c in children]
    valid_ends = [_parse_iso(c.get("end_time")) for c in children]
    starts = [s for s in valid_starts if s is not None]
    ends = [e for e in valid_ends if e is not None]
    if not starts or not ends:
        return _DURATION_UNKNOWN
    return _format_duration_from_datetimes(min(starts), max(ends))


def _format_duration_from_datetimes(dt_start: datetime, dt_end: datetime) -> str:
    """Return a human-readable duration string from two datetime objects."""
    delta = (dt_end - dt_start).total_seconds()
    if delta < 0:
        return _DURATION_UNKNOWN
    if delta < _DURATION_MINUTE_THRESHOLD:
        return _DURATION_SECONDS_FORMAT.format(delta)
    minutes = int(delta // 60)
    seconds = int(delta % 60)
    return _DURATION_MINUTES_FORMAT.format(minutes, seconds)


def _compute_overall_status(run: dict, children: list[dict]) -> str:
    """Return corrected run status, treating stale running runs as completed.

    A run is considered completed when all its children have ended and the
    most recent child end_time is more than _STATUS_STALE_THRESHOLD_MINUTES ago.
    """
    if run.get("error"):
        return "error"
    if run.get("end_time"):
        return "completed"
    if not children:
        return "running" if run.get("start_time") else "unknown"

    child_ends = [_parse_iso(c.get("end_time")) for c in children]
    if any(e is None for e in child_ends):
        return "running"

    valid_ends = [e for e in child_ends if e is not None]
    if valid_ends:
        latest_end = max(valid_ends)
        elapsed_minutes = (
            (datetime.now(timezone.utc) - latest_end).total_seconds() / 60
        )
        if elapsed_minutes > _STATUS_STALE_THRESHOLD_MINUTES:
            return "completed"
    return "running"


def _format_duration(start: Optional[str], end: Optional[str]) -> str:
    """Return a human-readable duration string from ISO-8601 timestamps."""
    dt_start = _parse_iso(start)
    dt_end = _parse_iso(end)
    if dt_start is None or dt_end is None:
        return _DURATION_UNKNOWN
    return _format_duration_from_datetimes(dt_start, dt_end)


def _extract_cost_display(meta: dict) -> str:
    """Return a formatted cost string from metadata, or empty string if absent."""
    cost = meta.get("cost") or meta.get("total_cost")
    if cost is None:
        return ""
    try:
        return _COST_DISPLAY_FORMAT.format(float(cost))
    except (TypeError, ValueError):
        return ""


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp to a UTC datetime, returning None on error."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_json(raw: Optional[str]) -> dict:
    """Parse a JSON string to a dict; return empty dict on any error."""
    if not raw:
        return {}
    try:
        result = json.loads(raw)
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}
