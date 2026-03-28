# Design: Redesign Traces Page for Usability

## Summary

Replace the raw LangSmith trace view with an item-centric execution narrative.
The current proxy_trace.html and proxy_list.html pages show developer-facing
data (routing nodes, raw tool_use events, metadata JSON). The redesign presents
traces through the user's mental model: "show me what happened to my work item
from start to finish."

This feature includes a design competition (3 UI approaches) before implementation.

## Architecture

### Phase 1: Design Competition

Three mockup approaches are produced using the frontend-design skill:

1. **Vertical timeline** -- each pipeline phase is a card in a vertical scroll,
   expandable to show agent details and artifacts.
2. **Tabbed phases** -- one tab per pipeline phase (Intake, Plan, Execute,
   Validate), each showing agent activity.
3. **Swimlane diagram** -- horizontal lanes per agent type with time flowing
   left to right, showing what each agent did and when.

The user selects the winner before implementation proceeds.

### Phase 2: Data Layer

The existing TracingProxy SQLite DB stores all trace data. A new helper module
maps raw trace rows to the item-centric view model:

- **Phase mapping** -- classify trace runs by pipeline phase (intake, planning,
  execution, validation, archival) using run name patterns and metadata.
- **Agent activity summary** -- aggregate tool calls per agent into summaries:
  "Read 5 files, edited 2, ran 8 bash commands, committed."
- **Cost and duration rollup** -- sum token costs and wall-clock time per phase.
- **Artifact extraction** -- link to design docs, plan YAMLs, validation results,
  git commits, and worker output logs from trace metadata and filesystem.

### Phase 3: UI Implementation

Build the winning design approach as a new template (or set of templates):

- New route: GET /proxy/{run_id}/narrative -- item-centric execution view
- New template: proxy_narrative.html -- the redesigned page
- Keep existing proxy_trace.html accessible via "Show raw trace" toggle
- Reuse base.html layout and existing CSS variables

### Key Files to Create

- langgraph_pipeline/web/helpers/trace_narrative.py -- phase mapping, activity
  summarization, artifact extraction logic
- langgraph_pipeline/web/templates/proxy_narrative.html -- winning design template

### Key Files to Modify

- langgraph_pipeline/web/routes/proxy.py -- add narrative endpoint, wire helpers
- langgraph_pipeline/web/templates/proxy_trace.html -- add link/toggle to
  narrative view
- langgraph_pipeline/web/templates/proxy_list.html -- default link to narrative
  view instead of raw trace

### Data Flow

```
TracingProxy.get_run(run_id)
  + TracingProxy.get_children(run_id)
  + TracingProxy.get_children_batch(child_ids)  [grandchildren]
       |
       v
trace_narrative.build_execution_view(run, children, grandchildren)
       |
       v
  ExecutionView:
    phases: [{name, status, duration, cost, agent, activity_summary, artifacts}]
    total_duration: str
    total_cost: str
    item_slug: str
       |
       v
  proxy_narrative.html template
```

### Design Decisions

- Keep raw trace view (proxy_trace.html) as a "Show raw trace" toggle rather
  than replacing it, because developers still need access to raw LangSmith data
  for debugging.
- Build the narrative as a separate route/template rather than modifying the
  existing trace page, to avoid regression risk on the working trace view.
- Classify phases by run name patterns (the pipeline uses consistent naming:
  "intake", "plan_creation", "execute_plan", "validate", "archive").
- Summarize tool calls by counting tool types rather than listing each one,
  matching the "Read 5 files, edited 2" pattern from the spec.
- The design competition happens first as a separate task so the user can
  evaluate mockups before any implementation code is written.

## Acceptance Criteria

- Can the user select a work item and see its full execution history on one page?
- Is each pipeline phase clearly labeled with duration, cost, and outcome?
- Can the user access prompts and raw tool calls without them being shown by default?
- Are output artifacts (design doc, validation results, commits) linked from the view?
- Is the raw LangSmith trace data accessible via a toggle but not the default view?
