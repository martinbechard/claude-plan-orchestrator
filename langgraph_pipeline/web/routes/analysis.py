# langgraph_pipeline/web/routes/analysis.py
# FastAPI router for the /analysis cost and token-usage page.
# Design: docs/plans/2026-03-25-16-tool-call-timing-and-cost-analysis-ui-design.md

"""FastAPI router that serves the read-only cost analysis page.

Endpoints:
    GET /analysis  — Renders analysis.html with SVG charts and cost tables.
                     Accepts an optional ?agent= query parameter that filters
                     the per-item cost table to tasks run by that agent type.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from langgraph_pipeline.web.cost_log_reader import CostLogReader, svg_bar_chart

# ─── Constants ────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

SVG_CHART_WIDTH = 700
SVG_BAR_HEIGHT = 18

# ─── Jinja2 Setup ─────────────────────────────────────────────────────────────

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter()

# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/analysis", response_class=HTMLResponse)
def analysis(
    request: Request,
    agent: Optional[str] = Query(default=None),
) -> HTMLResponse:
    """Render the cost analysis page.

    Loads all cost log JSON files on every request (no caching). Generates
    SVG bar charts server-side and passes them to the template as inline strings.
    When no data is available, passes has_data=False so the template can show
    a friendly empty-state message.

    Args:
        request: Starlette request required by Jinja2TemplateResponse.
        agent: Optional agent type string from the ?agent= query parameter.
               When present, filters the per-item table to items that include
               that agent type.

    Returns:
        Rendered analysis.html template.
    """
    cost_data = CostLogReader().load_all()

    if not cost_data.has_data:
        return templates.TemplateResponse(
            "analysis.html",
            {
                "request": request,
                "has_data": False,
            },
        )

    top_file_labels = [path for path, _ in cost_data.top_files]
    top_file_values = [bytes_count for _, bytes_count in cost_data.top_files]
    top_files_svg = svg_bar_chart(
        labels=top_file_labels,
        values=top_file_values,
        width=SVG_CHART_WIDTH,
        bar_height=SVG_BAR_HEIGHT,
        title="Top Files by Read Volume (bytes)",
    )

    agent_labels = list(cost_data.cost_by_agent.keys())
    agent_values = list(cost_data.cost_by_agent.values())
    agent_cost_svg = svg_bar_chart(
        labels=agent_labels,
        values=agent_values,
        width=SVG_CHART_WIDTH,
        bar_height=SVG_BAR_HEIGHT,
        title="Token Cost by Agent Type (total tokens)",
    )

    filtered_items = _filter_items_by_agent(cost_data.cost_by_item, agent)

    return templates.TemplateResponse(
        "analysis.html",
        {
            "request": request,
            "has_data": True,
            "top_files_svg": top_files_svg,
            "agent_cost_svg": agent_cost_svg,
            "cost_by_item": filtered_items,
            "wasted_reads": cost_data.wasted_reads,
            "agent_filter": agent,
            "all_agent_types": sorted(cost_data.cost_by_agent.keys()),
        },
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _filter_items_by_agent(items, agent: Optional[str]):
    """Return items whose agent_types list includes the given agent, or all items.

    Args:
        items: List of ItemCost objects.
        agent: Agent type string to filter by, or None to return all.

    Returns:
        Filtered (or unfiltered) list of ItemCost objects.
    """
    if not agent:
        return items
    return [item for item in items if agent in item.agent_types]
