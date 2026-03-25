# langgraph_pipeline/web/routes/proxy.py
# FastAPI router for the /proxy trace list and detail endpoints.
# Design: docs/plans/2026-03-25-14-langsmith-tracing-proxy-design.md

"""Read-only FastAPI router that serves the LangSmith trace proxy UI.

Endpoints:
    GET /proxy              — Paginated trace list with optional filters.
    GET /proxy/{run_id}     — Trace detail with child run timeline.

Both endpoints return HTTP 404 when the proxy is disabled (get_proxy() is None).
"""

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

# ─── Setup ────────────────────────────────────────────────────────────────────

router = APIRouter()

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/proxy", response_class=HTMLResponse)
def proxy_list(
    request: Request,
    page: int = Query(default=1, ge=1),
    slug: str = Query(default=""),
    model: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
) -> HTMLResponse:
    """Render the paginated trace list with optional filters.

    Args:
        request: Starlette request (required by Jinja2TemplateResponse).
        page: 1-based page number.
        slug: Optional substring filter on run name.
        model: Optional model string filter.
        date_from: Optional ISO date lower bound for created_at.
        date_to: Optional ISO date upper bound for created_at.

    Returns:
        Rendered proxy_list.html template.

    Raises:
        HTTPException: 404 when the proxy is disabled.
    """
    proxy = get_proxy()
    if proxy is None:
        raise HTTPException(status_code=HTTP_NOT_FOUND, detail="Proxy not enabled")

    runs = proxy.list_runs(
        page=page,
        slug=slug,
        model=model,
        date_from=date_from,
        date_to=date_to,
    )
    return templates.TemplateResponse(
        "proxy_list.html",
        {
            "request": request,
            "runs": runs,
            "page": page,
            "slug": slug,
            "model": model,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@router.get("/proxy/{run_id}", response_class=HTMLResponse)
def proxy_trace(request: Request, run_id: str) -> HTMLResponse:
    """Render the trace detail page with child run timeline.

    Args:
        request: Starlette request (required by Jinja2TemplateResponse).
        run_id: Identifier of the root run to display.

    Returns:
        Rendered proxy_trace.html template.

    Raises:
        HTTPException: 404 when the proxy is disabled or run not found.
    """
    proxy = get_proxy()
    if proxy is None:
        raise HTTPException(status_code=HTTP_NOT_FOUND, detail="Proxy not enabled")

    run = proxy.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=HTTP_NOT_FOUND, detail=f"Run not found: {run_id}")

    children = proxy.get_children(run_id)
    return templates.TemplateResponse(
        "proxy_trace.html",
        {
            "request": request,
            "run": run,
            "children": children,
        },
    )
