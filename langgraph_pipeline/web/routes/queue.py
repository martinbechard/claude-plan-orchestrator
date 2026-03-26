# langgraph_pipeline/web/routes/queue.py
# FastAPI router for the backlog queue page: HTML page and JSON data endpoint.
# Design: docs/plans/2026-03-26-05-queue-page-design.md

"""FastAPI router that serves the read-only backlog queue page.

Endpoints:
    GET /queue       — Renders queue.html via Jinja2Templates.
    GET /api/queue   — Returns {"items": [...]} JSON for client-side polling.
"""

import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

# ─── Constants ────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

BACKLOG_DIRECTORIES: list[tuple[str, str]] = [
    ("analysis", "docs/analysis-backlog"),
    ("defect", "docs/defect-backlog"),
    ("feature", "docs/feature-backlog"),
]

# ─── Jinja2 Setup ─────────────────────────────────────────────────────────────

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter()

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _collect_queue_items() -> list[dict]:
    """Scan backlog directories and return sorted queue items.

    Each item contains slug, item_type, mtime, age_seconds, and content.
    Sorted by item_type alphabetical, then age_seconds descending (oldest first).
    Missing directories are skipped silently.

    Returns:
        List of queue item dicts ready for JSON serialisation.
    """
    now = time.time()
    items: list[dict] = []

    for item_type, rel_dir in BACKLOG_DIRECTORIES:
        directory = _PROJECT_ROOT / rel_dir
        if not directory.is_dir():
            continue
        for md_file in directory.glob("*.md"):
            try:
                stat = md_file.stat()
                mtime = stat.st_mtime
                age_seconds = int(now - mtime)
                content = md_file.read_text(encoding="utf-8", errors="replace")
                items.append(
                    {
                        "slug": md_file.stem,
                        "item_type": item_type,
                        "mtime": mtime,
                        "age_seconds": age_seconds,
                        "content": content,
                    }
                )
            except OSError:
                continue

    items.sort(key=lambda x: (x["item_type"], -x["age_seconds"]))
    return items


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/queue", response_class=HTMLResponse)
def queue_page(request: Request) -> HTMLResponse:
    """Render the backlog queue page.

    Args:
        request: Starlette request required by Jinja2TemplateResponse.

    Returns:
        Rendered queue.html template.
    """
    return templates.TemplateResponse(request, "queue.html")


@router.get("/api/queue")
def queue_data() -> JSONResponse:
    """Return all backlog queue items as JSON.

    Returns:
        JSONResponse with {"items": [...]} where each item contains slug,
        item_type, mtime, age_seconds, and content fields.
    """
    items = _collect_queue_items()
    return JSONResponse({"items": items})
