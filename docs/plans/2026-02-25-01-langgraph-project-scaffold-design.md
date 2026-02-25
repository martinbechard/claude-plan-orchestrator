# Design: LangGraph Project Scaffold

## Overview

Create the foundational LangGraph pipeline package structure with dependencies,
a hello-world graph proving LangGraph + SQLite checkpointing works, and a pytest
test harness for future development.

## Architecture

### Package Layout

```
langgraph_pipeline/
  __init__.py              # Package root, version info
  pyproject.toml           # Package-local config (keeps deps separate from scripts/)
  pipeline/
    __init__.py
    graph.py               # Hello world StateGraph
  executor/
    __init__.py
  slack/
    __init__.py
  shared/
    __init__.py
tests/langgraph/
  __init__.py
  conftest.py              # Shared fixtures (graph factory, checkpointer)
  test_hello_graph.py      # Verifies graph compilation, invocation, checkpointing
```

### Key Decisions

1. **pyproject.toml inside langgraph_pipeline/**: The existing project root has
   scripts/ with their own Python dependencies managed via pyenv. Placing pyproject.toml
   inside the package avoids polluting the root and allows independent dependency
   management via pip install -e langgraph_pipeline/.

2. **SqliteSaver with in-memory DB for tests**: Uses ":memory:" for fast, isolated
   test runs. Production code can swap in a file-backed database later.

3. **Minimal StateGraph**: Two nodes (start_node, end_node) with a single TypedDict
   field. Proves imports, compilation, invocation, and checkpointing all work without
   adding unnecessary complexity.

### Dependencies

Production:
- langgraph
- langgraph-checkpoint-sqlite
- langsmith
- pyyaml

Dev:
- pytest
- pytest-asyncio

### Verification Criteria

- pytest tests/langgraph/ passes all tests green
- langgraph_pipeline package is importable from project root
- Hello world graph runs with SQLite checkpointing
