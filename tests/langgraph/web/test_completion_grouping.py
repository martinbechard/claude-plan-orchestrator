# tests/langgraph/web/test_completion_grouping.py
# Unit tests for the group_completions_by_slug() pure grouping utility.
# Design: docs/plans/2026-03-30-81-dashboard-group-retries-per-item-design-1-systems.md

"""Tests for langgraph_pipeline.web.completion_grouping."""

import pytest

from langgraph_pipeline.web.completion_grouping import (
    RETRY_FIELDS,
    group_completions_by_slug,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────


def make_row(
    slug: str,
    finished_at: float,
    outcome: str = "success",
    cost_usd: float = 0.10,
    duration_s: float = 60.0,
    run_id: str = "run-abc",
    item_type: str = "defect",
    tokens_per_minute: float = 1000.0,
    verification_notes: str = "",
) -> dict:
    """Build a minimal completion dict as the proxy would return."""
    return {
        "slug": slug,
        "item_type": item_type,
        "outcome": outcome,
        "cost_usd": cost_usd,
        "duration_s": duration_s,
        "finished_at": finished_at,
        "run_id": run_id,
        "tokens_per_minute": tokens_per_minute,
        "verification_notes": verification_notes,
    }


# ─── Tests ───────────────────────────────────────────────────────────────────


def test_empty_list_returns_empty():
    """An empty input list produces an empty output list."""
    result = group_completions_by_slug([])
    assert result == []


def test_single_item_no_retries():
    """A single row yields one entry with attempt_count=1 and retries=[]."""
    rows = [make_row("feature-01", 1000.0)]
    result = group_completions_by_slug(rows)

    assert len(result) == 1
    entry = result[0]
    assert entry["slug"] == "feature-01"
    assert entry["attempt_count"] == 1
    assert entry["retries"] == []


def test_two_rows_same_slug():
    """Two rows for the same slug produce one grouped entry with one retry."""
    rows = [
        make_row("bug-42", 2000.0, outcome="success", run_id="run-2"),
        make_row("bug-42", 1000.0, outcome="warn", run_id="run-1"),
    ]
    result = group_completions_by_slug(rows)

    assert len(result) == 1
    entry = result[0]
    assert entry["outcome"] == "success"
    assert entry["attempt_count"] == 2
    assert len(entry["retries"]) == 1
    assert entry["retries"][0]["outcome"] == "warn"
    assert entry["retries"][0]["run_id"] == "run-1"


def test_three_rows_same_slug_retries_oldest_first():
    """Three rows for the same slug produce retries listed oldest-first."""
    rows = [
        make_row("bug-99", 3000.0, outcome="success", run_id="run-3"),
        make_row("bug-99", 2000.0, outcome="warn", run_id="run-2"),
        make_row("bug-99", 1000.0, outcome="fail", run_id="run-1"),
    ]
    result = group_completions_by_slug(rows)

    assert len(result) == 1
    entry = result[0]
    assert entry["outcome"] == "success"
    assert entry["attempt_count"] == 3
    assert len(entry["retries"]) == 2
    # oldest first
    assert entry["retries"][0]["outcome"] == "fail"
    assert entry["retries"][0]["run_id"] == "run-1"
    assert entry["retries"][1]["outcome"] == "warn"
    assert entry["retries"][1]["run_id"] == "run-2"


def test_mixed_slugs_grouped_independently():
    """Each distinct slug is grouped independently; first-seen order is preserved."""
    rows = [
        make_row("alpha", 5000.0, outcome="success", run_id="a2"),
        make_row("beta",  4000.0, outcome="success", run_id="b1"),
        make_row("alpha", 3000.0, outcome="warn",    run_id="a1"),
    ]
    result = group_completions_by_slug(rows)

    assert len(result) == 2
    assert result[0]["slug"] == "alpha"
    assert result[0]["attempt_count"] == 2
    assert result[1]["slug"] == "beta"
    assert result[1]["attempt_count"] == 1
    assert result[1]["retries"] == []


def test_limit_applied_to_grouped_entries():
    """limit caps the number of distinct slugs returned, not raw rows."""
    rows = [make_row(f"item-{i}", float(100 - i)) for i in range(5)]
    result = group_completions_by_slug(rows, limit=2)

    assert len(result) == 2
    assert result[0]["slug"] == "item-0"
    assert result[1]["slug"] == "item-1"


def test_retry_dict_contains_only_retry_fields():
    """Retry dicts must contain exactly RETRY_FIELDS — no item_type, tokens_per_minute, etc."""
    rows = [
        make_row("task-7", 2000.0, tokens_per_minute=9999.0, verification_notes="note"),
        make_row("task-7", 1000.0, tokens_per_minute=8888.0, verification_notes="old note"),
    ]
    result = group_completions_by_slug(rows)

    assert len(result) == 1
    retry = result[0]["retries"][0]
    assert set(retry.keys()) == set(RETRY_FIELDS)
    assert "item_type" not in retry
    assert "tokens_per_minute" not in retry
    assert "verification_notes" not in retry
