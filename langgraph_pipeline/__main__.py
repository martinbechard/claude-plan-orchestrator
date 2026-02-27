# langgraph_pipeline/__main__.py
# Module entry point for the LangGraph pipeline.
# Design: docs/plans/2026-02-26-21-main-module-entry-point-design.md

"""Thin bootstrap for invoking the LangGraph pipeline as a module.

Allows: python -m langgraph_pipeline [args]
"""

import sys

from langgraph_pipeline.cli import main

if __name__ == "__main__":
    sys.exit(main())
