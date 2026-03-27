# Migrate test_agent_identity.py off legacy plan-orchestrator.py

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

test_agent_identity.py (64 tests) imports directly from
scripts/plan-orchestrator.py using importlib. This 6820-line legacy script
is the only reason it cannot be deleted. The test needs to be rewritten to
import from the new langgraph_pipeline.slack submodules (identity.py,
notifier.py, poller.py).

## Complication

The old monolithic SlackNotifier had all methods on one class. The new
architecture splits them across:
- langgraph_pipeline.slack.identity (AgentIdentity, IdentityMixin, constants)
- langgraph_pipeline.slack.notifier (SlackNotifier implementation)
- langgraph_pipeline.slack.poller (SlackPoller with _handle_polled_messages)
- langgraph_pipeline.slack (facade SlackNotifier wrapping the above)

27 of 64 tests fail when switched to the new imports because they call
methods that live on different sub-modules (e.g. _sign_text on notifier,
_handle_polled_messages on poller, bot_user_id on poller).

## Fix

1. Rewrite the test to import from the correct submodules.
2. For tests that need both notifier and poller behaviour, test against the
   actual submodule class that owns the method.
3. Once all 64 tests pass against the new imports, delete
   scripts/plan-orchestrator.py.
4. Also delete the stale pyc cache at tests/__pycache__/test_auto_pipeline*.




## 5 Whys Analysis

**Title:** Delete legacy plan-orchestrator.py by migrating its test suite to new modular architecture

**Clarity:** 4/5

**5 Whys:**

1. **Why** does test_agent_identity.py need to be rewritten?
   - Because it imports directly from scripts/plan-orchestrator.py, making that 6820-line legacy script impossible to delete

2. **Why** is the legacy script still preventing its deletion instead of being gone?
   - Because test_agent_identity.py (64 tests) is the last remaining code that depends on it, and removing the import would break all tests

3. **Why** does test_agent_identity.py still import from the old location instead of the new modular structure?
   - Because when SlackNotifier was refactored into distributed modules (identity, notifier, poller), the test file wasn't updated to map test calls to the correct new sub-module that owns each method

4. **Why** wasn't this test migration completed during the original refactoring?
   - Because the migration required understanding the new distributed interface (27 tests call methods that moved to different modules), making it a non-trivial mapping task that was deferred

5. **Why** was the monolithic design split into separate modules if it complicates testing?
   - Because separating concerns (identity management, message sending, polling, notification handling) reduces coupling, improves module-level testability, and creates a maintainable structure where each module has a single responsibility

**Root Need:** Remove technical debt (6820-line legacy script) by completing the architectural refactoring that splits monolithic concerns into testable, maintainable modules.

**Summary:** Complete the migration of test_agent_identity.py to use the refactored modular Slack architecture so the legacy plan-orchestrator.py can be deleted.

## LangSmith Trace: 756f7a42-ae8b-496d-8838-8cd678535d15
