# Design: Migrate test_agent_identity.py off legacy plan-orchestrator.py

## Work Item

.claude/plans/.claimed/25-migrate-tests-off-legacy-plan-orchestrator.md

## Overview

`tests/test_agent_identity.py` (64 tests) uses `importlib` to load
`scripts/plan-orchestrator.py` — a 6820-line monolithic script. That script is
the sole blocker preventing its deletion. The migration rewrites the test file to
import from the new `langgraph_pipeline.slack` submodules and then deletes the
legacy script and stale pyc cache.

## New Import Targets

| Symbol | New module |
|---|---|
| `AgentIdentity`, `IdentityMixin`, identity constants | `langgraph_pipeline.slack.identity` |
| `SlackNotifier` (full facade) | `langgraph_pipeline.slack` |
| `SlackNotifier` implementation + `_sign_text` | `langgraph_pipeline.slack.notifier` |
| `SlackPoller`, `_handle_polled_messages`, `bot_user_id` | `langgraph_pipeline.slack.poller` |

## Key Files

| File | Action |
|---|---|
| `tests/test_agent_identity.py` | Rewrite all imports; fix the 27 tests that call methods now on sub-modules |
| `scripts/plan-orchestrator.py` | Delete once all 64 tests pass |
| `tests/__pycache__/test_auto_pipeline*.pyc` | Delete (stale cache) |

## Design Decisions

- Tests that exercise notifier behaviour import directly from
  `langgraph_pipeline.slack.notifier`; tests that exercise poller behaviour
  import from `langgraph_pipeline.slack.poller`. There is no need for test
  helpers — each test instantiates the class that owns the method under test.
- The facade at `langgraph_pipeline.slack` re-exports `SlackNotifier` for
  callers that do not need to reach into sub-modules; tests that only call
  facade-level methods may continue to import from there.
- Deletion of `plan-orchestrator.py` is gated on all 64 tests passing; it is a
  separate task so the validator can confirm the green suite before the delete.
