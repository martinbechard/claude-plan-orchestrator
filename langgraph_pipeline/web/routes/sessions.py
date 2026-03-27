# langgraph_pipeline/web/routes/sessions.py
# FastAPI router for GET /sessions (HTML) and GET /api/sessions (JSON) endpoints.
# Design: tmp/plans/.claimed/15-session-tracking-and-cost-history.md

"""FastAPI router that serves the session history page and JSON API.

Endpoints:
    GET /sessions      — HTML page showing past sessions and daily cost totals.
    GET /api/sessions  — JSON with sessions list and daily totals.
"""

import logging
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from langgraph_pipeline.web.proxy import get_proxy

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

HTTP_NOT_FOUND = 404

# ─── Jinja2 Setup ─────────────────────────────────────────────────────────────

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter()

# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/sessions", response_class=HTMLResponse)
def sessions_page(request: Request) -> HTMLResponse:
    """Render the session history page with sessions and daily totals tables.

    Args:
        request: Starlette request required by Jinja2TemplateResponse.

    Returns:
        Rendered sessions.html template.

    Raises:
        HTTPException: 404 when the tracing proxy is disabled.
    """
    proxy = get_proxy()
    if proxy is None:
        raise HTTPException(status_code=HTTP_NOT_FOUND, detail="Proxy not enabled")

    session_list = proxy.list_sessions()
    daily_totals = proxy.list_daily_totals()

    return templates.TemplateResponse(
        request,
        "sessions.html",
        {
            "sessions": session_list,
            "daily_totals": daily_totals,
        },
    )


@router.get("/api/sessions")
def api_sessions() -> JSONResponse:
    """Return sessions list and daily totals as JSON.

    Returns:
        JSON object with "sessions" (list of session records) and
        "daily_totals" (list of daily aggregated totals).

    Raises:
        HTTPException: 404 when the tracing proxy is disabled.
    """
    proxy = get_proxy()
    if proxy is None:
        raise HTTPException(status_code=HTTP_NOT_FOUND, detail="Proxy not enabled")

    session_list = proxy.list_sessions()
    daily_totals = proxy.list_daily_totals()

    return JSONResponse(
        {
            "sessions": [asdict(s) for s in session_list],
            "daily_totals": [asdict(d) for d in daily_totals],
        }
    )
