# langgraph_pipeline/pipeline/graph.py
# Full pipeline StateGraph wiring all nodes, conditional edges, and SqliteSaver checkpointing.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Pipeline StateGraph for the Claude plan orchestrator.

Assembles the pipeline graph (intake_analyze, create_plan, execute_plan,
verify_fix, archive) with conditional edges and SQLite-backed
checkpointing for crash recovery.

The CLI pre-scans the backlog via scan_backlog_fn() before invoking the graph,
so the graph entry point is intake_analyze (item_path is always pre-populated).

Graph topology:
  intake_analyze --[route_after_intake]--> create_plan | END
  create_plan --[route_after_plan]--> execute_plan | END
  execute_plan --[route_after_execution]--> verify_fix | archive
  verify_fix --[verify_result]--> archive | create_plan
  archive --> END
"""

from contextlib import contextmanager
from typing import Iterator

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from langgraph_pipeline.pipeline.edges import route_after_execution, route_after_intake, route_after_plan, verify_result
from langgraph_pipeline.pipeline.nodes import (
    archive,
    create_plan,
    execute_plan,
    intake_analyze,
    verify_fix,
)
from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.langsmith import configure_tracing

# ─── Configuration constants ──────────────────────────────────────────────────

PIPELINE_DB_PATH = ".claude/pipeline-state.db"
PIPELINE_THREAD_ID = "pipeline-main"

# ─── Node name constants ───────────────────────────────────────────────────────
# These must match the string names registered with add_node() below.

NODE_INTAKE_ANALYZE = "intake_analyze"
NODE_CREATE_PLAN = "create_plan"
NODE_EXECUTE_PLAN = "execute_plan"
NODE_VERIFY_FIX = "verify_fix"
NODE_ARCHIVE = "archive"


# ─── Graph assembly ───────────────────────────────────────────────────────────


def build_graph() -> StateGraph:
    """Build and return the uncompiled pipeline StateGraph.

    The returned graph is uncompiled — callers that need checkpointing should
    use pipeline_graph() which wraps it with a SqliteSaver context manager.
    This function is also used directly in tests to inject a custom checkpointer.
    """
    configure_tracing()
    graph = StateGraph(PipelineState)

    graph.add_node(NODE_INTAKE_ANALYZE, intake_analyze)
    graph.add_node(NODE_CREATE_PLAN, create_plan)
    graph.add_node(NODE_EXECUTE_PLAN, execute_plan)
    graph.add_node(NODE_VERIFY_FIX, verify_fix)
    graph.add_node(NODE_ARCHIVE, archive)

    graph.set_entry_point(NODE_INTAKE_ANALYZE)

    # intake_analyze → route_after_intake → create_plan | END
    graph.add_conditional_edges(NODE_INTAKE_ANALYZE, route_after_intake)

    # create_plan → route_after_plan → execute_plan | END
    graph.add_conditional_edges(NODE_CREATE_PLAN, route_after_plan)

    # execute_plan → route_after_execution → verify_fix | archive
    graph.add_conditional_edges(NODE_EXECUTE_PLAN, route_after_execution)

    # verify_fix → verify_result → archive | create_plan
    graph.add_conditional_edges(NODE_VERIFY_FIX, verify_result)

    # archive → END (always)
    graph.add_edge(NODE_ARCHIVE, END)

    return graph


@contextmanager
def pipeline_graph(db_path: str = PIPELINE_DB_PATH) -> Iterator[CompiledStateGraph]:
    """Context manager that yields a compiled pipeline graph with SqliteSaver.

    Opens a SQLite connection at db_path, compiles the graph with it as the
    checkpointer, and closes the connection on exit.  On restart, the graph
    automatically resumes from the last checkpoint for the given thread_id.

    Usage:
        with pipeline_graph() as graph:
            config = {"configurable": {"thread_id": PIPELINE_THREAD_ID}}
            graph.invoke(initial_state, config=config)
    """
    with SqliteSaver.from_conn_string(db_path) as saver:
        yield build_graph().compile(checkpointer=saver)
