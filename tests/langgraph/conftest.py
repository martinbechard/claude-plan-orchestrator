# tests/langgraph/conftest.py
# Shared pytest fixtures: graph factory and in-memory SQLite checkpointer.
# Design: docs/plans/2026-02-25-01-langgraph-project-scaffold-design.md

"""Shared fixtures for langgraph_pipeline tests."""

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from langgraph_pipeline.pipeline.graph import build_graph


@pytest.fixture
def checkpointer():
    """Provide an in-memory SqliteSaver for fast, isolated test runs."""
    with SqliteSaver.from_conn_string(":memory:") as saver:
        yield saver


@pytest.fixture
def compiled_graph(checkpointer):
    """Provide a compiled hello-world graph wired to the in-memory checkpointer."""
    graph = build_graph()
    return graph.compile(checkpointer=checkpointer)
