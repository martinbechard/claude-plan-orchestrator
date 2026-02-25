# LangGraph Project Scaffold

## Status: Open

## Priority: High

## Summary

Create the langgraph_pipeline/ folder with pyproject.toml, package structure, LangGraph
and LangSmith dependencies, and a minimal "hello world" graph that compiles and runs
with SQLite checkpointing. Include pytest setup so that subsequent features have a
working test harness from day one.

## Scope

### Package Structure

Create the following directory tree:

```
langgraph_pipeline/
  __init__.py
  pipeline/
    __init__.py
  executor/
    __init__.py
  slack/
    __init__.py
  shared/
    __init__.py
tests/langgraph/
  __init__.py
  conftest.py
  test_hello_graph.py
```

### pyproject.toml

Create a pyproject.toml at the project root (or inside langgraph_pipeline/) with:

- Python >= 3.11
- Dependencies: langgraph, langgraph-checkpoint-sqlite, langsmith, pyyaml
- Dev dependencies: pytest, pytest-asyncio
- Package name: claude-plan-orchestrator-pipeline

### Hello World Graph

Create a minimal StateGraph in langgraph_pipeline/pipeline/graph.py that:

1. Defines a simple TypedDict state with one field
2. Has two nodes: start_node and end_node
3. Compiles with SqliteSaver checkpointer using an in-memory database
4. Can be invoked with a thread_id and produces a deterministic result

This proves that LangGraph is installed correctly, the package imports work, and
checkpointing functions.

### Test

Create tests/langgraph/test_hello_graph.py that:

1. Compiles the hello world graph
2. Invokes it with a thread_id
3. Asserts the expected output state
4. Verifies that a checkpoint was saved (invoke again with same thread_id)

### Verification

- Running pytest tests/langgraph/ passes with all tests green
- The langgraph_pipeline package is importable from the project root
- The hello world graph runs to completion with checkpointing

## Dependencies

None -- this is the first item and can be started immediately.
