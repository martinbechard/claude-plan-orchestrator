# langgraph_pipeline/web/routes/cost.py
# FastAPI router for the POST /api/cost endpoint that stores per-task cost records.
# Design: .claude/plans/.claimed/03-cost-analysis-db-backend.md

"""FastAPI router that accepts per-task cost payloads from plan-orchestrator.py
and persists them to the cost_tasks table via the TracingProxy DB connection.

Endpoints:
    POST /api/cost  — Accept a cost record and insert it into cost_tasks.
                      Returns {"ok": true} with status 202.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter()

# ─── Request Schema ───────────────────────────────────────────────────────────


class ToolCallEntry(BaseModel):
    tool: str
    file_path: Optional[str] = None
    command: Optional[str] = None
    result_bytes: Optional[int] = None


class CostPayload(BaseModel):
    item_slug: str
    item_type: str
    task_id: str
    agent_type: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_s: float = 0.0
    tool_calls: Optional[list[ToolCallEntry]] = None


# Known fake data pattern from prior test insertions — used to detect accidental
# test data being posted to the real pipeline.
_FAKE_COST_USD = 0.01
_FAKE_INPUT_TOKENS = 100
_FAKE_OUTPUT_TOKENS = 50

# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/api/cost", status_code=202)
def record_cost(payload: CostPayload) -> JSONResponse:
    """Accept a per-task cost record and insert it into the cost_tasks table.

    The caller (plan-orchestrator.py) fires this POST and does not block on the
    response, so we return 202 immediately after persisting the row.

    Args:
        payload: Per-task cost data matching the CostPayload schema.

    Returns:
        JSON response {"ok": true} with HTTP 202.
    """
    if (
        payload.cost_usd == _FAKE_COST_USD
        and payload.input_tokens == _FAKE_INPUT_TOKENS
        and payload.output_tokens == _FAKE_OUTPUT_TOKENS
    ):
        logger.warning(
            "POST /api/cost: suspiciously fake data received for item_slug=%r "
            "(cost=%.2f, input_tokens=%d, output_tokens=%d) — "
            "this matches the known test-data pattern; verify this is not test data",
            payload.item_slug,
            payload.cost_usd,
            payload.input_tokens,
            payload.output_tokens,
        )

    from langgraph_pipeline.web.proxy import get_proxy

    proxy = get_proxy()
    if proxy is None:
        logger.warning("POST /api/cost: proxy not initialised, record dropped")
        return JSONResponse({"ok": True}, status_code=202)

    tool_calls_json: Optional[str] = None
    if payload.tool_calls is not None:
        tool_calls_json = json.dumps([tc.model_dump(exclude_none=True) for tc in payload.tool_calls])

    recorded_at = datetime.now(timezone.utc).isoformat()
    proxy.record_cost_task(
        item_slug=payload.item_slug,
        item_type=payload.item_type,
        task_id=payload.task_id,
        agent_type=payload.agent_type,
        model=payload.model,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        cost_usd=payload.cost_usd,
        duration_s=payload.duration_s,
        tool_calls_json=tool_calls_json,
        recorded_at=recorded_at,
    )

    return JSONResponse({"ok": True}, status_code=202)
