# LangSmith Observability - Design Document

Work item: docs/feature-backlog/06-langsmith-observability.md

## Architecture Overview

LangSmith integration adds observability tracing to the LangGraph pipeline and executor
graphs. LangGraph has native LangSmith support via environment variables, so the core
integration is lightweight: a shared configuration module sets the right env vars at
startup, and node-level decorators add custom metadata (graph level, cost, tokens).

### Integration Points

```
shared/langsmith.py          <-- new: config loading, env setup, trace helpers
  |
  +-- pipeline/graph.py      <-- add: configure_tracing() at graph startup
  +-- executor/graph.py      <-- add: configure_tracing() at graph startup
  |
  +-- pipeline/nodes/*.py    <-- add: trace metadata on each node
  +-- executor/nodes/*.py    <-- add: trace metadata on each node
  |
  +-- shared/budget.py       <-- add: emit cost metadata to active trace
  +-- shared/claude_cli.py   <-- add: emit CLI invocation details to active trace
```

### How LangSmith Tracing Works with LangGraph

LangGraph automatically traces all graph execution when these env vars are set:
- LANGCHAIN_TRACING_V2=true
- LANGCHAIN_API_KEY=<key>
- LANGCHAIN_PROJECT=<project name>
- LANGCHAIN_ENDPOINT=<optional, for self-hosted>

This gives us the graph structure, node timings, and input/output states for free.
The custom work is adding meaningful metadata and filtering out noisy nodes.

## Key Files

### New Files

- langgraph_pipeline/shared/langsmith.py -- Configuration, env setup, trace helpers
- tests/langgraph/shared/test_langsmith.py -- Unit tests

### Modified Files

- langgraph_pipeline/pipeline/graph.py -- Call configure_tracing() at startup
- langgraph_pipeline/executor/graph.py -- Call configure_tracing() at startup
- langgraph_pipeline/pipeline/nodes/scan.py -- Add trace metadata
- langgraph_pipeline/pipeline/nodes/intake.py -- Add trace metadata
- langgraph_pipeline/pipeline/nodes/plan_creation.py -- Add trace metadata, tag traces
- langgraph_pipeline/pipeline/nodes/execute_plan.py -- Add trace metadata, tag traces
- langgraph_pipeline/pipeline/nodes/archival.py -- Add trace metadata
- langgraph_pipeline/executor/nodes/task_selector.py -- Add trace metadata
- langgraph_pipeline/executor/nodes/task_runner.py -- Add trace metadata + cost
- langgraph_pipeline/executor/nodes/validator.py -- Add trace metadata
- langgraph_pipeline/executor/nodes/parallel.py -- Add trace metadata
- langgraph_pipeline/shared/claude_cli.py -- Emit CLI invocation details to trace
- langgraph_pipeline/shared/budget.py -- Emit cost metadata to active trace
- docs/setup-guide.md -- Add LangSmith configuration section

## Design Decisions

### 1. Environment Variable Approach

Use LangChain's standard env vars (LANGCHAIN_TRACING_V2, LANGCHAIN_API_KEY, etc.)
rather than custom LANGSMITH_* vars. This follows the official LangSmith SDK convention
and means LangGraph's built-in tracing works automatically without code changes.

The shared/langsmith.py configure_tracing() function reads config from:
1. Environment variables (highest priority)
2. .claude/orchestrator-config.yaml langsmith section
3. Defaults (tracing disabled when no API key)

### 2. Graceful Degradation

When LANGCHAIN_API_KEY is not set:
- Tracing is disabled silently (LANGCHAIN_TRACING_V2 not set)
- A single warning is logged at startup
- All pipeline functionality works normally
- No exceptions thrown from tracing code

### 3. Trace Filtering Strategy

Use LangSmith's run_type and tags to filter noise:
- Tag all traces with item_slug and item_type
- Skip tracing for scan_backlog iterations that find no items (return early)
- Skip tracing for sleep/wait cycles
- Always trace: plan_creation, execute_plan, task execution, validation, archival

Implementation: nodes that should be filtered call a should_trace() helper that checks
node name against a skip-list. When should_trace() returns False, the node skips
emitting custom metadata (LangGraph still records the node run, but with minimal data).

### 4. Cost Metadata on Traces

Each Claude CLI invocation (task_runner, validator) already captures cost data from
the stream-json result event. The integration adds this data as trace metadata:
- total_cost_usd
- input_tokens, output_tokens
- cache_read_tokens, cache_creation_tokens
- model, duration_ms

This enables LangSmith dashboard to show cost per node, per task, and per plan.

### 5. No langsmith Python Package Dependency

LangGraph's built-in tracing via env vars handles most needs. For custom metadata,
use langsmith.run_trees or the langchain_core.callbacks approach only if already
available. Check import availability and degrade gracefully if the langsmith package
is not installed.

## Task Breakdown

### Phase 1: Core LangSmith Module
Create shared/langsmith.py with configure_tracing(), should_trace(), and
add_trace_metadata() helpers. Add unit tests.

### Phase 2: Pipeline and Executor Integration
Wire configure_tracing() into both graph builders. Add trace metadata to all
pipeline and executor nodes. Add cost metadata to Claude CLI invocations.

### Phase 3: Documentation
Add LangSmith configuration section to docs/setup-guide.md with account setup,
config, dashboard navigation, and cost tracking instructions.
