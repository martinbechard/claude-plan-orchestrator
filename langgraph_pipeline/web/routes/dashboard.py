# langgraph_pipeline/web/routes/dashboard.py
# FastAPI router for the pipeline activity dashboard: HTML page and SSE stream.
# Design: docs/plans/2026-03-25-15-pipeline-activity-dashboard-design.md

"""FastAPI router that serves the live pipeline activity dashboard.

Endpoints:
    GET /dashboard   — Renders dashboard.html via Jinja2Templates.
    GET /api/stream  — SSE StreamingResponse; pushes a JSON state snapshot
                       every SSE_INTERVAL_SECONDS until the client disconnects.
"""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.responses import StreamingResponse

from langgraph_pipeline.web.dashboard_state import get_dashboard_state

# ─── Constants ────────────────────────────────────────────────────────────────

SSE_INTERVAL_SECONDS = 2

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# ─── Jinja2 Setup ─────────────────────────────────────────────────────────────

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter()

# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    """Render the pipeline activity dashboard page.

    Args:
        request: Starlette request required by Jinja2TemplateResponse.

    Returns:
        Rendered dashboard.html template.
    """
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/api/stream")
async def stream_state(request: Request) -> StreamingResponse:
    """Stream pipeline state as Server-Sent Events.

    Sends one SSE message with event type ``state`` every SSE_INTERVAL_SECONDS.
    The generator exits when the client disconnects (request.is_disconnected()).

    Returns:
        StreamingResponse with Content-Type text/event-stream.
    """
    return StreamingResponse(
        _state_event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─── SSE Generator ────────────────────────────────────────────────────────────


async def _state_event_generator(request: Request):
    """Async generator that yields SSE-formatted state snapshots.

    Sends the first snapshot immediately so the browser has data on connect,
    then waits SSE_INTERVAL_SECONDS between subsequent snapshots.

    Args:
        request: Starlette request used to detect client disconnection.

    Yields:
        SSE-formatted strings: "event: state\\ndata: <json>\\n\\n"
    """
    state = get_dashboard_state()

    while True:
        if await request.is_disconnected():
            break

        snapshot = state.snapshot()
        payload = json.dumps(snapshot)
        yield f"event: state\ndata: {payload}\n\n"

        await asyncio.sleep(SSE_INTERVAL_SECONDS)
