# langgraph_pipeline/web/routes/proxy.py
# FastAPI router for the /proxy trace list and detail endpoints.
# Design: docs/plans/2026-03-25-14-langsmith-tracing-proxy-design.md

"""Read-only FastAPI router that serves the LangSmith trace proxy UI.

Endpoints:
    GET /proxy              — Paginated trace list with optional filters.
    GET /proxy/{run_id}     — Trace detail with child run timeline.

Both endpoints return HTTP 404 when the proxy is disabled (get_proxy() is None).
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from langgraph_pipeline.web.proxy import PAGE_SIZE_DEFAULT, get_proxy

# ─── Constants ────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

HTTP_NOT_FOUND = 404

# ─── Jinja2 Setup ─────────────────────────────────────────────────────────────

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _fromjson(value: Optional[str]) -> Optional[dict]:
    """Jinja2 filter: parse a JSON string into a Python dict (or None on failure)."""
    if not value:
        return None
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return None


templates.env.filters["fromjson"] = _fromjson

# ─── Setup ────────────────────────────────────────────────────────────────────

router = APIRouter()

# ─── Helpers ──────────────────────────────────────────────────────────────────

_ISO_FMT = "%Y-%m-%dT%H:%M:%S"
_ISO_FMT_WITH_TZ = "%Y-%m-%dT%H:%M:%S%z"


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string to a datetime, returning None on error."""
    if not ts:
        return None
    for fmt in (_ISO_FMT_WITH_TZ, _ISO_FMT):
        try:
            return datetime.strptime(ts[:19], _ISO_FMT).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _format_duration(start: Optional[str], end: Optional[str]) -> str:
    """Return a human-readable duration string (e.g. '1.23 s' or '2m 05s')."""
    dt_start = _parse_iso(start)
    dt_end = _parse_iso(end)
    if dt_start is None or dt_end is None:
        return "—"
    delta = (dt_end - dt_start).total_seconds()
    if delta < 0:
        return "—"
    if delta < 60:
        return f"{delta:.2f}s"
    minutes = int(delta // 60)
    seconds = int(delta % 60)
    return f"{minutes}m {seconds:02d}s"


def _enrich_run(run: dict) -> dict:
    """Add pre-computed display fields to a run dict for template rendering.

    Adds: display_duration, display_slug, display_model, display_cost.
    """
    run = dict(run)
    run["display_duration"] = _format_duration(run.get("start_time"), run.get("end_time"))

    meta: dict = {}
    if run.get("metadata_json"):
        try:
            meta = json.loads(run["metadata_json"])
        except (ValueError, TypeError):
            meta = {}

    run["display_slug"] = meta.get("slug") or meta.get("item_slug") or ""
    run["display_model"] = meta.get("model") or meta.get("model_name") or ""
    cost = meta.get("cost") or meta.get("total_cost")
    run["display_cost"] = f"~${float(cost):.4f}" if cost is not None else ""
    return run


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

    raw_runs = proxy.list_runs(
        page=page,
        slug=slug,
        model=model,
        date_from=date_from,
        date_to=date_to,
    )
    runs = [_enrich_run(r) for r in raw_runs]

    # Child run counts in a single batch query
    run_ids = [r["run_id"] for r in runs if r.get("run_id")]
    child_counts = proxy.count_children_batch(run_ids)
    for run in runs:
        run["child_count"] = child_counts.get(run.get("run_id", ""), 0)

    # Total pages for pagination
    total_count = proxy.count_runs(
        slug=slug, model=model, date_from=date_from, date_to=date_to
    )
    total_pages = max(1, math.ceil(total_count / PAGE_SIZE_DEFAULT))

    return templates.TemplateResponse(
        "proxy_list.html",
        {
            "request": request,
            "runs": runs,
            "page": page,
            "total_pages": total_pages,
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
            "run": _enrich_run(run),
            "children": [_enrich_run(c) for c in children],
        },
    )
