# Migrate test_agent_identity.py off legacy plan-orchestrator.py

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
