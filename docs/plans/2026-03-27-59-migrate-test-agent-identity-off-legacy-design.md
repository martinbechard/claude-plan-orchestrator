# Design: Migrate test_agent_identity.py off legacy plan-orchestrator.py

## Status: Already Resolved

Investigation shows this defect has already been fixed in prior work:

- tests/test_agent_identity.py already imports exclusively from
  langgraph_pipeline.slack submodules (identity, notifier, poller)
- scripts/plan-orchestrator.py has already been deleted
- All 64 tests pass (0.13s runtime)
- No importlib references to plan-orchestrator.py remain in tests/

## Architecture

The migration followed the expected pattern:

- langgraph_pipeline/slack/identity.py - AgentIdentity, load_agent_identity, role constants
- langgraph_pipeline/slack/notifier.py - SlackNotifier, block text limits
- langgraph_pipeline/slack/poller.py - SlackPoller, rate limiting, loop detection constants

## Key Files

- tests/test_agent_identity.py (987 lines, 64 tests) - already migrated
- langgraph_pipeline/slack/identity.py - identity module
- langgraph_pipeline/slack/notifier.py - notifier module
- langgraph_pipeline/slack/poller.py - poller module

## Plan

Single verification task to confirm all acceptance criteria and close the item.
