# Test: pipeline with tmp/plans and token tracking

## Summary

Add a comment "# tmp plans test" to langgraph_pipeline/shared/paths.py.

## Acceptance Criteria

- Does langgraph_pipeline/shared/paths.py contain "# tmp plans test"?
  YES = pass, NO = fail
- Was the plan YAML created without permission denials?
  YES = pass, NO = fail
- Does the item page show non-zero Tokens after completion?
  YES = pass, NO = fail

## LangSmith Trace: 761b663f-1c78-47be-a73f-97fd0a1080b6


## 5 Whys Analysis

Title: Validate plan directory refactoring and token tracking integration
Clarity: 2
5 Whys:

1. Why add a comment "# tmp plans test" to langgraph_pipeline/shared/paths.py?
   Because this creates an observable artifact to prove the orchestrator successfully executed a plan and modified files in the specified path—a smoke test that the basic system works.

2. Why verify the plan YAML was created without permission denials?
   Because recent refactoring moved plans from `.claude/plans/` to `tmp/plans/`, and permission errors would indicate the new directory structure is inaccessible to the orchestrator, breaking core functionality.

3. Why is validating the new tmp/plans/ path critical?
   Because commit 59819039 shows this was a deliberate architectural change with cleanup of claim metadata files—a refactoring that could have introduced regressions in how the orchestrator locates and manages plan files.

4. Why would this refactoring matter enough to need regression testing?
   Because the pipeline absolutely depends on being able to read/write plan YAMLs; if the new path breaks this, the entire auto-orchestrator loop fails silently, leaving stale plans and blocking further work.

5. Why specifically check for non-zero token counts after completion?
   Because recent commits ("fix: write token counts to trace metadata...") show active work on cost observability, and this test validates that token tracking works end-to-end through a completed plan—proving the instrumentation is actually capturing LLM usage.

Root Need: Validate that the recent plans directory refactoring didn't break the orchestrator's ability to create/execute plans AND that the new token tracking instrumentation works correctly in production.

Summary: This is a regression test for two recent changes (directory structure + token tracking) that are critical to the pipeline's observability and reliability.
