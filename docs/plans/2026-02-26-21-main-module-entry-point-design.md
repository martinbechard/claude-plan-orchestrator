# Design: Module Entry Point for LangGraph Pipeline

## Work Item

docs/feature-backlog/21-main-module-entry-point.md

## Overview

Add langgraph_pipeline/__main__.py so the pipeline can be invoked as
python -m langgraph_pipeline. Move CLI logic from scripts/run-pipeline.py
into langgraph_pipeline/cli.py, making the package self-contained.

## Architecture

```
Before:
  scripts/run-pipeline.py  (all CLI + pipeline logic)

After:
  langgraph_pipeline/cli.py        (CLI logic relocated here)
  langgraph_pipeline/__main__.py   (thin bootstrap: calls cli.main())
  scripts/run-pipeline.py          (thin wrapper: calls cli.main())
```

## Key Files

### Create

- langgraph_pipeline/cli.py -- All CLI logic from scripts/run-pipeline.py
  moves here: argument parsing, PID file management, signal handling,
  startup banner, budget checking, state builders, single-item mode,
  scan loop, and main() entry point.

- langgraph_pipeline/__main__.py -- Thin module:
  ```
  from langgraph_pipeline.cli import main
  import sys
  sys.exit(main())
  ```

### Modify

- scripts/run-pipeline.py -- Replace the full implementation with a thin
  wrapper that imports and calls langgraph_pipeline.cli.main(). Keep the
  shebang and a brief docstring for backward compatibility.

- tests/langgraph/test_run_pipeline.py -- Update imports to test
  langgraph_pipeline.cli instead of scripts.run_pipeline (or wherever
  the test currently imports from). All existing test logic stays the same.

## Design Decisions

1. cli.py vs __main__.py separation: The __main__.py module should be
   trivially thin. All logic lives in cli.py so it can be imported and
   tested without triggering sys.exit().

2. Backward compatibility: scripts/run-pipeline.py becomes a one-liner
   wrapper. Existing invocations (cron jobs, shell scripts, pipeline
   configs) continue to work without changes.

3. Import structure: cli.py uses the same imports as the current
   run-pipeline.py. No new dependencies are introduced.

4. Test migration: Tests update their import path from the script module
   to langgraph_pipeline.cli. Test assertions and mocking remain unchanged.
