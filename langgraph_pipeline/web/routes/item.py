# langgraph_pipeline/web/routes/item.py
# FastAPI router for the GET /item/{slug} work-item detail page.
# Design: docs/plans/2026-03-26-06-work-item-detail-page-design.md

"""FastAPI router that serves the work-item detail page.

Endpoints:
    GET /item/{slug}  — Renders item.html with requirements, plan tasks,
                        completion history, and linked root traces.
"""

from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from langgraph_pipeline.shared.paths import BACKLOG_DIRS, COMPLETED_DIRS
from langgraph_pipeline.web.proxy import get_proxy

# ─── Constants ────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_PLANS_DIR = Path(".claude/plans")

_STATUS_RUNNING = "running"
_STATUS_COMPLETED = "completed"
_STATUS_QUEUED = "queued"
_STATUS_UNKNOWN = "unknown"

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
    item_type = _detect_item_type(slug)
    plan_tasks = _load_plan_tasks(slug)
    completions = _load_completions(slug)
    traces = _load_root_traces(slug)
    status = _derive_status(slug, completions)
    total_cost_usd = sum(c.get("cost_usd", 0.0) for c in completions)

    return templates.TemplateResponse(
        request,
        "item.html",
        {
            "slug": slug,
            "item_type": item_type,
            "status": status,
            "total_cost_usd": total_cost_usd,
            "requirements_html": requirements_html,
            "plan_tasks": plan_tasks,
            "completions": completions,
            "traces": traces,
        },
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _load_requirements_html(slug: str) -> str:
    """Return requirements markdown rendered as HTML, or empty string if not found.

    Scans all backlog and completed directories for a file named ``<slug>.md``.

    Args:
        slug: Work item slug.

    Returns:
        HTML string, or empty string when no file is found.
    """
    md_path = _find_requirements_file(slug)
    if md_path is None:
        return ""
    try:
        import markdown
        text = md_path.read_text(encoding="utf-8")
        return markdown.markdown(text, extensions=["fenced_code", "tables"])
    except Exception:
        return ""


def _find_requirements_file(slug: str) -> Optional[Path]:
    """Locate the ``<slug>.md`` file across all backlog and completed directories.

    Args:
        slug: Work item slug.

    Returns:
        Path to the file, or None if not found.
    """
    search_dirs = list(BACKLOG_DIRS.values()) + list(COMPLETED_DIRS.values())
    for dir_str in search_dirs:
        candidate = Path(dir_str) / f"{slug}.md"
        if candidate.exists():
            return candidate
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


def _derive_status(slug: str, completions: list[dict]) -> str:
    """Derive the current status of a work item.

    Checks active-worker state via dashboard_state, then falls back to
    completion history and plan file presence.

    Args:
        slug: Work item slug.
        completions: List of completion records for this slug.

    Returns:
        One of "running", "completed", "queued", "unknown".
    """
    try:
        from langgraph_pipeline.web.dashboard_state import get_dashboard_state
        state = get_dashboard_state()
        active_slugs = {w.get("slug") for w in (state.get("active_workers") or [])}
        if slug in active_slugs:
            return _STATUS_RUNNING
    except Exception:
        pass

    if completions:
        return _STATUS_COMPLETED

    if (_PLANS_DIR / f"{slug}.yaml").exists():
        return _STATUS_QUEUED

    if _find_requirements_file(slug) is not None:
        return _STATUS_QUEUED

    return _STATUS_UNKNOWN
