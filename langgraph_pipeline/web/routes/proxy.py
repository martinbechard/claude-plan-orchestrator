# langgraph_pipeline/web/routes/proxy.py
# FastAPI router for the /proxy trace list and detail endpoints.
# Design: docs/plans/2026-03-25-14-langsmith-tracing-proxy-design.md
# Design: docs/plans/2026-03-26-04-timeline-duplicate-labels-and-elapsed-time-design.md

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


ELAPSED_FALLBACK_DURATION_S = 1.0


def _compute_elapsed(child: dict, root_start: datetime) -> dict:
    """Add elapsed_start_s and elapsed_end_s (floats) to a child run dict.

    Both values are seconds from root_start to child start/end respectively.
    If the child has no end_time, elapsed_end_s = elapsed_start_s + ELAPSED_FALLBACK_DURATION_S.
    """
    child = dict(child)
    child_start = _parse_iso(child.get("start_time"))
    child_end = _parse_iso(child.get("end_time"))

    if child_start is None:
        child["elapsed_start_s"] = 0.0
        child["elapsed_end_s"] = ELAPSED_FALLBACK_DURATION_S
        return child

    elapsed_start = (child_start - root_start).total_seconds()
    child["elapsed_start_s"] = max(0.0, elapsed_start)

    if child_end is not None:
        elapsed_end = (child_end - root_start).total_seconds()
        child["elapsed_end_s"] = max(child["elapsed_start_s"], elapsed_end)
    else:
        child["elapsed_end_s"] = child["elapsed_start_s"] + ELAPSED_FALLBACK_DURATION_S

    return child


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
    run["display_model"] = run.get("model") or ""
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
    trace_id: str = Query(default=""),
) -> HTMLResponse:
    """Render the paginated trace list with optional filters.

    Args:
        request: Starlette request (required by Jinja2TemplateResponse).
        page: 1-based page number.
        slug: Optional substring filter on run name.
        model: Optional model string filter.
        date_from: Optional ISO date lower bound for created_at.
        date_to: Optional ISO date upper bound for created_at.
        trace_id: Optional run_id prefix filter.

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
        trace_id=trace_id,
    )
    runs = [_enrich_run(r) for r in raw_runs]

    # Child run counts in a single batch query
    run_ids = [r["run_id"] for r in runs if r.get("run_id")]
    child_counts = proxy.count_children_batch(run_ids)
    for run in runs:
        run["child_count"] = child_counts.get(run.get("run_id", ""), 0)

    # Total pages for pagination
    total_count = proxy.count_runs(
        slug=slug, model=model, date_from=date_from, date_to=date_to, trace_id=trace_id
    )
    total_pages = max(1, math.ceil(total_count / PAGE_SIZE_DEFAULT))

    return templates.TemplateResponse(
        request,
        "proxy_list.html",
        {
            "runs": runs,
            "page": page,
            "total_pages": total_pages,
            "slug": slug,
            "model": model,
            "date_from": date_from,
            "date_to": date_to,
            "trace_id": trace_id,
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
    enriched_run = _enrich_run(run)

    root_start = _parse_iso(run.get("start_time"))
    if root_start is None:
        root_start = datetime.fromtimestamp(0, tz=timezone.utc)

    enriched_children = [
        _compute_elapsed(_enrich_run(c), root_start) for c in children
    ]

    span_s = 0.0
    if enriched_children:
        span_s = max(c["elapsed_end_s"] for c in enriched_children)

    child_ids = [c["run_id"] for c in enriched_children if c.get("run_id")]
    grandchild_counts = proxy.count_children_batch(child_ids)

    return templates.TemplateResponse(
        request,
        "proxy_trace.html",
        {
            "run": enriched_run,
            "children": enriched_children,
            "span_s": span_s,
            "grandchild_counts": grandchild_counts,
        },
    )
