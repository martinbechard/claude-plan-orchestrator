# langgraph_pipeline/web/routes/item.py
# FastAPI router for the GET /item/{slug} work-item detail page.
# Design: docs/plans/2026-03-26-35-work-item-page-missing-requirements-from-backlog-file-design.md
# Design: docs/plans/2026-03-26-43-capture-raw-worker-output-per-item-design.md
# Design: docs/plans/2026-03-27-56-item-page-show-output-artifacts-design.md
# Design: docs/plans/2026-03-27-57-track-and-display-item-artifacts-design.md
# Design: docs/plans/2026-03-28-72-item-page-auto-refresh-collapses-sections-design.md
# Design: docs/plans/2026-03-29-74-item-page-step-explorer-design.md

"""FastAPI router that serves the work-item detail page.

Endpoints:
    GET /item/{slug}                    — Renders item.html with requirements, plan tasks,
                                          completion history, and linked root traces.
    GET /item/{slug}/dynamic            — Returns JSON with dynamic item data for
                                          selective refresh (D2).
    GET /item/{slug}/output/{filename}  — Returns a worker log file as text/plain.
    GET /item/{slug}/artifact-content   — Returns a project file as text/plain.
"""

import json
import logging
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, TypedDict

import yaml
from fastapi import APIRouter, HTTPException, Query

# Suppress noisy DEBUG messages from the markdown library
# ("Successfully loaded extension ...") on every conversion call.
logging.getLogger("markdown").setLevel(logging.WARNING)
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from langgraph_pipeline.shared.artifact_manifest import load_manifest
from langgraph_pipeline.shared.paths import (
    BACKLOG_DIRS,
    CLAIMED_DIR,
    COMPLETED_DIRS,
    WORKER_OUTPUT_DIR,
    workspace_path as ws_path_fn,
)
from langgraph_pipeline.web.proxy import get_proxy

# ─── Constants ────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_PLANS_DIR = Path("tmp/plans")
_CLAIMED_PATH = Path(CLAIMED_DIR)
_DESIGN_DOCS_DIR = Path("docs/plans")

_REPORTS_DIR = Path("docs/reports")

_SOURCE_GIT = "git"
_SOURCE_DESIGN = "design"
_SOURCE_REPORT = "report"

_ACTION_CREATED = "created"
_ACTION_MODIFIED = "modified"
_ACTION_DISCOVERED = "discovered"

_STAGE_EXECUTING = "executing"
_STAGE_VALIDATING = "validating"
_STAGE_COMPLETED = "completed"
_STAGE_PLANNING = "planning"
_STAGE_CLAIMED = "claimed"
_STAGE_DESIGNING = "designing"
_STAGE_QUEUED = "queued"
_STAGE_STUCK = "stuck"
_STAGE_UNKNOWN = "unknown"

_STAGE_STATUS_NOT_STARTED = "not_started"
_STAGE_STATUS_IN_PROGRESS = "in_progress"
_STAGE_STATUS_DONE = "done"

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"

# Ordered pipeline stages for the step-explorer accordion (D1/AC9).
# Each tuple is (machine_id, display_name).  This constant is the single
# source of truth for stage identity and display names.
STAGE_ORDER: list[tuple[str, str]] = [
    ("intake", "Intake"),
    ("requirements", "Requirements"),
    ("planning", "Planning"),
    ("execution", "Execution"),
    ("verification", "Verification"),
    ("archive", "Archive"),
]

# Maps stage id -> canonical index in STAGE_ORDER for status matrix lookup.
# Used instead of positional indexing so that omitting Verification for
# features does not shift the archive column to the wrong matrix position.
_STAGE_ID_TO_ORDER_INDEX: dict[str, int] = {
    sid: i for i, (sid, _) in enumerate(STAGE_ORDER)
}

# ─── Data Models ──────────────────────────────────────────────────────────────


class ArtifactInfo(TypedDict):
    """A single discoverable artifact within a pipeline stage.

    name: Human-readable label shown in the UI (e.g. "User Request").
    path: Relative file path passed to /artifact-content for on-demand loading.
    timestamp: Raw epoch float from file mtime; 0.0 when unavailable.
    timestamp_display: Pre-formatted "YYYY-MM-DD HH:MM" string for Jinja2.
    """

    name: str
    path: str
    timestamp: float
    timestamp_display: str


class StageInfo(TypedDict):
    """One ordered pipeline stage containing zero or more artifacts.

    id: Lowercase identifier (e.g. "intake") used as CSS class and JSON key.
    name: Title-case display label (e.g. "Intake").
    status: One of "not_started", "in_progress", or "done".
    artifacts: Ordered list of discovered artifacts for this stage.
    completion_ts: Formatted timestamp when done, None otherwise.
    completion_epoch: Raw epoch float for JSON serialisation, None otherwise.
    """

    id: str
    name: str
    status: str
    artifacts: list[ArtifactInfo]
    completion_ts: Optional[str]
    completion_epoch: Optional[float]


# ─── Jinja2 Setup ─────────────────────────────────────────────────────────────

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter()

# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/item/{slug}", response_class=HTMLResponse)
def item_detail(request: Request, slug: str) -> HTMLResponse:
    """Render the work-item detail page for the given slug.

    Aggregates requirements markdown, plan task list, completion history,
    and linked root traces. Never returns 404; missing data sections are
    shown as empty with a "No data found" notice.

    Args:
        request: Starlette request required by Jinja2TemplateResponse.
        slug: Work item slug (e.g. "01-some-feature").

    Returns:
        Rendered item.html template.
    """
    requirements_html = _load_requirements_html(slug)
    original_request_html = _load_original_request_html(slug)
    structured_requirements_html = _load_structured_requirements_html(slug)
    clause_register_html = _load_workspace_artifact_html(slug, "clauses.md")
    five_whys_html = _load_workspace_artifact_html(slug, "five-whys.md")
    cross_ref_reports = _load_cross_reference_reports(slug)
    item_type = _detect_item_type(slug)
    plan_tasks = _load_plan_tasks(slug)
    completions = _load_completions(slug)
    _parse_verification_notes(completions)
    outcome = _derive_outcome(completions)
    traces = _load_root_traces(slug)
    pipeline_stage = _derive_pipeline_stage(slug, completions)
    active_worker = _get_active_worker(slug)
    total_cost_usd = sum(c.get("cost_usd", 0.0) for c in completions)
    total_duration_s = sum(c.get("duration_s", 0.0) for c in completions)
    total_tokens = _compute_total_tokens(completions)
    output_files = _list_output_files(slug)
    output_artifacts = _collect_output_artifacts(slug)
    validation_results = _load_validation_results(slug)
    avg_velocity = _compute_avg_velocity(completions)
    stages = build_stages(slug, item_type, pipeline_stage)

    # When a worker is active, use its live stats instead of completions
    if active_worker:
        if active_worker.get("tokens_in", 0) + active_worker.get("tokens_out", 0) > 0:
            total_tokens = active_worker["tokens_in"] + active_worker["tokens_out"]
        if active_worker.get("cost_usd", 0) > 0:
            total_cost_usd = active_worker["cost_usd"]
        total_duration_s = active_worker.get("elapsed_raw_s", 0)
        if active_worker.get("current_velocity", 0) > 0:
            avg_velocity = active_worker["current_velocity"]
    last_trace = traces[0] if traces else None

    return templates.TemplateResponse(
        request,
        "item.html",
        {
            "slug": slug,
            "item_type": item_type,
            "pipeline_stage": pipeline_stage,
            "active_worker": active_worker,
            "total_cost_usd": total_cost_usd,
            "total_duration_s": total_duration_s,
            "total_tokens": total_tokens,
            "stages": stages,
            "requirements_html": requirements_html,
            "original_request_html": original_request_html,
            "structured_requirements_html": structured_requirements_html,
            "clause_register_html": clause_register_html,
            "five_whys_html": five_whys_html,
            "cross_ref_reports": cross_ref_reports,
            "plan_tasks": plan_tasks,
            "completions": completions,
            "traces": traces,
            "output_files": output_files,
            "output_artifacts": output_artifacts,
            "validation_results": validation_results,
            "avg_velocity": avg_velocity,
            "last_trace": last_trace,
            "outcome": outcome,
        },
    )


@router.get("/item/{slug}/dynamic", response_class=JSONResponse)
def item_dynamic(slug: str) -> JSONResponse:
    """Return dynamic item data as JSON for selective refresh (D2).

    Computes only the values that change during processing, reusing
    the same helper functions as item_detail. When an active worker
    is present, its live stats override completion aggregates.

    Args:
        slug: Work item slug (e.g. "72-item-page-auto-refresh").

    Returns:
        JSON object with pipeline_stage, active_worker, total_cost_usd,
        total_duration_s, total_tokens, avg_velocity, plan_tasks,
        validation_results, and stages (lightweight stage-status summary).
    """
    completions = _load_completions(slug)
    outcome = _derive_outcome(completions)
    pipeline_stage = _derive_pipeline_stage(slug, completions)
    item_type = _detect_item_type(slug)
    active_worker = _get_active_worker(slug)
    total_cost_usd = sum(c.get("cost_usd", 0.0) for c in completions)
    total_duration_s = sum(c.get("duration_s", 0.0) for c in completions)
    total_tokens = _compute_total_tokens(completions)
    avg_velocity = _compute_avg_velocity(completions)
    plan_tasks = _load_plan_tasks(slug)
    validation_results = _load_validation_results(slug)
    stages = build_stages(slug, item_type, pipeline_stage)
    stage_summaries = [
        {
            "id": s["id"],
            "status": s["status"],
            "completion_ts": s["completion_ts"],
            "completion_epoch": s["completion_epoch"],
            "artifact_count": len(s["artifacts"]),
        }
        for s in stages
    ]

    # When a worker is active, use its live stats instead of completions
    if active_worker:
        if active_worker.get("tokens_in", 0) + active_worker.get("tokens_out", 0) > 0:
            total_tokens = active_worker["tokens_in"] + active_worker["tokens_out"]
        if active_worker.get("cost_usd", 0) > 0:
            total_cost_usd = active_worker["cost_usd"]
        total_duration_s = active_worker.get("elapsed_raw_s", 0)
        if active_worker.get("current_velocity", 0) > 0:
            avg_velocity = active_worker["current_velocity"]

    return JSONResponse(content={
        "pipeline_stage": pipeline_stage,
        "active_worker": active_worker,
        "total_cost_usd": total_cost_usd,
        "total_duration_s": total_duration_s,
        "total_tokens": total_tokens,
        "avg_velocity": avg_velocity,
        "plan_tasks": plan_tasks,
        "validation_results": validation_results,
        "stages": stage_summaries,
        "outcome": outcome,
    })


@router.get("/item/{slug}/output/{filename}", response_class=PlainTextResponse)
def item_output_file(slug: str, filename: str) -> PlainTextResponse:
    """Return a raw worker log file as text/plain.

    Serves files from docs/reports/worker-output/<slug>/<filename>.
    Rejects any filename containing path separators to prevent traversal.

    Args:
        slug: Work item slug (e.g. "43-capture-raw-worker-output").
        filename: Log filename (e.g. "task-1.1-20260326-143022.log").

    Returns:
        Plain-text content of the log file.

    Raises:
        HTTPException 400: If the filename contains path traversal characters.
        HTTPException 404: If the log file does not exist.
    """
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    output_dir = WORKER_OUTPUT_DIR / slug
    log_path = output_dir / filename

    # Resolve to catch any remaining traversal attempts (e.g. encoded separators)
    try:
        resolved = log_path.resolve()
        expected_parent = output_dir.resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not str(resolved).startswith(str(expected_parent) + "/"):
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not resolved.exists():
        raise HTTPException(status_code=404, detail="Log file not found")

    return PlainTextResponse(content=resolved.read_text(encoding="utf-8", errors="replace"))


@router.get("/item/{slug}/artifact-content", response_class=PlainTextResponse)
def item_artifact_content(
    slug: str, path: str = Query(..., description="Relative path to the artifact file")
) -> PlainTextResponse:
    """Return the text content of an artifact file within the project root.

    Validates that the requested path resolves to a location inside the project
    root to prevent directory traversal. Only serves regular files.

    Args:
        slug: Work item slug (used for URL structure; the path param selects the file).
        path: Relative or absolute path to the artifact (query parameter).

    Returns:
        Plain-text content of the file.

    Raises:
        HTTPException 400: If the path resolves outside the project root.
        HTTPException 404: If the file does not exist or is not a regular file.
    """
    project_root = Path.cwd().resolve()
    try:
        requested = Path(path).resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not str(requested).startswith(str(project_root) + "/"):
        raise HTTPException(status_code=400, detail="Path outside project root")

    if not requested.exists() or not requested.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return PlainTextResponse(content=requested.read_text(encoding="utf-8", errors="replace"))


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _format_timestamp(epoch: float) -> str:
    """Format an epoch float as 'YYYY-MM-DD HH:MM' in local time.

    Returns an empty string when epoch is 0.0 (sentinel for unavailable mtime).

    Args:
        epoch: Seconds since Unix epoch.

    Returns:
        Formatted timestamp string, or empty string for epoch 0.0.
    """
    if epoch == 0.0:
        return ""
    return datetime.fromtimestamp(epoch).strftime(_TIMESTAMP_FORMAT)


def _make_artifact(name: str, path: Path) -> ArtifactInfo:
    """Create an ArtifactInfo dict for an existing file.

    Args:
        name: Human-readable display label.
        path: Path to the artifact file.

    Returns:
        ArtifactInfo dict with timestamp from file mtime (0.0 on error).
    """
    try:
        ts = path.stat().st_mtime
    except Exception:
        ts = 0.0
    return {
        "name": name,
        "path": str(path),
        "timestamp": ts,
        "timestamp_display": _format_timestamp(ts),
    }


def build_stages(
    slug: str,
    item_type: Optional[str],
    pipeline_stage: str,
) -> list[StageInfo]:
    """Build the ordered list of pipeline stages with their discovered artifacts.

    Performs three passes:
    1. Discover artifacts per stage using existing helper functions.
    2. Compute stage status via _compute_stage_statuses().
    3. Compute completion timestamps for done stages (latest artifact mtime).

    The Verification stage is omitted entirely when item_type is "feature".

    Args:
        slug: Work item slug.
        item_type: "feature", "defect", "analysis", or None.
        pipeline_stage: Current pipeline stage from _derive_pipeline_stage().

    Returns:
        Ordered list of StageInfo dicts per STAGE_ORDER (without Verification
        when item_type is "feature").
    """
    # ── Pass 1: Discover artifacts per stage ──────────────────────────────────

    stage_artifacts: dict[str, list[ArtifactInfo]] = {sid: [] for sid, _ in STAGE_ORDER}

    # Intake
    req_path = _find_original_request_file(slug)
    if req_path is not None:
        stage_artifacts["intake"].append(_make_artifact("User Request", req_path))
    clauses_path = ws_path_fn(slug) / "clauses.md"
    if clauses_path.exists():
        stage_artifacts["intake"].append(_make_artifact("Clause Register", clauses_path))
    five_whys_path = ws_path_fn(slug) / "five-whys.md"
    if five_whys_path.exists():
        stage_artifacts["intake"].append(_make_artifact("5 Whys Analysis", five_whys_path))

    # Requirements
    req_file = _find_structured_requirements_file(slug)
    if req_file is not None:
        stage_artifacts["requirements"].append(
            _make_artifact("Structured Requirements", req_file)
        )

    # Planning
    design_doc = _find_design_doc(slug)
    if design_doc is not None:
        stage_artifacts["planning"].append(_make_artifact("Design Document", design_doc))
    plan_yaml = _find_plan_yaml(slug)
    if plan_yaml is not None:
        stage_artifacts["planning"].append(_make_artifact("YAML Plan", plan_yaml))

    # Execution: log files (worker-output first, then workspace logs; deduplicate by name)
    seen_logs: set[str] = set()
    for log_dir in [WORKER_OUTPUT_DIR / slug, ws_path_fn(slug) / "logs"]:
        if not log_dir.is_dir():
            continue
        for p in sorted(log_dir.iterdir()):
            if p.suffix == ".log" and p.name not in seen_logs:
                seen_logs.add(p.name)
                stage_artifacts["execution"].append(_make_artifact(p.name, p))

    # Execution: validation JSON files (workspace first, then worker-output)
    seen_val: set[str] = set()
    for val_dir in [ws_path_fn(slug) / "validation", WORKER_OUTPUT_DIR / slug]:
        if not val_dir.is_dir():
            continue
        for p in sorted(val_dir.glob("validation-*.json")):
            if p.name not in seen_val:
                seen_val.add(p.name)
                stage_artifacts["execution"].append(_make_artifact(p.name, p))

    # Verification: workspace takes priority over worker-output
    for vr_path in [
        ws_path_fn(slug) / "verification-report.md",
        WORKER_OUTPUT_DIR / slug / "verification-report.md",
    ]:
        if vr_path.exists():
            stage_artifacts["verification"].append(
                _make_artifact("Verification Report", vr_path)
            )
            break

    # Archive: first match across completed backlog directories
    for dir_str in COMPLETED_DIRS.values():
        completion_path = Path(dir_str) / f"{slug}.md"
        if completion_path.exists():
            stage_artifacts["archive"].append(
                _make_artifact("Completion Record", completion_path)
            )
            break

    # ── Build initial StageInfo list ──────────────────────────────────────────

    stages: list[StageInfo] = []
    for stage_id, stage_name in STAGE_ORDER:
        if stage_id == "verification" and item_type == "feature":
            continue
        stages.append({
            "id": stage_id,
            "name": stage_name,
            "status": _STAGE_STATUS_NOT_STARTED,
            "artifacts": stage_artifacts[stage_id],
            "completion_ts": None,
            "completion_epoch": None,
        })

    # ── Pass 2: Compute stage statuses ────────────────────────────────────────
    _compute_stage_statuses(stages, pipeline_stage)

    # ── Pass 3: Compute completion timestamps for done stages ─────────────────
    for stage in stages:
        if stage["status"] == _STAGE_STATUS_DONE and stage["artifacts"]:
            max_ts = max(a["timestamp"] for a in stage["artifacts"])
            stage["completion_epoch"] = max_ts
            stage["completion_ts"] = _format_timestamp(max_ts)

    return stages


def _compute_stage_statuses(
    stages: list[StageInfo],
    pipeline_stage: str,
) -> None:
    """Mutate stages in place to set status fields based on pipeline_stage.

    Uses a lookup matrix mapping each pipeline_stage value to a list of
    expected statuses per stage index, adjusted for artifact presence on
    "done*" entries (stages that should show done only when artifacts exist).

    Args:
        stages: List of StageInfo dicts to update in place.
        pipeline_stage: Current pipeline stage string from _derive_pipeline_stage().
    """
    # Base status assignments per pipeline_stage (before artifact-presence
    # adjustment).  "done*" is represented as DONE here; the adjustment below
    # downgrades to IN_PROGRESS when the stage has no artifacts.
    # Matrix columns are indexed by canonical STAGE_ORDER position via
    # _STAGE_ID_TO_ORDER_INDEX, so omitting Verification for features does
    # not shift archive to the wrong column.
    D = _STAGE_STATUS_DONE
    P = _STAGE_STATUS_IN_PROGRESS
    N = _STAGE_STATUS_NOT_STARTED

    _BASE_MATRIX: dict[str, list[str]] = {
        _STAGE_QUEUED:    [N, N, N, N, N, N],
        _STAGE_UNKNOWN:   [N, N, N, N, N, N],
        _STAGE_CLAIMED:   [P, N, N, N, N, N],
        _STAGE_DESIGNING: [D, D, P, N, N, N],
        _STAGE_PLANNING:  [D, D, P, N, N, N],
        _STAGE_EXECUTING: [D, D, D, P, N, N],
        _STAGE_VALIDATING:[D, D, D, D, P, N],
        _STAGE_COMPLETED: [D, D, D, D, D, D],
    }

    # "done*" stages: a stage is in_progress when it has no artifacts,
    # even though the pipeline has nominally moved past it.
    _DONE_STAR_STAGES = {"intake", "requirements", "planning", "execution", "verification"}

    base_statuses = _BASE_MATRIX.get(pipeline_stage)
    if base_statuses is None:
        # stuck or unrecognised: derive from artifact presence
        found_in_progress = False
        for stage in stages:
            if stage["artifacts"]:
                stage["status"] = D
            elif not found_in_progress:
                stage["status"] = P
                found_in_progress = True
            else:
                stage["status"] = N
        return

    # Apply base matrix using canonical STAGE_ORDER index (not filtered position)
    for stage in stages:
        order_idx = _STAGE_ID_TO_ORDER_INDEX.get(stage["id"], -1)
        if order_idx < 0 or order_idx >= len(base_statuses):
            stage["status"] = N
            continue
        assigned = base_statuses[order_idx]
        if (
            assigned == D
            and stage["id"] in _DONE_STAR_STAGES
            and pipeline_stage != _STAGE_COMPLETED
            and not stage["artifacts"]
        ):
            assigned = P
        stage["status"] = assigned


def _render_md_to_html(md_path: Path) -> str:
    """Render a markdown file to an HTML string.

    Args:
        md_path: Path to the markdown file.

    Returns:
        HTML string, or empty string on error.
    """
    try:
        import markdown
        text = md_path.read_text(encoding="utf-8")
        return markdown.markdown(text, extensions=["fenced_code", "tables"])
    except Exception:
        return ""


def _find_requirements_file(slug: str) -> Optional[Path]:
    """Locate the primary requirements document using the priority chain.

    Priority order:
    1. Design doc  — ``docs/plans/*-<slug>-design.md`` (most-recent glob match)
    2. Claimed     — ``tmp/plans/.claimed/<slug>.md``
    3. Active backlog dirs
    4. Completed backlog dirs

    Args:
        slug: Work item slug.

    Returns:
        Path to the highest-priority file found, or None.
    """
    design = _find_design_doc(slug)
    if design is not None:
        return design

    claimed = _CLAIMED_PATH / f"{slug}.md"
    if claimed.exists():
        return claimed

    for dir_str in BACKLOG_DIRS.values():
        candidate = Path(dir_str) / f"{slug}.md"
        if candidate.exists():
            return candidate

    for dir_str in COMPLETED_DIRS.values():
        candidate = Path(dir_str) / f"{slug}.md"
        if candidate.exists():
            return candidate

    return None


def _find_original_request_file(slug: str) -> Optional[Path]:
    """Return the original backlog/claimed file (the raw input).

    Searches claimed, active backlog, and completed backlog in that order.
    Always returns the raw backlog file if found, regardless of whether a
    design doc or structured requirements exist.

    Args:
        slug: Work item slug.

    Returns:
        Path to the original request file, or None if not found.
    """
    claimed = _CLAIMED_PATH / f"{slug}.md"
    if claimed.exists():
        return claimed

    for dir_str in BACKLOG_DIRS.values():
        candidate = Path(dir_str) / f"{slug}.md"
        if candidate.exists():
            return candidate

    for dir_str in COMPLETED_DIRS.values():
        candidate = Path(dir_str) / f"{slug}.md"
        if candidate.exists():
            return candidate

    return None


def _find_structured_requirements_file(slug: str) -> Optional[Path]:
    """Locate the structured requirements file for the given slug.

    Checks workspace first, then falls back to docs/plans/ glob.

    Args:
        slug: Work item slug.

    Returns:
        Path to the structured requirements file, or None if not found.
    """
    # Check workspace first
    ws_req = ws_path_fn(slug) / "requirements.md"
    if ws_req.exists():
        return ws_req
    # Fallback to legacy location
    matches = sorted(_DESIGN_DOCS_DIR.glob(f"*-{slug}-requirements.md"))
    return matches[0] if matches else None


def _load_structured_requirements_html(slug: str) -> Optional[str]:
    """Return structured requirements rendered as HTML, or None if not found.

    Args:
        slug: Work item slug.

    Returns:
        HTML string, or None when no structured requirements file exists.
    """
    md_path = _find_structured_requirements_file(slug)
    if md_path is None:
        return None
    html = _render_md_to_html(md_path)
    return html if html else None


def _load_workspace_artifact_html(slug: str, filename: str) -> Optional[str]:
    """Load a markdown artifact from the workspace and render as HTML.

    Args:
        slug: Work item slug.
        filename: Artifact filename (e.g. 'clauses.md', 'five-whys.md').

    Returns:
        HTML string, or None if the file does not exist.
    """
    artifact_path = ws_path_fn(slug) / filename
    if not artifact_path.exists():
        return None
    html = _render_md_to_html(artifact_path)
    return html if html else None


def _load_cross_reference_reports(slug: str) -> list[dict[str, str]]:
    """Load all cross-reference validation reports from the workspace.

    Returns a list of dicts with 'name' (human-readable step name) and 'html'
    (rendered markdown content), sorted by step number.
    """
    val_dir = ws_path_fn(slug) / "validation"
    if not val_dir.exists():
        return []
    reports: list[dict[str, str]] = []
    for report_file in sorted(val_dir.glob("step-*.md")):
        html = _render_md_to_html(report_file)
        if html:
            # Extract step name from filename: step-3-requirements-structuring-20260328T...md
            parts = report_file.stem.split("-", 3)
            step_num = parts[1] if len(parts) > 1 else "?"
            step_name = parts[2] if len(parts) > 2 else "unknown"
            # Remove timestamp from step_name if present
            if len(parts) > 3:
                step_name = parts[2]
            display_name = f"Step {step_num}: {step_name.replace('-', ' ').title()}"
            reports.append({"name": display_name, "html": html})
    return reports


def _load_requirements_html(slug: str) -> str:
    """Return primary requirements markdown rendered as HTML, or empty string if not found.

    Uses the priority chain in ``_find_requirements_file``.

    Args:
        slug: Work item slug.

    Returns:
        HTML string, or empty string when no file is found.
    """
    md_path = _find_requirements_file(slug)
    if md_path is None:
        return ""
    return _render_md_to_html(md_path)


def _load_original_request_html(slug: str) -> Optional[str]:
    """Return original backlog/claimed request (raw input) rendered as HTML.

    Strips the appended 5 Whys section if present, since the 5 Whys has its
    own dedicated display section from the workspace artifact.

    Args:
        slug: Work item slug.

    Returns:
        HTML string, or None when no raw backlog file is found.
    """
    md_path = _find_original_request_file(slug)
    if md_path is None:
        return None
    try:
        import markdown
        text = md_path.read_text(encoding="utf-8")
        # Strip appended 5 Whys section to avoid duplication with the
        # dedicated 5 Whys panel (loaded from workspace five-whys.md).
        whys_marker = "\n## 5 Whys Analysis"
        marker_idx = text.find(whys_marker)
        if marker_idx >= 0:
            text = text[:marker_idx].rstrip()
        return markdown.markdown(text, extensions=["fenced_code", "tables"])
    except Exception:
        return None


def _detect_item_type(slug: str) -> Optional[str]:
    """Infer item type by locating the requirements file in typed directories.

    Args:
        slug: Work item slug.

    Returns:
        One of "feature", "defect", "analysis", or None if not found.
    """
    all_dirs = {**BACKLOG_DIRS, **COMPLETED_DIRS}
    for item_type, dir_str in all_dirs.items():
        # COMPLETED_DIRS keys have the same names as BACKLOG_DIRS keys
        if (Path(dir_str) / f"{slug}.md").exists():
            # Strip trailing 's' from plural completed dir key if needed
            # Keys are: "defect", "feature", "analysis" for both dicts
            return item_type
    return None


def _load_plan_tasks(slug: str) -> Optional[list[dict]]:
    """Load and flatten plan tasks from the YAML plan file for the given slug.

    Tries ``<slug>.yaml`` first, then globs for ``<slug>*.yaml``.

    Args:
        slug: Work item slug.

    Returns:
        Flat list of dicts with keys: id, name, status — or None if no plan found.
    """
    plan_path = _PLANS_DIR / f"{slug}.yaml"
    if not plan_path.exists():
        matches = sorted(_PLANS_DIR.glob(f"{slug}*.yaml"))
        if matches:
            plan_path = matches[0]
        else:
            # Check workspace and worker-output for archived plans
            for candidate in [
                ws_path_fn(slug) / "plan.yaml",
                WORKER_OUTPUT_DIR / slug / "plan.yaml",
            ]:
                if candidate.exists():
                    plan_path = candidate
                    break
            else:
                return None

    try:
        with plan_path.open(encoding="utf-8") as fh:
            plan = yaml.safe_load(fh)
    except Exception:
        return None

    tasks: list[dict] = []
    for section in plan.get("sections", []):
        for task in section.get("tasks", []):
            tasks.append(
                {
                    "id": task.get("id", ""),
                    "name": task.get("name", ""),
                    "status": task.get("status", "pending"),
                    "agent": task.get("agent", ""),
                }
            )
    return tasks if tasks else None


def _derive_outcome(completions: list[dict]) -> Optional[str]:
    """Return the outcome from the most recent completion record.

    The completions list is ordered by finished_at descending (newest first),
    so the first element is the most recent.

    Args:
        completions: List of completion dicts from _load_completions().

    Returns:
        Outcome string ("success", "warn", or "fail"), or None if no completions.
    """
    if not completions:
        return None
    return completions[0].get("outcome") or None


def _load_completions(slug: str) -> list[dict]:
    """Return all completions for the given slug from the proxy DB.

    Args:
        slug: Work item slug.

    Returns:
        List of completion dicts, empty list if proxy is unavailable.
    """
    proxy = get_proxy()
    if proxy is None:
        return []
    return proxy.list_completions_by_slug(slug)


def _load_root_traces(slug: str) -> list[dict]:
    """Return root traces whose name contains the given slug.

    Args:
        slug: Work item slug.

    Returns:
        List of dicts with keys: run_id, name, created_at.
    """
    proxy = get_proxy()
    if proxy is None:
        return []
    return proxy.list_root_traces_by_slug(slug)


def _find_plan_yaml(slug: str) -> Optional[Path]:
    """Locate the plan YAML file for the given slug.

    Tries an exact match first, then a prefix glob.

    Args:
        slug: Work item slug.

    Returns:
        Path to the YAML file, or None if not found.
    """
    exact = _PLANS_DIR / f"{slug}.yaml"
    if exact.exists():
        return exact
    matches = sorted(_PLANS_DIR.glob(f"{slug}*.yaml"))
    return matches[0] if matches else None


def _find_design_doc(slug: str) -> Optional[Path]:
    """Locate the design document for the given slug.

    Checks workspace first, then falls back to docs/plans/ glob.

    Args:
        slug: Work item slug.

    Returns:
        Path to the design doc, or None if not found.
    """
    # Check workspace first
    ws_design = ws_path_fn(slug) / "design.md"
    if ws_design.exists():
        return ws_design
    # Fallback to legacy location
    matches = sorted(_DESIGN_DOCS_DIR.glob(f"*-{slug}-design.md"))
    return matches[0] if matches else None


def _is_active_task_validation(slug: str) -> bool:
    """Return True if the current in_progress plan task is a validation task.

    Checks whether the in_progress task's agent is "validator" or the task
    name contains "validat" (case-insensitive).

    Args:
        slug: Work item slug.

    Returns:
        True when the active task is validation, False otherwise.
    """
    plan_tasks = _load_plan_tasks(slug)
    if not plan_tasks:
        return False
    for task in plan_tasks:
        if task.get("status") == "in_progress":
            if task.get("agent") == "validator" or "validat" in task.get("name", "").lower():
                return True
    return False


def _derive_pipeline_stage(slug: str, completions: list[dict]) -> str:
    """Derive the current pipeline stage of a work item.

    Checks the full waterfall: active worker → completed backlog → claimed
    state → plan/design docs → backlog presence. The "stuck" sub-stage is
    returned when all prior completions failed and the item is still pending.

    Args:
        slug: Work item slug.
        completions: List of completion records for this slug.

    Returns:
        One of "executing", "completed", "planning", "claimed", "designing",
        "queued", "stuck", or "unknown".
    """
    # 1. Active worker → validating or executing
    try:
        from langgraph_pipeline.web.dashboard_state import get_dashboard_state
        state = get_dashboard_state()
        for worker in state.active_workers.values():
            if worker.slug == slug:
                if _is_active_task_validation(slug):
                    return _STAGE_VALIDATING
                return _STAGE_EXECUTING
    except Exception:
        pass

    all_failed = bool(completions) and all(
        c.get("outcome") != "success" for c in completions
    )

    # 2. Item in completed backlog → completed
    for dir_str in COMPLETED_DIRS.values():
        if (Path(dir_str) / f"{slug}.md").exists():
            return _STAGE_COMPLETED

    # 3–5. Item in .claimed
    claimed_file = _CLAIMED_PATH / f"{slug}.md"
    if claimed_file.exists():
        if all_failed:
            return _STAGE_STUCK
        if _find_plan_yaml(slug) is not None:
            return _STAGE_EXECUTING
        if _find_design_doc(slug) is not None:
            return _STAGE_PLANNING
        return _STAGE_CLAIMED

    # 6. Plan YAML exists → executing
    if _find_plan_yaml(slug) is not None:
        return _STAGE_EXECUTING

    # 7. Design doc exists → designing
    if _find_design_doc(slug) is not None:
        return _STAGE_DESIGNING

    # 8. Item in backlog dir → queued (or stuck)
    if _find_requirements_file(slug) is not None:
        return _STAGE_STUCK if all_failed else _STAGE_QUEUED

    # 9. Otherwise → unknown
    return _STAGE_UNKNOWN


def _list_output_files(slug: str) -> list[str]:
    """List log filenames from worker-output and workspace logs for the given slug.

    Args:
        slug: Work item slug.

    Returns:
        Sorted deduplicated list of ``.log`` filenames, newest first.
    """
    seen: set[str] = set()
    logs: list[str] = []

    for log_dir in [WORKER_OUTPUT_DIR / slug, ws_path_fn(slug) / "logs"]:
        if not log_dir.is_dir():
            continue
        for p in log_dir.iterdir():
            if p.suffix == ".log" and p.name not in seen:
                seen.add(p.name)
                logs.append(p.name)

    return sorted(logs, reverse=True)


def _load_validation_results(slug: str) -> list[dict]:
    """Load validation result JSON files from worker-output and workspace."""
    seen_names: set[str] = set()
    results: list[dict] = []

    for val_dir in [WORKER_OUTPUT_DIR / slug, ws_path_fn(slug) / "validation"]:
        if not val_dir.exists():
            continue
        for f in sorted(val_dir.glob("validation-*.json"), reverse=True):
            if f.name in seen_names:
                continue
            seen_names.add(f.name)
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append(data)
            except (json.JSONDecodeError, OSError):
                continue

    return sorted(results, key=lambda r: r.get("timestamp", ""), reverse=True)


def _compute_total_tokens(completions: list[dict]) -> int:
    """Estimate total tokens from completions using velocity * duration."""
    total = 0
    for c in completions:
        tpm = c.get("tokens_per_minute", 0) or 0
        dur = c.get("duration_s", 0) or 0
        if tpm > 0 and dur > 0:
            total += int(tpm * dur / 60.0)
    return total


def _compute_avg_velocity(completions: list[dict]) -> Optional[float]:
    """Compute average tokens-per-minute across completions that have a value.

    Args:
        completions: List of completion dicts, each optionally containing
            ``tokens_per_minute``.

    Returns:
        Average tokens/min rounded to the nearest integer, or None when no
        completions carry velocity data.
    """
    values = [
        c["tokens_per_minute"]
        for c in completions
        if c.get("tokens_per_minute") is not None
    ]
    if not values:
        return None
    return round(sum(values) / len(values))


def _parse_verification_notes(completions: list[dict]) -> None:
    """Parse verification_notes JSON strings into structured dicts in-place.

    Each completion dict gains a ``verification_data`` key containing the parsed
    JSON (with keys verdict, findings, evidence), or None if the field is absent
    or unparseable.

    Args:
        completions: List of completion dicts (modified in-place).
    """
    for c in completions:
        raw = c.get("verification_notes")
        if raw and isinstance(raw, str):
            try:
                c["verification_data"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                c["verification_data"] = None
        else:
            c["verification_data"] = None


_REPORT_PATH_PATTERN = re.compile(r"docs/reports/[\w./-]+\.(?:md|json|csv|txt|html)")


def _add_report_refs_from_file(
    doc_path: Path, add_fn: "Callable[[str, str], None]"
) -> None:
    """Scan a document for docs/reports/ path references and add existing ones.

    Parses the text content of *doc_path* for paths matching docs/reports/*.
    Each path that exists on disk is added via *add_fn* with source "report".

    Args:
        doc_path: Path to the document to scan (typically a design doc).
        add_fn: Callback that accepts (raw_path, source) to register an artifact.
    """
    try:
        text = doc_path.read_text(encoding="utf-8")
    except Exception:
        return
    for match in _REPORT_PATH_PATTERN.findall(text):
        candidate = Path(match)
        if candidate.exists():
            add_fn(str(candidate), _SOURCE_REPORT)


def _collect_output_artifacts(slug: str) -> list[dict]:
    """Gather output artifacts for a work item from git, design docs, and reports.

    Searches four sources:
    1. Git commits whose message contains the slug (via git log --all --grep).
    2. Design document in docs/plans/ matching the slug.
    3. Files in docs/reports/ whose name contains the slug.
    4. Files in docs/reports/worker-output/<slug>/ (non-log artifacts).

    Deduplicates by resolved absolute path. Enriches each artifact with
    file_size (bytes) and action (created/modified/discovered) from the
    artifact manifest when available.

    Args:
        slug: Work item slug.

    Returns:
        List of dicts with keys: path (str), source (str), display_name (str),
        file_size (int or None), action (str).
    """
    # Build a resolved-path -> action lookup from the manifest
    manifest_by_resolved: dict[str, str] = {}
    for entry in load_manifest(slug):
        try:
            resolved_key = str(Path(entry["path"]).resolve())
        except Exception:
            resolved_key = entry["path"]
        manifest_by_resolved[resolved_key] = entry.get("action", _ACTION_DISCOVERED)

    seen_paths: set[str] = set()
    artifacts: list[dict] = []

    def _add(raw_path: str, source: str) -> None:
        p = Path(raw_path)
        try:
            resolved = str(p.resolve())
        except Exception:
            resolved = raw_path
        if resolved in seen_paths:
            return
        seen_paths.add(resolved)

        file_size: Optional[int] = None
        try:
            if p.exists():
                file_size = p.stat().st_size
        except Exception:
            pass

        action = manifest_by_resolved.get(resolved, _ACTION_DISCOVERED)

        artifacts.append(
            {
                "path": raw_path,
                "source": source,
                "display_name": p.name,
                "file_size": file_size,
                "action": action,
            }
        )

    # 1. Git commits
    try:
        result = subprocess.run(
            ["git", "log", "--all", f"--grep={slug}", "--name-only", "--pretty=format:"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if line and not line.startswith("commit "):
                    if Path(line).exists():
                        _add(line, _SOURCE_GIT)
    except Exception:
        pass

    # 2. Design document
    design_doc = _find_design_doc(slug)
    if design_doc is not None:
        _add(str(design_doc), _SOURCE_DESIGN)

    # 3. Reports directory — files whose name contains the slug
    if _REPORTS_DIR.is_dir():
        for candidate in _REPORTS_DIR.iterdir():
            if candidate.is_file() and slug in candidate.name:
                _add(str(candidate), _SOURCE_REPORT)

    # 3b. Reports referenced inside the design doc (covers outputs like
    #     docs/reports/design-doc-audit.md that don't contain the slug in name)
    if design_doc is not None:
        _add_report_refs_from_file(design_doc, _add)

    # 4. Worker-output non-log artifacts
    worker_output_slug_dir = WORKER_OUTPUT_DIR / slug
    if worker_output_slug_dir.is_dir():
        for candidate in worker_output_slug_dir.iterdir():
            if candidate.is_file() and candidate.suffix != ".log":
                _add(str(candidate), _SOURCE_REPORT)

    # 5. Manifest-only entries (files recorded by workers but not found by discovery)
    for entry in load_manifest(slug):
        entry_path = entry.get("path", "")
        if entry_path:
            _add(entry_path, _SOURCE_GIT)

    return artifacts


def _get_active_worker(slug: str) -> Optional[dict]:
    """Return active worker info for the given slug, or None if not running.

    Scans DashboardState.active_workers for a WorkerInfo whose slug matches.
    Elapsed time is formatted as "Xm Ys" for display.

    Args:
        slug: Work item slug.

    Returns:
        Dict with keys ``pid``, ``elapsed_s``, ``run_id``, or None.
    """
    try:
        from langgraph_pipeline.web.dashboard_state import get_dashboard_state
        state = get_dashboard_state()
        now = time.monotonic()
        for worker in state.active_workers.values():
            if worker.slug == slug:
                elapsed_total = now - worker.start_time
                minutes = int(elapsed_total // 60)
                seconds = int(elapsed_total % 60)
                # Find the current task from the plan YAML
                current_task = None
                plan_tasks = _load_plan_tasks(slug)
                if plan_tasks:
                    for t in plan_tasks:
                        if t["status"] == "in_progress":
                            current_task = f"#{t['id']} {t['name']}"
                            break
                return {
                    "pid": worker.pid,
                    "elapsed_s": f"{minutes}m {seconds}s",
                    "elapsed_raw_s": elapsed_total,
                    "run_id": worker.run_id,
                    "current_task": current_task,
                    "current_velocity": round(worker.current_velocity()),
                    "tokens_in": worker.tokens_in,
                    "tokens_out": worker.tokens_out,
                    "cost_usd": worker.estimated_cost_usd,
                }
    except Exception:
        pass
    return None
