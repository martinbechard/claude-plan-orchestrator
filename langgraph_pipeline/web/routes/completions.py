# langgraph_pipeline/web/routes/completions.py
# FastAPI router for the /completions paginated history page.
# Design: docs/plans/2026-03-26-07-completions-paged-table-design.md

"""Read-only FastAPI router that serves the full completions history page.

Endpoints:
    GET /completions  — Paginated completions table with filters and summary stats.
                        Returns HTTP 404 when the proxy is disabled.
"""

import math
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from langgraph_pipeline.web.proxy import get_proxy

# ─── Constants ────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

HTTP_NOT_FOUND = 404
DEFAULT_PAGE_SIZE = 50

# ─── Jinja2 Setup ─────────────────────────────────────────────────────────────

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter()

# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/completions", response_class=HTMLResponse)
def completions(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=500),
    slug: Optional[str] = Query(default=""),
    outcome: Optional[str] = Query(default=""),
    date_from: Optional[str] = Query(default=""),
    date_to: Optional[str] = Query(default=""),
) -> HTMLResponse:
    """Render the paginated completions history page.

    Shows all work-item completions with optional filters for slug substring,
    outcome, and date range. Includes summary stats (total count by outcome,
    total cost) that always reflect the active filter set.

    Args:
        request: Starlette request required by Jinja2TemplateResponse.
        page: 1-based page number.
        page_size: Rows per page (1–500, default 50).
        slug: Substring filter on slug (case-insensitive).
        outcome: Exact outcome filter ("success", "warn", "fail", or "").
        date_from: ISO date lower bound for finished_at (inclusive).
        date_to: ISO date upper bound for finished_at (inclusive).

    Returns:
        Rendered completions.html template.

    Raises:
        HTTPException: 404 when the tracing proxy is disabled.
    """
    proxy = get_proxy()
    if proxy is None:
        raise HTTPException(status_code=HTTP_NOT_FOUND, detail="Proxy not enabled")

    slug = slug or ""
    outcome = outcome or ""
    date_from = date_from or ""
    date_to = date_to or ""

    total_count = proxy.count_completions(
        slug=slug, outcome=outcome, date_from=date_from, date_to=date_to
    )
    total_pages = max(1, math.ceil(total_count / page_size))
    page = min(page, total_pages)

    rows = proxy.list_completions(
        page=page,
        page_size=page_size,
        slug=slug,
        outcome=outcome,
        date_from=date_from,
        date_to=date_to,
    )

    success_count = proxy.count_completions(
        slug=slug, outcome="success", date_from=date_from, date_to=date_to
    )
    warn_count = proxy.count_completions(
        slug=slug, outcome="warn", date_from=date_from, date_to=date_to
    )
    fail_count = proxy.count_completions(
        slug=slug, outcome="fail", date_from=date_from, date_to=date_to
    )
    total_cost_usd = proxy.sum_completions_cost(
        slug=slug, outcome=outcome, date_from=date_from, date_to=date_to
    )

    return templates.TemplateResponse(
        request,
        "completions.html",
        {
            "rows": rows,
            "page": page,
            "total_pages": total_pages,
            "slug": slug,
            "outcome": outcome,
            "date_from": date_from,
            "date_to": date_to,
            "total_count": total_count,
            "success_count": success_count,
            "warn_count": warn_count,
            "fail_count": fail_count,
            "total_cost_usd": total_cost_usd,
        },
    )
