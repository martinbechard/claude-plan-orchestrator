#!/usr/bin/env -S python3 -u
# scripts/run-pipeline.py
# Thin wrapper for the unified LangGraph pipeline runner.
# Design: docs/plans/2026-02-26-21-main-module-entry-point-design.md

"""Thin wrapper that calls the LangGraph pipeline CLI.

For backward compatibility, this script provides the same interface as before.
The actual implementation has been moved to langgraph_pipeline.cli.
"""

import sys

from langgraph_pipeline.cli import main

if __name__ == "__main__":
    sys.exit(main())
