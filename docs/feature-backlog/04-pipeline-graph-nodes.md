# Pipeline Graph Nodes

## Status: Open

## Priority: Medium

## Summary

Implement the top-level pipeline StateGraph that replaces auto-pipeline.py main_loop().
The graph has five nodes (scan_backlog, intake, create_plan, verify, archive) with
conditional edges for routing. Uses SQLite checkpointing for crash recovery. In this
phase, the execute_plan step still calls plan-orchestrator.py as a subprocess -- the
subgraph replacement comes in feature 05.

## Scope

### State Schema

Define PipelineState in langgraph_pipeline/pipeline/state.py:

```
class PipelineState(TypedDict):
    item_path: str
    item_slug: str
    item_type: str                    # "defect" | "feature" | "analysis"
    item_name: str
    plan_path: Optional[str]
    design_doc_path: Optional[str]
    verification_cycle: int
    verification_history: Annotated[list[dict], operator.add]
    should_stop: bool
    rate_limited: bool
    rate_limit_reset: Optional[str]
    session_cost_usd: float
    session_input_tokens: int
    session_output_tokens: int
```

### Node Implementations

#### pipeline/nodes/scan.py -- scan_backlog
- Scan docs/defect-backlog/, docs/feature-backlog/, docs/analysis-backlog/
- Prioritize: defects first, then features, then analyses
- Check for in-progress plans that need resuming
- Return item metadata or empty state (triggering sleep/wait edge)

#### pipeline/nodes/intake.py -- intake_analyze
- For defects: verify symptoms are reproducible before planning
- For ideas in analysis-backlog: run 5-Whys classification
- Use shared/claude_cli.py to spawn Claude session for analysis

#### pipeline/nodes/plan_creation.py -- create_plan
- Spawn Claude with planner agent to generate YAML plan
- Write plan to .claude/plans/{slug}.yaml
- Optionally generate design doc if the item scope warrants it

#### pipeline/nodes/verification.py -- verify_symptoms
- For defects only: run verification after plan execution
- Parse verification result (PASS/FAIL)
- Append to verification_history in state
- Increment verification_cycle

#### pipeline/nodes/archival.py -- archive
- Move backlog item from docs/{type}-backlog/ to docs/completed-backlog/{type}/
- Clean up plan YAML
- Send Slack notification via langgraph_pipeline.slack

### Conditional Edges

#### edges.py
- has_items: route to intake or sleep based on scan results
- is_defect: route to verify or archive based on item_type
- verify_result: route to archive, create_plan (retry), or mark_exhausted
- cycles_exhausted: check verification_cycle >= max (default 3)

### Execute Plan (Subprocess Bridge)

In this phase, the execute_plan node is a thin wrapper that:
1. Spawns plan-orchestrator.py as a subprocess (same as current auto-pipeline.py)
2. Captures exit code and output
3. Returns updated state with cost/token usage

This subprocess bridge is replaced by the task execution subgraph in feature 05.

### Graph Compilation

Compile the graph with SqliteSaver using .claude/pipeline-state.db. The main entry
point invokes the compiled graph with thread_id "pipeline-main". On restart, the
graph resumes from the last checkpoint automatically.

### Verification

- The pipeline graph compiles without errors
- Unit tests cover each node with mocked Claude CLI calls
- Integration test runs the full graph on a test backlog item
- Checkpointing works: kill the process mid-run, restart, and it resumes
- The subprocess bridge to plan-orchestrator.py works identically to current behavior

## Dependencies

- 01-langgraph-project-scaffold.md (package structure and LangGraph dependency)
- 02-extract-shared-modules.md (shared/config.py, shared/claude_cli.py, shared/paths.py)
- 03-extract-slack-modules.md (slack/notifier.py for archive notifications)
