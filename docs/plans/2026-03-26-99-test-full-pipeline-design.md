# Design: Full Pipeline Integration Test with Token Tracking

## Summary

Add a comment marker to langgraph_pipeline/shared/paths.py and verify the full
pipeline (planner -> executor -> token tracking -> velocity badge) works end-to-end.

## Architecture

This is a minimal integration test. The task itself is trivial (add a comment),
but the acceptance criteria verify infrastructure:

1. **Code change**: Add "# full pipeline test" comment to paths.py
2. **Token tracking**: Verify traces DB has execute_task row with input_tokens > 100
3. **Velocity**: Verify completions table has tokens_per_minute > 0

## Key Files

- **Modify**: langgraph_pipeline/shared/paths.py -- add comment marker
- **Verify**: traces DB (execute_task rows), completions table (tokens_per_minute)

## Design Decisions

- Single task: the code change is one line; the orchestrator validator handles
  acceptance criteria verification automatically
- No test files needed: this is a pipeline smoke test, not a unit test
