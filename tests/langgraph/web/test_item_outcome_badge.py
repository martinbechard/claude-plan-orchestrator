# tests/langgraph/web/test_item_outcome_badge.py
# Unit tests for the _derive_outcome helper and its integration with endpoints.
# Design: docs/plans/2026-03-31-84-item-page-missing-outcome-badge-design.md

"""Unit tests for the outcome badge feature.

Covers:
    - _derive_outcome returns the outcome from the most recent completion (D1).
    - _derive_outcome returns None when completions is empty.
    - _derive_outcome handles multiple completions correctly (picks first/latest).
    - item_dynamic JSON includes the "outcome" key (D2).
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from langgraph_pipeline.web.dashboard_state import reset_dashboard_state
from langgraph_pipeline.web.routes.item import _derive_outcome
from langgraph_pipeline.web.server import create_app

# ─── Constants ────────────────────────────────────────────────────────────────

_MODULE = "langgraph_pipeline.web.routes.item"

_TEST_SLUG = "84-outcome-badge"

# ─── _derive_outcome unit tests ───────────────────────────────────────────────


def test_derive_outcome_returns_outcome_from_single_completion():
    """Returns the outcome from the only completion record."""
    completions = [{"outcome": "success", "finished_at": "2026-03-31T10:00:00"}]
    assert _derive_outcome(completions) == "success"


def test_derive_outcome_returns_none_for_empty_list():
    """Returns None when the completions list is empty."""
    assert _derive_outcome([]) is None


def test_derive_outcome_returns_first_element_outcome():
    """Returns the outcome from the first (most recent) completion.

    list_completions_by_slug orders by finished_at DESC so completions[0]
    is the latest.  _derive_outcome must pick that element, not the last.
    """
    completions = [
        {"outcome": "fail", "finished_at": "2026-03-31T12:00:00"},
        {"outcome": "success", "finished_at": "2026-03-31T10:00:00"},
        {"outcome": "warn", "finished_at": "2026-03-30T08:00:00"},
    ]
    assert _derive_outcome(completions) == "fail"


def test_derive_outcome_returns_none_when_outcome_field_missing():
    """Returns None when the latest completion has no outcome key."""
    completions = [{"finished_at": "2026-03-31T10:00:00"}]
    assert _derive_outcome(completions) is None


def test_derive_outcome_returns_none_when_outcome_is_empty_string():
    """Returns None when outcome is an empty string (treats as absent)."""
    completions = [{"outcome": "", "finished_at": "2026-03-31T10:00:00"}]
    assert _derive_outcome(completions) is None


@pytest.mark.parametrize("outcome_value", ["success", "warn", "fail"])
def test_derive_outcome_all_valid_values(outcome_value: str):
    """Returns each valid outcome string unchanged."""
    completions = [{"outcome": outcome_value, "finished_at": "2026-03-31T10:00:00"}]
    assert _derive_outcome(completions) == outcome_value


# ─── Integration: item_dynamic endpoint includes outcome ──────────────────────


@pytest.fixture()
def client():
    reset_dashboard_state()
    return TestClient(create_app())


def _make_completions(outcome: str) -> list[dict]:
    return [
        {
            "outcome": outcome,
            "finished_at": "2026-03-31T12:00:00",
            "cost_usd": 0.01,
            "duration_s": 10.0,
            "tokens_per_minute": 1000,
            "verification_notes": None,
        }
    ]


@patch(f"{_MODULE}._load_plan_tasks", return_value=None)
@patch(f"{_MODULE}._load_validation_results", return_value=[])
@patch(f"{_MODULE}.build_stages", return_value=[])
@patch(f"{_MODULE}._get_active_worker", return_value=None)
@patch(f"{_MODULE}._detect_item_type", return_value="feature")
@patch(f"{_MODULE}._load_completions")
def test_item_dynamic_includes_outcome_key(
    mock_completions,
    mock_item_type,
    mock_worker,
    mock_stages,
    mock_validation,
    mock_plan_tasks,
    client,
):
    """GET /item/{slug}/dynamic response includes the 'outcome' field."""
    mock_completions.return_value = _make_completions("success")

    response = client.get(f"/item/{_TEST_SLUG}/dynamic")

    assert response.status_code == 200
    data = response.json()
    assert "outcome" in data
    assert data["outcome"] == "success"


@patch(f"{_MODULE}._load_plan_tasks", return_value=None)
@patch(f"{_MODULE}._load_validation_results", return_value=[])
@patch(f"{_MODULE}.build_stages", return_value=[])
@patch(f"{_MODULE}._get_active_worker", return_value=None)
@patch(f"{_MODULE}._detect_item_type", return_value="feature")
@patch(f"{_MODULE}._load_completions")
def test_item_dynamic_outcome_none_when_no_completions(
    mock_completions,
    mock_item_type,
    mock_worker,
    mock_stages,
    mock_validation,
    mock_plan_tasks,
    client,
):
    """GET /item/{slug}/dynamic returns outcome=null when no completions exist."""
    mock_completions.return_value = []

    response = client.get(f"/item/{_TEST_SLUG}/dynamic")

    assert response.status_code == 200
    data = response.json()
    assert data["outcome"] is None
