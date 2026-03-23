# Module Entry Point for LangGraph Pipeline

## Status: Open

## Priority: High

## Summary

Add langgraph_pipeline/__main__.py so the pipeline can be invoked as
python -m langgraph_pipeline instead of python scripts/run-pipeline.py.
Move the CLI logic from scripts/run-pipeline.py into the package so
the entry point is self-contained.

## Scope

### Project Virtual Environment

The v1 scripts work with system Python because they have no external
dependencies. The LangGraph runner requires langgraph, langgraph-checkpoint-sqlite,
langsmith, etc. which are currently only in the pyenv 3.11 environment.

Create a project .venv so the runner works without knowing the pyenv path:

1. Add a Makefile or setup script that creates .venv from pyenv 3.11
   and installs the package in editable mode (pip install -e .)
2. Add a shell wrapper scripts/lg-pipeline that activates .venv and
   delegates to python -m langgraph_pipeline with all arguments
3. The wrapper should be the primary invocation method:

       ./scripts/lg-pipeline --budget-cap 5.00 --single-item docs/feature-backlog/foo.md

### Create __main__.py

Create langgraph_pipeline/__main__.py that contains (or imports) the CLI
entry point currently in scripts/run-pipeline.py. The module should:

1. Import and call the main() function with sys.argv
2. Handle sys.exit with the appropriate exit code

### Relocate CLI Logic

Move the argument parsing, PID file management, signal handling, and
graph invocation loop from scripts/run-pipeline.py into a new module
langgraph_pipeline/cli.py. The __main__.py delegates to cli.main().

scripts/run-pipeline.py becomes a thin wrapper that imports and calls
langgraph_pipeline.cli.main() for backward compatibility.

### Invocation

After this change, the pipeline runs as:

    python -m langgraph_pipeline --budget-cap 5.00 --single-item docs/feature-backlog/foo.md

All CLI arguments remain identical to what scripts/run-pipeline.py supports.

## Verification

- python -m langgraph_pipeline --help prints usage
- python -m langgraph_pipeline --dry-run starts and scans the backlog
- scripts/run-pipeline.py still works as before (thin wrapper)
- All existing tests in tests/langgraph/test_run_pipeline.py still pass

## Dependencies

- 20-unified-langgraph-runner.md (the runner must exist to relocate)
