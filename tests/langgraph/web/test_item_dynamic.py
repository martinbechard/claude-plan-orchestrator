# tests/langgraph/web/test_item_dynamic.py
# Unit tests for GET /item/{slug}/dynamic JSON endpoint.
# Design: docs/plans/2026-03-28-72-item-page-auto-refresh-collapses-sections-design.md

"""Unit tests for the item_dynamic endpoint (D2).

Verifies that GET /item/{slug}/dynamic returns correct JSON structure,
reuses existing helpers, and applies the active-worker override logic.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from langgraph_pipeline.web.dashboard_state import reset_dashboard_state
from langgraph_pipeline.web.server import create_app

# ─── Constants ────────────────────────────────────────────────────────────────

_MODULE = "langgraph_pipeline.web.routes.item"

_TEST_SLUG = "72-auto-refresh"

_SAMPLE_COMPLETIONS = [
    {
        "cost_usd": 0.0342,
        "duration_s": 123.5,
        "tokens_per_minute": 4200,
        "outcome": "success",
    },
    {
        "cost_usd": 0.0158,
        "duration_s": 67.3,
        "tokens_per_minute": 3800,
        "outcome": "success",
    },
]

_SAMPLE_PLAN_TASKS = [
    {"id": "1.1", "name": "Add dynamic endpoint", "status": "completed", "agent": "coder"},
    {"id": "2.1", "name": "Add JS refresh", "status": "in_progress", "agent": "coder"},
    {"id": "3.1", "name": "Verify", "status": "pending", "agent": "validator"},
]

_SAMPLE_VALIDATION_RESULTS = [
    {
        "timestamp": "2026-03-28T15:30:00",
        "verdict": "PASS",
        "findings": [],
    },
]

_SAMPLE_ACTIVE_WORKER = {
    "pid": 12345,
    "elapsed_s": "3m 42s",
    "elapsed_raw_s": 222.0,
    "run_id": "run-abc123",
    "current_task": "#2.1 Add JS refresh",
    "current_velocity": 5100,
    "tokens_in": 48000,
    "tokens_out": 12000,
    "cost_usd": 0.0875,
}

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def fresh_state():
    """Reset dashboard singleton before each test."""
    reset_dashboard_state()
    yield
    reset_dashboard_state()


@pytest.fixture()
def client():
    """FastAPI TestClient with default configuration."""
    app = create_app(config={})
    return TestClient(app)


# ─── Tests ────────────────────────────────────────────────────────────────────


def test_dynamic_returns_json_with_all_fields(client: TestClient):
    """Endpoint returns 200 with all expected top-level keys."""
    with (
        patch(f"{_MODULE}._load_completions", return_value=_SAMPLE_COMPLETIONS),
        patch(f"{_MODULE}._derive_pipeline_stage", return_value="executing"),
        patch(f"{_MODULE}._detect_item_type", return_value="defect"),
        patch(f"{_MODULE}._get_active_worker", return_value=None),
        patch(f"{_MODULE}._load_plan_tasks", return_value=_SAMPLE_PLAN_TASKS),
        patch(f"{_MODULE}._load_validation_results", return_value=_SAMPLE_VALIDATION_RESULTS),
        patch(f"{_MODULE}.build_stages", return_value=[]),
    ):
        resp = client.get(f"/item/{_TEST_SLUG}/dynamic")

    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]

    data = resp.json()
    expected_keys = {
        "pipeline_stage",
        "active_worker",
        "total_cost_usd",
        "total_duration_s",
        "total_tokens",
        "avg_velocity",
        "plan_tasks",
        "validation_results",
        "stages",
    }
    assert set(data.keys()) == expected_keys


def test_dynamic_aggregates_completions_without_active_worker(client: TestClient):
    """Without an active worker, values are aggregated from completions."""
    with (
        patch(f"{_MODULE}._load_completions", return_value=_SAMPLE_COMPLETIONS),
        patch(f"{_MODULE}._derive_pipeline_stage", return_value="executing"),
        patch(f"{_MODULE}._get_active_worker", return_value=None),
        patch(f"{_MODULE}._load_plan_tasks", return_value=_SAMPLE_PLAN_TASKS),
        patch(f"{_MODULE}._load_validation_results", return_value=[]),
    ):
        resp = client.get(f"/item/{_TEST_SLUG}/dynamic")

    data = resp.json()
    assert data["pipeline_stage"] == "executing"
    assert data["active_worker"] is None
    # cost_usd = 0.0342 + 0.0158
    assert abs(data["total_cost_usd"] - 0.05) < 0.001
    # duration_s = 123.5 + 67.3
    assert abs(data["total_duration_s"] - 190.8) < 0.1
    # avg_velocity = (4200 + 3800) / 2
    assert data["avg_velocity"] == 4000
    assert data["plan_tasks"] == _SAMPLE_PLAN_TASKS
    assert data["validation_results"] == []


def test_dynamic_active_worker_overrides_completions(client: TestClient):
    """When an active worker is present, its live stats override aggregates."""
    with (
        patch(f"{_MODULE}._load_completions", return_value=_SAMPLE_COMPLETIONS),
        patch(f"{_MODULE}._derive_pipeline_stage", return_value="executing"),
        patch(f"{_MODULE}._get_active_worker", return_value=_SAMPLE_ACTIVE_WORKER),
        patch(f"{_MODULE}._load_plan_tasks", return_value=_SAMPLE_PLAN_TASKS),
        patch(f"{_MODULE}._load_validation_results", return_value=[]),
    ):
        resp = client.get(f"/item/{_TEST_SLUG}/dynamic")

    data = resp.json()
    # Active worker tokens override
    assert data["total_tokens"] == 48000 + 12000
    # Active worker cost overrides
    assert abs(data["total_cost_usd"] - 0.0875) < 0.0001
    # Active worker duration overrides
    assert abs(data["total_duration_s"] - 222.0) < 0.1
    # Active worker velocity overrides
    assert data["avg_velocity"] == 5100
    assert data["active_worker"] == _SAMPLE_ACTIVE_WORKER


def test_dynamic_no_plan_returns_null_tasks(client: TestClient):
    """When no plan YAML exists, plan_tasks is null."""
    with (
        patch(f"{_MODULE}._load_completions", return_value=[]),
        patch(f"{_MODULE}._derive_pipeline_stage", return_value="queued"),
        patch(f"{_MODULE}._get_active_worker", return_value=None),
        patch(f"{_MODULE}._load_plan_tasks", return_value=None),
        patch(f"{_MODULE}._load_validation_results", return_value=[]),
    ):
        resp = client.get(f"/item/{_TEST_SLUG}/dynamic")

    data = resp.json()
    assert data["plan_tasks"] is None
    assert data["pipeline_stage"] == "queued"


def test_dynamic_completed_stage(client: TestClient):
    """Completed items return terminal stage and no active worker."""
    with (
        patch(f"{_MODULE}._load_completions", return_value=_SAMPLE_COMPLETIONS),
        patch(f"{_MODULE}._derive_pipeline_stage", return_value="completed"),
        patch(f"{_MODULE}._get_active_worker", return_value=None),
        patch(f"{_MODULE}._load_plan_tasks", return_value=_SAMPLE_PLAN_TASKS),
        patch(f"{_MODULE}._load_validation_results", return_value=_SAMPLE_VALIDATION_RESULTS),
    ):
        resp = client.get(f"/item/{_TEST_SLUG}/dynamic")

    data = resp.json()
    assert data["pipeline_stage"] == "completed"
    assert data["active_worker"] is None
    assert data["validation_results"] == _SAMPLE_VALIDATION_RESULTS


def test_dynamic_empty_completions_zero_totals(client: TestClient):
    """With no completions and no worker, numeric totals are zero/null."""
    with (
        patch(f"{_MODULE}._load_completions", return_value=[]),
        patch(f"{_MODULE}._derive_pipeline_stage", return_value="unknown"),
        patch(f"{_MODULE}._get_active_worker", return_value=None),
        patch(f"{_MODULE}._load_plan_tasks", return_value=None),
        patch(f"{_MODULE}._load_validation_results", return_value=[]),
    ):
        resp = client.get(f"/item/{_TEST_SLUG}/dynamic")

    data = resp.json()
    assert data["total_cost_usd"] == 0.0
    assert data["total_duration_s"] == 0.0
    assert data["total_tokens"] == 0
    assert data["avg_velocity"] is None
    assert data["pipeline_stage"] == "unknown"


def test_dynamic_active_worker_zero_tokens_no_override(client: TestClient):
    """Active worker with zero tokens does not override completion aggregates."""
    worker_no_tokens = {
        "pid": 99999,
        "elapsed_s": "0m 5s",
        "elapsed_raw_s": 5.0,
        "run_id": "run-xyz",
        "current_task": "#1.1 Setup",
        "current_velocity": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0,
    }
    with (
        patch(f"{_MODULE}._load_completions", return_value=_SAMPLE_COMPLETIONS),
        patch(f"{_MODULE}._derive_pipeline_stage", return_value="executing"),
        patch(f"{_MODULE}._get_active_worker", return_value=worker_no_tokens),
        patch(f"{_MODULE}._load_plan_tasks", return_value=_SAMPLE_PLAN_TASKS),
        patch(f"{_MODULE}._load_validation_results", return_value=[]),
    ):
        resp = client.get(f"/item/{_TEST_SLUG}/dynamic")

    data = resp.json()
    # Tokens from completions preserved (worker has zero)
    assert data["total_tokens"] > 0
    # Cost from completions preserved (worker has zero)
    assert data["total_cost_usd"] > 0
    # Duration still overridden (elapsed_raw_s is always used)
    assert abs(data["total_duration_s"] - 5.0) < 0.1
    # Velocity from completions preserved (worker has zero)
    assert data["avg_velocity"] == 4000
