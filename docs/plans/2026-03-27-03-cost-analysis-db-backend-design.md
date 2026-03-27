# Cost Analysis DB Backend - Design

## Status: Validation & Gap-Fix

Most of the implementation already exists. This plan focuses on verifying the
end-to-end flow works with real data and fixing any remaining gaps.

## Existing Implementation

### Already in place:
- **DB schema**: cost_tasks table created in proxy.py (TracingProxy.__init__)
- **POST /api/cost**: Endpoint in langgraph_pipeline/web/routes/cost.py (returns 202)
- **Cost recording**: proxy.record_cost_task() persists to SQLite
- **Pipeline integration**: Both task_runner.py and validator.py call _post_cost_to_api()
  after task completion (fire-and-forget POST to /api/cost)
- **CostLogReader**: Reads from DB first, falls back to JSON files
- **Analysis page**: Full template with summary cards, charts, filters, pagination
- **Test coverage**: tests/langgraph/web/test_cost_endpoint.py

### What changed since the backlog item was written:
- scripts/plan-orchestrator.py no longer exists; the LangGraph pipeline replaced it
- The LangGraph pipeline nodes (task_runner, validator) already POST cost data
- The "tool-call duration histogram" placeholder text has been removed

## Key Files

| File | Role |
|------|------|
| langgraph_pipeline/web/proxy.py | DB table creation, record_cost_task() |
| langgraph_pipeline/web/routes/cost.py | POST /api/cost endpoint |
| langgraph_pipeline/executor/nodes/task_runner.py | _post_cost_to_api() caller |
| langgraph_pipeline/executor/nodes/validator.py | _post_cost_to_api() caller |
| langgraph_pipeline/web/cost_log_reader.py | CostLogReader with DB + JSON fallback |
| langgraph_pipeline/web/routes/analysis.py | /analysis page route |
| langgraph_pipeline/web/templates/analysis.html | Analysis page template |
| tests/langgraph/web/test_cost_endpoint.py | Endpoint + DB tests |

## Design Decisions

1. **Single verification task**: Since the code exists, we validate against acceptance
   criteria and fix any gaps rather than reimplementing
2. **Acceptance criteria reinterpretation**: The original criterion about plan-orchestrator.py
   is satisfied by the LangGraph pipeline nodes calling _post_cost_to_api()
3. **JSON fallback**: CostLogReader.load_all() already tries DB first, falls back to
   JSON file glob - needs verification that fallback path still works
