# langgraph_pipeline/web/routes/execution_history.py
# FastAPI router for the execution history page and JSON API.
# Design: docs/plans/2026-03-28-71-execution-history-redesign-design.md (D6)

"""FastAPI router for execution history endpoints.

Endpoints:
    GET /execution-history/{run_id}    -- HTML page shell with loading state.
    GET /api/execution-tree/{run_id}   -- JSON API returning full recursive tree.

The HTML endpoint serves a minimal page shell; the frontend JS fetches the tree
from the JSON API and renders it client-side. This decouples the page load from
the potentially heavy recursive tree fetch.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from langgraph_pipeline.web.helpers.execution_tree import build_tree
from langgraph_pipeline.web.proxy import get_proxy

# ─── Constants ────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

HTTP_NOT_FOUND = 404

logger = logging.getLogger(__name__)

# ─── Jinja2 Setup ─────────────────────────────────────────────────────────────

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter()


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/execution-history/{run_id}", response_class=HTMLResponse)
def execution_history_page(request: Request, run_id: str) -> HTMLResponse:
    """Render the execution history HTML page shell for a pipeline run.

    The page displays a loading state; client-side JS fetches the full tree
    from /api/execution-tree/{run_id} and renders it.

    Args:
        request: Starlette request (required by Jinja2TemplateResponse).
        run_id: Identifier of the root run to display.

    Returns:
        Rendered execution_history.html template.

    Raises:
        HTTPException: 404 when the proxy is disabled or run not found.
    """
    proxy = get_proxy()
    if proxy is None:
        raise HTTPException(status_code=HTTP_NOT_FOUND, detail="Proxy not enabled")

    run = proxy.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=HTTP_NOT_FOUND, detail=f"Run not found: {run_id}")

    return templates.TemplateResponse(
        request,
        "execution_history.html",
        {"run_id": run_id, "run": run},
    )


@router.get("/api/execution-tree/{run_id}")
def execution_tree_api(run_id: str) -> JSONResponse:
    """Return the full recursive execution tree for a run as JSON.

    Each node includes: run_id, name, display_name, node_type, status,
    duration, cost, model, token_count, inputs_json, outputs_json,
    metadata_json, children[].

    Args:
        run_id: Identifier of the root run whose tree to return.

    Returns:
        JSONResponse with the tree structure under a "tree" key, plus
        the root run_id.

    Raises:
        HTTPException: 404 when the proxy is disabled or run not found.
    """
    proxy = get_proxy()
    if proxy is None:
        raise HTTPException(status_code=HTTP_NOT_FOUND, detail="Proxy not enabled")

    run = proxy.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=HTTP_NOT_FOUND, detail=f"Run not found: {run_id}")

    flat_rows = proxy.get_full_tree(run_id)
    tree_nodes = build_tree(run_id, flat_rows)

    return JSONResponse({
        "run_id": run_id,
        "tree": [node.to_dict() for node in tree_nodes],
    })
