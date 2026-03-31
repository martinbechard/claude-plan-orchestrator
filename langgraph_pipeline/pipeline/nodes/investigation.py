# langgraph_pipeline/pipeline/nodes/investigation.py
# run_investigation and process_investigation LangGraph nodes (placeholder).
# Design: docs/plans/2026-03-31-82-investigation-workflow-with-slack-proposals-design.md

"""Placeholder investigation nodes for the pipeline StateGraph.

These nodes are wired into the graph topology by task 1.1 so the graph
compiles and routes correctly.  Full implementation is delivered in later
tasks per the design document.

Node sequence for investigation items:
  intake_analyze -> run_investigation -> process_investigation -> archive | END
"""

import logging

from langgraph_pipeline.pipeline.state import PipelineState

logger = logging.getLogger(__name__)


def run_investigation(state: PipelineState) -> dict:
    """LangGraph node: run Claude-powered investigation and produce proposals.

    Placeholder — returns state unchanged.  Full implementation (reading
    code, logs, data and traces, generating structured proposals, persisting
    them, and posting to Slack) is delivered in task 2.x.
    """
    item_slug = state.get("item_slug", "")
    logger.info("[run_investigation] placeholder — item=%s", item_slug)
    return {}


def process_investigation(state: PipelineState) -> dict:
    """LangGraph node: process Slack approval and file accepted proposals.

    Placeholder — returns state unchanged.  Full implementation (polling
    the Slack thread, parsing the user's response, and filing accepted
    proposals as backlog items) is delivered in task 3.x.
    """
    item_slug = state.get("item_slug", "")
    logger.info("[process_investigation] placeholder — item=%s", item_slug)
    return {}
