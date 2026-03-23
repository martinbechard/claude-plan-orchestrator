# langgraph_pipeline/studio.py
# Entrypoint for LangGraph Studio dev server.
# Exposes compiled graphs for visualization and step-through debugging.

"""LangGraph Studio entrypoints for the pipeline and executor graphs."""

from langgraph_pipeline.pipeline.graph import build_graph as _build_pipeline
from langgraph_pipeline.executor.graph import build_executor_graph as _build_executor
from langgraph_pipeline.shared.langsmith import configure_tracing

configure_tracing()

# Compiled graphs for LangGraph Studio
pipeline_graph = _build_pipeline().compile()
executor_graph = _build_executor().compile()
