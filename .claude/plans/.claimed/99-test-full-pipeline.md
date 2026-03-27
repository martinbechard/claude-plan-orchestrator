# Test: verify full pipeline with token tracking

## Summary

Add a comment "# full pipeline test" to langgraph_pipeline/shared/paths.py.
This tests that the planner creates a YAML, the executor runs, tokens are
tracked, and the velocity badge appears.

## Acceptance Criteria

- Does langgraph_pipeline/shared/paths.py contain "# full pipeline test"?
  YES = pass, NO = fail
- Does the traces DB have an execute_task row with input_tokens > 100
  for this item? YES = pass, NO = fail
- Does the completions table have tokens_per_minute > 0 for this item?
  YES = pass, NO = fail

## LangSmith Trace: 8beb4114-ea1b-444f-9fb6-a22f5683cc8f


## 5 Whys Analysis

Title: Add full pipeline integration test with token tracking verification
Clarity: 2

5 Whys:

1. **Why add a comment marker to paths.py?** — To create a traceable identifier so that when this test runs through the full orchestrator pipeline, its execution can be correlated in the traces database and metrics can be attributed specifically to this test.

2. **Why do we need to correlate this specific test run in the traces database?** — Because without the marker, it's impossible to verify that *this particular* test exercised the entire pipeline (planner → executor → token tracking → velocity badge) rather than testing components in isolation.

3. **Why is it critical to verify the *entire* pipeline runs together rather than testing components separately?** — Because the pipeline loop bug incidents (per memory notes) showed that individual components could work while the integrated system failed in production, spinning into infinite loops despite passing unit tests.

4. **Why does the integration matter more than individual component correctness?** — Because the orchestrator's value depends on reliable end-to-end execution and cost visibility. If the pipeline loops infinitely or token tracking fails silently, the system wastes resources and users lose trust in automation.

5. **Why is pipeline reliability + cost transparency the core concern?** — Because the orchestrator's purpose is to automate work safely and efficiently. A system that completes tasks but hides resource consumption, or that appears to work in parts but fails end-to-end, is fundamentally unreliable.

Root Need: The system needs an end-to-end integration test that proves the orchestrator can execute a complete task-to-completion cycle with full visibility into token consumption, preventing regressions into the infinite-loop bugs that plagued previous iterations.

Summary: This test gates the orchestrator's ability to demonstrate safe, efficient, verifiable autonomous execution.
