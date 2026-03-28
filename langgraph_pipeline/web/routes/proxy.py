# langgraph_pipeline/web/routes/proxy.py
# FastAPI router for the /proxy trace list and detail endpoints.
# Design: docs/plans/2026-03-25-14-langsmith-tracing-proxy-design.md
# Design: docs/plans/2026-03-26-04-timeline-duplicate-labels-and-elapsed-time-design.md
# Design: docs/plans/2026-03-26-16-tool-calls-missing-from-traces-design.md

"""Read-only FastAPI router that serves the LangSmith trace proxy UI.

Endpoints:
    GET /proxy              — Paginated trace list with optional filters.
    GET /proxy/{run_id}     — Trace detail with child run timeline.

Both endpoints return HTTP 404 when the proxy is disabled (get_proxy() is None).
"""

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from langgraph_pipeline.web.helpers.trace_narrative import build_execution_view
from langgraph_pipeline.web.proxy import PAGE_SIZE_DEFAULT, ChildTimeSpan, get_proxy

# ─── Constants ────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Logs directory relative to the project root (four levels above this file).
_LOGS_DIR = Path(__file__).parent.parent.parent.parent / "logs"

HTTP_NOT_FOUND = 404

# Runs with no end_time whose start_time is older than this many minutes are
# shown as "stale" rather than "running" on the list page.
_STALE_RUN_THRESHOLD_MINUTES = 30

# Root run durations below this threshold (seconds) are treated as near-zero and
# replaced with the child-aggregated span when child data is available.
# LangSmith root runs often record 0.01s because the SDK emits two events
# (start and end) that are nearly simultaneous at the graph level.
_NEAR_ZERO_DURATION_S = 1.0


# ─── Child Aggregation ────────────────────────────────────────────────────────


@dataclass
class ChildAggregation:
    """Child-aggregated values for a single root run, used by _enrich_run.

    Bundles all four child-derived fields so _enrich_run stays at two
    parameters (run + child_agg).
    """

    time_span: Optional[ChildTimeSpan]
    cost: Optional[float]
    model: Optional[str]
    slug: Optional[str]


@dataclass
class RunGroup:
    """A group of runs sharing the same display_slug for grouped list view.

    Members are ordered most-recent-first (created_at DESC) because list_runs
    returns rows in that order. The summary is the first member — the most
    recent run for this slug.
    """

    display_slug: str
    summary: dict  # most recent run — shown in the collapsed group row
    members: list[dict]  # all runs in the group


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


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string to a datetime, returning None on error.

    Uses datetime.fromisoformat() to preserve fractional seconds (microseconds).
    The tzinfo is normalised to UTC regardless of the offset in the string.
    """
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    except ValueError:
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


def _compute_display_status(run: dict) -> str:
    """Return display status string, correcting stale RUNNING runs.

    Without children data, uses a time-based heuristic: runs with no end_time
    that started more than _STALE_RUN_THRESHOLD_MINUTES ago are labeled "stale".
    """
    if run.get("error"):
        return "error"
    if run.get("end_time"):
        return "completed"
    start = _parse_iso(run.get("start_time"))
    if start:
        elapsed_minutes = (
            (datetime.now(timezone.utc) - start).total_seconds() / 60
        )
        if elapsed_minutes > _STALE_RUN_THRESHOLD_MINUTES:
            return "stale"
    return "running"


def _enrich_run(run: dict, child_agg: Optional[ChildAggregation] = None) -> dict:
    """Add pre-computed display fields to a run dict for template rendering.

    Adds: display_duration, display_slug, display_model, display_cost, display_status.
    When child_agg is provided, child-aggregated values replace root-row data
    that is missing or near-zero (duration < _NEAR_ZERO_DURATION_S, empty model,
    missing cost, or "LangGraph" slug).

    Args:
        run: Raw trace row dict from the database.
        child_agg: Optional batch-aggregated child values for this run_id.
    """
    run = dict(run)

    meta: dict = {}
    if run.get("metadata_json"):
        try:
            meta = json.loads(run["metadata_json"])
        except (ValueError, TypeError):
            meta = {}

    # display_duration: prefer child span when root is missing or near-zero
    root_start = _parse_iso(run.get("start_time"))
    root_end = _parse_iso(run.get("end_time"))
    use_child_span = False
    if child_agg and child_agg.time_span:
        if root_start is None or root_end is None:
            use_child_span = True
        else:
            root_delta = (root_end - root_start).total_seconds()
            use_child_span = root_delta < _NEAR_ZERO_DURATION_S
    if use_child_span and child_agg and child_agg.time_span:
        run["display_duration"] = _format_duration(
            child_agg.time_span.earliest_start, child_agg.time_span.latest_end
        )
    else:
        run["display_duration"] = _format_duration(run.get("start_time"), run.get("end_time"))

    # display_slug: prefer child slug when root is "LangGraph" or empty
    raw_name = run.get("name", "")
    meta_slug = meta.get("slug") or meta.get("item_slug") or ""
    display_slug = meta_slug or (raw_name if raw_name != "LangGraph" else "")
    if not display_slug and child_agg and child_agg.slug:
        display_slug = child_agg.slug
    run["display_slug"] = display_slug

    # display_model: prefer child model when root is empty
    root_model = run.get("model") or ""
    if not root_model and child_agg and child_agg.model:
        root_model = child_agg.model
    run["display_model"] = root_model

    # display_cost: prefer child cost when root metadata carries no cost
    root_cost = meta.get("cost") or meta.get("total_cost")
    if root_cost is not None:
        run["display_cost"] = f"${float(root_cost):.4f}"
    elif child_agg and child_agg.cost is not None:
        run["display_cost"] = f"${child_agg.cost:.4f}"
    else:
        run["display_cost"] = ""

    run["display_status"] = _compute_display_status(run)
    return run


def _find_worker_logs(slug: str) -> list[str]:
    """Return log file names under logs/ whose name contains the item slug.

    Scans _LOGS_DIR for files where the slug substring appears in the filename.
    Returns just the filenames (not full paths) sorted alphabetically.

    Args:
        slug: Work item slug to search for, e.g. "03-add-dark-mode".

    Returns:
        Sorted list of matching log filenames, empty when none found.
    """
    if not slug or not _LOGS_DIR.exists():
        return []
    slug_key = slug.lower()
    return sorted(
        p.name
        for p in _LOGS_DIR.iterdir()
        if p.is_file() and slug_key in p.name.lower()
    )


def _group_runs_by_slug(runs: list[dict]) -> list[RunGroup]:
    """Group enriched runs by display_slug for the grouped list view.

    Runs arrive ordered by created_at DESC. Within each group the first run
    becomes the summary (most recent execution). Runs whose display_slug is
    empty each form their own single-run group keyed by run_id, keeping them
    individually visible.

    Args:
        runs: Enriched run dicts with display_slug set by _enrich_run.

    Returns:
        List of RunGroup objects ordered by most recent summary run.
    """
    seen: dict[str, RunGroup] = {}
    order: list[str] = []

    for run in runs:
        slug = run.get("display_slug") or ""
        key = slug if slug else (run.get("run_id") or str(id(run)))
        if key not in seen:
            seen[key] = RunGroup(
                display_slug=slug,
                summary=run,
                members=[run],
            )
            order.append(key)
        else:
            seen[key].members.append(run)

    return [seen[k] for k in order]


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
    group: int = Query(default=0, ge=0, le=1),
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
        group: When 1, collapse runs with the same display_slug into groups.

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
    run_ids = [r["run_id"] for r in raw_runs if r.get("run_id")]

    # Batch-aggregate child data for the entire page in four queries
    child_time_spans = proxy.get_child_time_spans_batch(run_ids)
    child_costs = proxy.get_child_costs_batch(run_ids)
    child_models = proxy.get_child_models_batch(run_ids)
    child_slugs = proxy.get_child_slugs_batch(run_ids)

    runs = []
    for r in raw_runs:
        rid = r.get("run_id", "")
        child_agg = ChildAggregation(
            time_span=child_time_spans.get(rid),
            cost=child_costs.get(rid),
            model=child_models.get(rid),
            slug=child_slugs.get(rid),
        )
        runs.append(_enrich_run(r, child_agg))

    # Child run counts in a single batch query (run_ids already computed above)
    child_counts = proxy.count_children_batch(run_ids)
    for run in runs:
        run["child_count"] = child_counts.get(run.get("run_id", ""), 0)

    # Total pages for pagination
    total_count = proxy.count_runs(
        slug=slug, model=model, date_from=date_from, date_to=date_to, trace_id=trace_id
    )
    total_pages = max(1, math.ceil(total_count / PAGE_SIZE_DEFAULT))

    groups = _group_runs_by_slug(runs) if group else []

    return templates.TemplateResponse(
        request,
        "proxy_list.html",
        {
            "runs": runs,
            "groups": groups,
            "grouped": bool(group),
            "group": group,
            "page": page,
            "total_pages": total_pages,
            "slug": slug,
            "model": model,
            "date_from": date_from,
            "date_to": date_to,
            "trace_id": trace_id,
        },
    )


@router.get("/proxy/{run_id}/narrative", response_class=HTMLResponse)
def proxy_narrative(request: Request, run_id: str) -> HTMLResponse:
    """Render the item-centric execution narrative page for a pipeline run.

    Args:
        request: Starlette request (required by Jinja2TemplateResponse).
        run_id: Identifier of the root run to display.

    Returns:
        Rendered proxy_narrative.html template with ExecutionView data.

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
    child_ids = [c["run_id"] for c in children if c.get("run_id")]
    grandchild_counts = proxy.count_children_batch(child_ids)
    grandchildren = proxy.get_children_batch(
        [cid for cid in child_ids if grandchild_counts.get(cid, 0) > 0]
    )

    view = build_execution_view(run, children, grandchildren)
    worker_logs = _find_worker_logs(view.item_slug)

    return templates.TemplateResponse(
        request,
        "proxy_narrative.html",
        {
            "run": _enrich_run(run),
            "view": view,
            "worker_logs": worker_logs,
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

    child_ids = [c["run_id"] for c in enriched_children if c.get("run_id")]
    grandchild_counts = proxy.count_children_batch(child_ids)

    raw_grandchildren = proxy.get_children_batch(
        [cid for cid in child_ids if grandchild_counts.get(cid, 0) > 0]
    )
    grandchildren_by_parent: dict[str, list[dict]] = {
        parent_id: [_compute_elapsed(_enrich_run(gc), root_start) for gc in gcs]
        for parent_id, gcs in raw_grandchildren.items()
    }

    all_items = enriched_children + [
        gc for gcs in grandchildren_by_parent.values() for gc in gcs
    ]
    span_s = max(c["elapsed_end_s"] for c in all_items) if all_items else 0.0

    return templates.TemplateResponse(
        request,
        "proxy_trace.html",
        {
            "run": enriched_run,
            "children": enriched_children,
            "span_s": span_s,
            "grandchild_counts": grandchild_counts,
            "grandchildren_by_parent": grandchildren_by_parent,
        },
    )
