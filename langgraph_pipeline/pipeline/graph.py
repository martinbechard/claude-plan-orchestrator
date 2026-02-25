# langgraph_pipeline/pipeline/graph.py
# Hello-world StateGraph proving LangGraph + SQLite checkpointing works end-to-end.
# Design: docs/plans/2026-02-25-01-langgraph-project-scaffold-design.md

"""Minimal two-node StateGraph used to verify the LangGraph scaffold."""

from typing import TypedDict

from langgraph.graph import END, StateGraph

GREETING_MESSAGE = "hello from langgraph"


class HelloState(TypedDict):
    """State for the hello-world graph."""

    message: str


def start_node(state: HelloState) -> HelloState:
    """Set the initial greeting message."""
    return {"message": GREETING_MESSAGE}


def end_node(state: HelloState) -> HelloState:
    """Return state unchanged, acting as a terminal processing step."""
    return state


def build_graph() -> StateGraph:
    """Build and return the compiled hello-world StateGraph.

    The graph has two nodes (start_node -> end_node -> END) and proves
    that imports, compilation, invocation, and checkpointing all work.
    """
    graph = StateGraph(HelloState)
    graph.add_node("start_node", start_node)
    graph.add_node("end_node", end_node)
    graph.set_entry_point("start_node")
    graph.add_edge("start_node", "end_node")
    graph.add_edge("end_node", END)
    return graph
