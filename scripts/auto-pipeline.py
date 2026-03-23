#!/usr/bin/env -S python3 -u
"""Auto-Pipeline: backward-compatible wrapper for the LangGraph pipeline.

This script preserves the original CLI interface (--dry-run, --once, --verbose)
while delegating to the new unified LangGraph pipeline runner.

Usage:
    python scripts/auto-pipeline.py [--dry-run] [--once] [--verbose]
    python scripts/auto-pipeline.py [--budget-cap N] [--no-slack] [--log-level LEVEL]

All flags from the new CLI (langgraph_pipeline.cli) are also accepted.
"""

import sys

from langgraph_pipeline.cli import main

if __name__ == "__main__":
    sys.exit(main())
