# langgraph_pipeline/web/routes/item.py
# FastAPI router for the GET /item/{slug} work-item detail page.
# Design: docs/plans/2026-03-26-35-work-item-page-missing-requirements-from-backlog-file-design.md
# Design: docs/plans/2026-03-26-43-capture-raw-worker-output-per-item-design.md

"""FastAPI router that serves the work-item detail page.

Endpoints:
    GET /item/{slug}               — Renders item.html with requirements, plan tasks,
                                     completion history, and linked root traces.
    GET /item/{slug}/output/{filename} — Returns a worker log file as text/plain.
"""

import time
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from langgraph_pipeline.shared.paths import (
    BACKLOG_DIRS,
    CLAIMED_DIR,
    COMPLETED_DIRS,
    WORKER_OUTPUT_DIR,
)
from langgraph_pipeline.web.proxy import get_proxy

# ─── Constants ────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_PLANS_DIR = Path(".claude/plans")
_CLAIMED_PATH = Path(CLAIMED_DIR)
_DESIGN_DOCS_DIR = Path("docs/plans")

_STAGE_EXECUTING = "executing"
_STAGE_COMPLETED = "completed"
_STAGE_PLANNING = "planning"
_STAGE_CLAIMED = "claimed"
_STAGE_DESIGNING = "designing"
_STAGE_QUEUED = "queued"
_STAGE_STUCK = "stuck"
_STAGE_UNKNOWN = "unknown"

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
    item_type = _detect_item_type(slug)
    plan_tasks = _load_plan_tasks(slug)
    completions = _load_completions(slug)
    traces = _load_root_traces(slug)
    pipeline_stage = _derive_pipeline_stage(slug, completions)
    active_worker = _get_active_worker(slug)
    total_cost_usd = sum(c.get("cost_usd", 0.0) for c in completions)
    total_duration_s = sum(c.get("duration_s", 0.0) for c in completions)
    total_tokens = _compute_total_tokens(slug)
    output_files = _list_output_files(slug)
    avg_velocity = _compute_avg_velocity(completions)
    if active_worker and active_worker.get("current_velocity", 0) > 0:
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
            "requirements_html": requirements_html,
            "original_request_html": original_request_html,
            "plan_tasks": plan_tasks,
            "completions": completions,
            "traces": traces,
            "output_files": output_files,
            "avg_velocity": avg_velocity,
            "last_trace": last_trace,
        },
    )


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


# ─── Helpers ──────────────────────────────────────────────────────────────────


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
    2. Claimed     — ``.claude/plans/.claimed/<slug>.md``
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
    """Return the original backlog/claimed file when the primary source is a design doc.

    When the highest-priority requirements source is a design doc, the original
    backlog or claimed file is surfaced as a secondary "Original request" block.

    Args:
        slug: Work item slug.

    Returns:
        Path to the original request file, or None if not applicable.
    """
    if _find_design_doc(slug) is None:
        return None

    claimed = _CLAIMED_PATH / f"{slug}.md"
    if claimed.exists():
        return claimed

    for dir_str in BACKLOG_DIRS.values():
        candidate = Path(dir_str) / f"{slug}.md"
        if candidate.exists():
            return candidate

    return None


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
    """Return original backlog/claimed request rendered as HTML, or None if not applicable.

    Only returns content when the primary requirements source is a design doc and
    an original backlog or claimed file also exists.

    Args:
        slug: Work item slug.

    Returns:
        HTML string, or None when not applicable.
    """
    md_path = _find_original_request_file(slug)
    if md_path is None:
        return None
    html = _render_md_to_html(md_path)
    return html if html else None


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
        if not matches:
            return None
        plan_path = matches[0]

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
                }
            )
    return tasks if tasks else None


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
    """Locate the design document for the given slug in docs/plans/.

    Matches files of the form ``docs/plans/*-<slug>-design.md``.

    Args:
        slug: Work item slug.

    Returns:
        Path to the design doc, or None if not found.
    """
    matches = sorted(_DESIGN_DOCS_DIR.glob(f"*-{slug}-design.md"))
    return matches[0] if matches else None


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
    # 1. Active worker → executing
    try:
        from langgraph_pipeline.web.dashboard_state import get_dashboard_state
        state = get_dashboard_state()
        for worker in state.active_workers.values():
            if worker.slug == slug:
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
    """List log filenames in the worker-output directory for the given slug.

    Args:
        slug: Work item slug.

    Returns:
        Sorted list of ``.log`` filenames, newest first (by name, which encodes
        the timestamp). Empty list if the directory does not exist.
    """
    output_dir = WORKER_OUTPUT_DIR / slug
    if not output_dir.is_dir():
        return []
    return sorted(
        (p.name for p in output_dir.iterdir() if p.suffix == ".log"),
        reverse=True,
    )


def _compute_total_tokens(slug: str) -> int:
    """Sum input_tokens + output_tokens from all traces for this slug."""
    try:
        from langgraph_pipeline.web.proxy import get_proxy
        proxy = get_proxy()
        if proxy is None:
            return 0
        with proxy._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(json_extract(metadata_json, '$.input_tokens')), 0) + "
                "COALESCE(SUM(json_extract(metadata_json, '$.output_tokens')), 0) as total "
                "FROM traces WHERE json_extract(metadata_json, '$.item_slug') = ?",
                [slug],
            ).fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0


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
                    "run_id": worker.run_id,
                    "current_task": current_task,
                    "current_velocity": round(worker.current_velocity()),
                }
    except Exception:
        pass
    return None
