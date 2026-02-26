# Pipeline Graph Nodes - Design Document

## Overview

Replace the procedural main_loop() in auto-pipeline.py with a LangGraph StateGraph
containing five core nodes (scan_backlog, intake_analyze, create_plan, verify_symptoms,
archive) plus an execute_plan subprocess bridge. Uses SqliteSaver for crash recovery.

## Architecture

```
scan_backlog --> [has_items?]
  |-- no items --> END (sleep/wait)
  |-- has items --> intake_analyze
        |
        v
  create_plan --> execute_plan --> [is_defect?]
                                    |-- yes --> verify_symptoms --> [verify_result?]
                                    |              |-- PASS --> archive
                                    |              |-- FAIL + cycles left --> create_plan
                                    |              |-- FAIL + exhausted --> archive (mark exhausted)
                                    |-- no --> archive
```

## Key Files

### New files
- langgraph_pipeline/pipeline/state.py - PipelineState TypedDict schema
- langgraph_pipeline/pipeline/edges.py - Conditional edge routing functions
- langgraph_pipeline/pipeline/nodes/__init__.py - Nodes subpackage
- langgraph_pipeline/pipeline/nodes/scan.py - scan_backlog node
- langgraph_pipeline/pipeline/nodes/intake.py - intake_analyze node (with throttle + dedup)
- langgraph_pipeline/pipeline/nodes/plan_creation.py - create_plan node
- langgraph_pipeline/pipeline/nodes/execute_plan.py - Subprocess bridge to plan-orchestrator.py
- langgraph_pipeline/pipeline/nodes/verification.py - verify_symptoms node
- langgraph_pipeline/pipeline/nodes/archival.py - archive node
- tests/langgraph/pipeline/test_state.py - State schema tests
- tests/langgraph/pipeline/test_edges.py - Edge routing tests
- tests/langgraph/pipeline/nodes/__init__.py
- tests/langgraph/pipeline/nodes/test_scan.py
- tests/langgraph/pipeline/nodes/test_intake.py
- tests/langgraph/pipeline/nodes/test_plan_creation.py
- tests/langgraph/pipeline/nodes/test_execute_plan.py
- tests/langgraph/pipeline/nodes/test_verification.py
- tests/langgraph/pipeline/nodes/test_archival.py
- tests/langgraph/pipeline/test_graph_integration.py

### Modified files
- langgraph_pipeline/pipeline/graph.py - Replace hello-world graph with full pipeline
- langgraph_pipeline/pipeline/__init__.py - Update exports

## Design Decisions

### State Schema
PipelineState uses TypedDict with Annotated list fields for append-only history.
Two additional intake count fields (intake_count_defects, intake_count_features) track
in-graph counts separately from the disk-persisted throttle file.

### Safety: Disk-Persisted Throttle
The backlog creation throttle (.claude/plans/.backlog-creation-throttle.json) lives on
disk, NOT in graph state. This ensures the throttle survives graph checkpoint restarts
and process crashes. The intake node reads/writes this file directly.

### Subprocess Bridge Pattern
execute_plan spawns plan-orchestrator.py as a subprocess (matching current
auto-pipeline.py behavior). It captures exit code, stdout, and cost/token data from
the result JSON event. This is a temporary bridge replaced by feature 05.

### Checkpointing
SqliteSaver at .claude/pipeline-state.db with thread_id "pipeline-main". On restart,
graph.invoke() automatically resumes from the last checkpoint.

### Conditional Edges
Edge functions are pure functions that read PipelineState and return the next node name
string. This keeps routing logic testable independently from node implementations.

## Dependencies

- Feature 01 (scaffold) - provides package structure, LangGraph deps
- Feature 02 (shared modules) - provides config.py, claude_cli.py, paths.py
- Feature 03 (slack modules) - provides slack/notifier.py for archive notifications
