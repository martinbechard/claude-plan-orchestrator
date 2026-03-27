# langgraph_pipeline/web/routes/analysis.py
# FastAPI router for the /analysis trace-based cost analysis page.
# Design: docs/plans/2026-03-26-10-trace-cost-analysis-page-design.md

"""FastAPI router that serves the trace-based cost analysis page.

Endpoints:
    GET /analysis  — Renders analysis.html with cost summary cards, SVG bar
                     chart, paginated top-runs table, and aggregated cost tables.
                     Accepts query params: slug, item_type, date_from, date_to,
                     sort, page.
"""

import math
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from langgraph_pipeline.web.cost_log_reader import svg_bar_chart
from langgraph_pipeline.web.proxy import (
    COST_SORT_DATE_DESC,
    COST_SORT_EXCLUSIVE_DESC,
    COST_SORT_INCLUSIVE_DESC,
    get_proxy,
)

# ─── Constants ────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

HTTP_NOT_FOUND = 404
DEFAULT_PAGE_SIZE = 50
SVG_CHART_WIDTH = 700
SVG_BAR_HEIGHT = 18

VALID_SORT_OPTIONS = [
    COST_SORT_INCLUSIVE_DESC,
    COST_SORT_EXCLUSIVE_DESC,
    COST_SORT_DATE_DESC,
]

# ─── Jinja2 Setup ─────────────────────────────────────────────────────────────

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter()

# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/analysis", response_class=HTMLResponse)
def analysis(
    request: Request,
    page: int = Query(default=1, ge=1),
    slug: Optional[str] = Query(default=""),
    item_type: Optional[str] = Query(default=""),
    date_from: Optional[str] = Query(default=""),
    date_to: Optional[str] = Query(default=""),
    sort: str = Query(default=COST_SORT_INCLUSIVE_DESC),
) -> HTMLResponse:
    """Render the trace-based cost analysis page.

    Queries all cost data from the traces table via TracingProxy. Generates
    an SVG bar chart for cost over time and passes all data to the template.

    Args:
        request: Starlette request required by Jinja2TemplateResponse.
        page: 1-based page number for the top-runs table.
        slug: Substring filter on item_slug (case-insensitive).
        item_type: Exact filter on item_type.
        date_from: ISO date lower bound on created_at (inclusive).
        date_to: ISO date upper bound on created_at (inclusive).
        sort: Sort order for the top-runs table.

    Returns:
        Rendered analysis.html template.

    Raises:
        HTTPException: 404 when the tracing proxy is disabled.
    """
    proxy = get_proxy()
    if proxy is None:
        raise HTTPException(status_code=HTTP_NOT_FOUND, detail="Proxy not enabled")

    slug = slug or ""
    item_type = item_type or ""
    date_from = date_from or ""
    date_to = date_to or ""
    if sort not in VALID_SORT_OPTIONS:
        sort = COST_SORT_INCLUSIVE_DESC

    summary = proxy.get_cost_summary()
    daily_costs = proxy.get_cost_by_day(days=30)
    slug_costs = proxy.get_cost_by_slug()
    slug_runs = proxy.get_slug_cost_runs()
    node_costs = proxy.get_cost_by_node_type()
    tool_attribution = proxy.get_tool_call_attribution()

    runs, total_count = proxy.list_cost_runs(
        page=page,
        page_size=DEFAULT_PAGE_SIZE,
        slug=slug or None,
        item_type=item_type or None,
        date_from=date_from or None,
        date_to=date_to or None,
        sort=sort,
    )

    total_pages = max(1, math.ceil(total_count / DEFAULT_PAGE_SIZE))
    page = min(page, total_pages)

    cost_over_time_svg = _build_cost_over_time_svg(daily_costs)
    node_cost_svg = _build_node_cost_svg(node_costs)

    return templates.TemplateResponse(
        request,
        "analysis.html",
        {
            "summary": summary,
            "cost_over_time_svg": cost_over_time_svg,
            "runs": runs,
            "page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "slug_costs": slug_costs,
            "slug_runs": slug_runs,
            "node_costs": node_costs,
            "node_cost_svg": node_cost_svg,
            "slug": slug,
            "item_type": item_type,
            "date_from": date_from,
            "date_to": date_to,
            "sort": sort,
            "sort_options": VALID_SORT_OPTIONS,
            "tool_attribution": tool_attribution,
        },
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _build_cost_over_time_svg(daily_costs) -> str:
    """Build an SVG bar chart for daily cost over the last 30 days.

    Args:
        daily_costs: List of DailyCost objects from TracingProxy.

    Returns:
        SVG string for inline embedding.
    """
    labels = [dc.date_str for dc in daily_costs]
    values = [dc.cost_usd for dc in daily_costs]
    return svg_bar_chart(
        labels=labels,
        values=values,
        width=SVG_CHART_WIDTH,
        bar_height=SVG_BAR_HEIGHT,
        title="Cost Over Time — Last 30 Days (USD)",
    )


def _build_node_cost_svg(node_costs) -> str:
    """Build an SVG bar chart for cost by node type.

    Args:
        node_costs: List of NodeCost objects from TracingProxy.

    Returns:
        SVG string for inline embedding.
    """
    labels = [nc.node_name for nc in node_costs]
    values = [nc.total_cost_usd for nc in node_costs]
    return svg_bar_chart(
        labels=labels,
        values=values,
        width=SVG_CHART_WIDTH,
        bar_height=SVG_BAR_HEIGHT,
        title="Total Cost by Node Type (USD)",
    )
