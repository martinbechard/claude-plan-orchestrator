# LangSmith Observability

## Status: Open

## Priority: Low

## Summary

Add LangSmith tracing to all graph nodes in the pipeline and task execution graphs.
Configure project-level settings, environment variables, and trace filtering. Document
how to use the LangSmith dashboard for pipeline monitoring, debugging failed tasks,
and tracking costs.

## Scope

### Environment Configuration

Add LangSmith environment variables to the orchestrator config:

- LANGSMITH_API_KEY -- API key for LangSmith (from .claude/slack.local.yaml or env)
- LANGSMITH_PROJECT -- project name (default: "claude-plan-orchestrator")
- LANGSMITH_TRACING -- enable/disable tracing (default: "true")
- LANGSMITH_ENDPOINT -- custom endpoint for self-hosted (optional)

Create a shared/langsmith.py module that:
1. Reads config and sets environment variables
2. Provides a configure_tracing() function called at graph startup
3. Handles missing API key gracefully (tracing disabled, warning logged)

### Node-Level Tracing

Each graph node function should emit meaningful trace metadata:

- Node name and graph level (pipeline vs executor)
- Input state snapshot (filtered to avoid logging full plan YAML)
- Output state delta
- Claude CLI invocation details (model, token counts, duration)
- Error details with stack traces on failure

### Trace Filtering

Configure trace filtering to avoid noise:

- Filter out sleep/wait nodes (no useful trace data)
- Filter out health check / scan_backlog iterations that find no items
- Always trace: plan creation, task execution, validation, archival
- Tag traces with item_slug and item_type for easy filtering in the dashboard

### Dashboard Documentation

Add a section to the setup guide (docs/setup-guide.md) documenting:

- How to create a LangSmith account and get an API key
- How to configure the orchestrator for LangSmith
- How to navigate the LangSmith dashboard for this project
- Key views: run history, trace waterfall, error drill-down
- How to compare two pipeline runs to diagnose regressions
- How to track token costs by node, task, and plan

### Cost Tracking Integration

Connect LangSmith cost tracking with the existing budget guard:

- Emit cost metadata on each Claude CLI invocation trace
- Aggregate costs visible in LangSmith match the budget guard calculations
- Dashboard can show cost trends over time

### Verification

- LangSmith receives traces when the pipeline runs with tracing enabled
- Traces show up in the correct project with meaningful metadata
- Filtering works: sleep/scan nodes do not generate trace noise
- Pipeline runs without errors when LANGSMITH_API_KEY is not set (graceful degradation)
- Setup guide has a complete LangSmith configuration section

## Dependencies

- 04-pipeline-graph-nodes.md (pipeline graph must exist to add tracing)
- 02-extract-shared-modules.md (shared/ package must exist for shared/langsmith.py)
