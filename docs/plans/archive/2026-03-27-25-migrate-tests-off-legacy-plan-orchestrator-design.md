# Design: Migrate test_agent_identity.py off legacy plan-orchestrator.py

## Status

Previously implemented. All acceptance criteria met. This plan validates the existing work.

## Architecture Overview

The original monolithic SlackNotifier in scripts/plan-orchestrator.py was refactored into:

- langgraph_pipeline/slack/identity.py - AgentIdentity, IdentityMixin, constants
- langgraph_pipeline/slack/notifier.py - SlackNotifier implementation
- langgraph_pipeline/slack/poller.py - SlackPoller with polling/filtering methods
- langgraph_pipeline/slack/__init__.py - Facade re-exports

tests/test_agent_identity.py (64 tests) was migrated to import from the new submodules.
The legacy scripts/plan-orchestrator.py has been deleted.

## Key Files

- tests/test_agent_identity.py - Already migrated to new imports, all 64 tests passing
- scripts/plan-orchestrator.py - Already deleted

## Verification Criteria

1. All 64 tests in test_agent_identity.py pass
2. No imports from scripts/plan-orchestrator.py remain anywhere in the codebase
3. scripts/plan-orchestrator.py does not exist
4. No stale pyc caches for test_auto_pipeline exist
