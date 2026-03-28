# Migrate test_agent_identity.py off legacy plan-orchestrator.py imports

## Summary

tests/test_agent_identity.py imports from scripts/plan-orchestrator.py
via importlib. This 6820-line legacy script is the only reason it cannot
be deleted. The tests need to import from the new langgraph_pipeline.slack
submodules instead.

27 of 64 tests fail when switched to the new imports because they call
methods on different sub-modules (notifier vs poller vs identity).

## Acceptance Criteria

- Do all 64 tests in test_agent_identity.py pass when importing from
  langgraph_pipeline.slack submodules? YES = pass, NO = fail
- Is scripts/plan-orchestrator.py deleted after migration?
  YES = pass, NO = fail
- Are there zero importlib references to plan-orchestrator.py in tests/?
  YES = pass, NO = fail

## LangSmith Trace: 5d143f2b-a90e-4f61-84cd-dbf3a50406be


## 5 Whys Analysis

Title: Consolidate pipeline architecture by eliminating legacy monolith blocker
Clarity: 4/5

5 Whys:

1. **Why do 27 of 64 tests fail when switching to new imports?**
   Because the test methods call functions on classes/submodules that exist in plan-orchestrator.py but are located in different submodules in langgraph_pipeline.slack (notifier, poller, identity), so the same method calls don't work without adapting them to the new structure.

2. **Why are the methods on different submodules between the old and new architecture?**
   Because plan-orchestrator.py was a monolithic script where all functionality lived in one file, while langgraph_pipeline.slack was intentionally refactored to separate concerns into focused submodules (notifier handles Slack comms, poller handles polling, identity handles agent identity).

3. **Why does the refactored architecture exist as a separate codebase instead of replacing the old one?**
   Because the migration is incomplete—the old plan-orchestrator.py was never deleted, so both implementations coexist, with tests still depending on the legacy version rather than being updated to use the new modular design.

4. **Why is plan-orchestrator.py still not deleted despite the new langgraph_pipeline architecture existing?**
   Because test_agent_identity.py still imports from it via importlib, creating a hard dependency that blocks deletion. No other code depends on it, so the tests are the sole blocker preventing the cleanup.

5. **Why is it critical to delete the legacy plan-orchestrator.py rather than maintain both architectures in parallel?**
   Because maintaining two parallel implementations creates technical debt, divergence in behavior, confusion about the canonical codebase, and prevents the team from confidently evolving the pipeline. A single, modern architecture enables reliable changes and reduces cognitive overhead.

Root Need: Eliminate the legacy monolithic codebase (plan-orchestrator.py) to consolidate on a single, modern, modular pipeline architecture and reduce technical debt from parallel implementations.

Summary: The team needs to complete the architecture migration by updating tests to use the new modular design, enabling deletion of the legacy monolith and establishing a single source of truth.
