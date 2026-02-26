# tests/langgraph/conftest.py
# Shared pytest fixtures: in-memory SQLite checkpointer for isolated test runs.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Shared fixtures for langgraph_pipeline tests."""

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver


@pytest.fixture
def checkpointer():
    """Provide an in-memory SqliteSaver for fast, isolated test runs."""
    with SqliteSaver.from_conn_string(":memory:") as saver:
        yield saver
