# Test: full pipeline with YAML rescue

## Summary

Add a comment "# yaml rescue test" to langgraph_pipeline/shared/paths.py.

## Acceptance Criteria

- Does langgraph_pipeline/shared/paths.py contain "# yaml rescue test"?
  YES = pass, NO = fail
- Does the pipeline log show "Rescued YAML plan from permission denial"?
  YES = pass, NO = fail
- Does the item complete with a non-zero cost? YES = pass, NO = fail

## LangSmith Trace: 233ad989-08dc-454d-941f-b49f471992e3


## 5 Whys Analysis

Title: Verify YAML state recovery from permission denial scenarios

Clarity: 2

5 Whys:

1. Why are we adding a comment "# yaml rescue test" to paths.py and running a full pipeline?
   - To trigger and verify a specific code path (the YAML rescue handler) that was recently implemented to handle permission denial scenarios during pipeline execution

2. Why do we need to verify this rescue handler works in a real pipeline run?
   - Because the fix was added to prevent data loss when Claude Code blocks writes to `.claude/` directories, and we need proof it actually rescues the YAML state rather than crashing or silently failing

3. Why is it critical to handle permission denials without losing YAML plans?
   - Because YAML plans are the pipeline's orchestration database—if they're lost or corrupted during a permission denial, in-flight work becomes orphaned and the entire pipeline state becomes unrecoverable

4. Why does the pipeline write YAML files frequently enough that permission denials are a real concern?
   - Because the orchestrator continuously updates plan YAMLs to track progress (completed steps, verification cycles, archival status), so any disruption to write operations directly impacts state tracking

5. Why is this particular test necessary now as a tracked backlog item rather than just a one-off verification?
   - Because the recent fix (commit 4b2455de) introduced new error-handling code that needs regression testing to ensure future changes don't re-introduce the vulnerability where permission denials cause silent data loss

Root Need: Establish a regression test that confirms the pipeline's YAML state recovery mechanism prevents data loss during permission denial scenarios, ensuring operational resilience of the orchestration system.

Summary: This test verifies that a recently-added fix correctly rescues YAML plans when Claude Code permission denials occur during pipeline state updates.
