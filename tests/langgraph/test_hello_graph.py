# tests/langgraph/test_hello_graph.py
# Verifies graph compilation, invocation, and SQLite checkpointing for the hello-world graph.
# Design: docs/plans/2026-02-25-01-langgraph-project-scaffold-design.md

"""Tests for the hello-world LangGraph StateGraph."""

from langgraph_pipeline.pipeline.graph import GREETING_MESSAGE, build_graph

THREAD_ID = "test-thread-1"


def test_graph_compiles(checkpointer):
    """Graph should compile without errors."""
    graph = build_graph()
    compiled = graph.compile(checkpointer=checkpointer)
    assert compiled is not None


def test_graph_invocation_returns_greeting(compiled_graph):
    """Invoking the graph should produce the expected greeting message."""
    config = {"configurable": {"thread_id": THREAD_ID}}
    result = compiled_graph.invoke({"message": ""}, config=config)
    assert result["message"] == GREETING_MESSAGE


def test_graph_checkpointing_persists_state(compiled_graph):
    """After invocation, the checkpointer should have state for the thread."""
    config = {"configurable": {"thread_id": THREAD_ID}}
    compiled_graph.invoke({"message": ""}, config=config)
    state = compiled_graph.get_state(config)
    assert state is not None
    assert state.values["message"] == GREETING_MESSAGE
