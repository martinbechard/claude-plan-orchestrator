# Extract Slack Modules

## Status: Open

## Priority: High

## Summary

Extract the SlackNotifier class (~1,500 lines) from plan-orchestrator.py into focused
modules under langgraph_pipeline/slack/. The current SlackNotifier is a monolith that
handles message posting, polling, identity management, and question/suspension flows
in a single class. Breaking it into 4 modules makes each concern independently testable
and reusable by both the existing scripts and the future LangGraph nodes.

## Scope

### Modules to Create

#### slack/notifier.py (~400 lines)
Message posting and channel discovery:
- send_status() -- post to notifications channel
- send_defect_notification() / send_feature_notification()
- _get_channel_id() / _get_notifications_channel_id()
- Channel name resolution and caching
- Message formatting (blocks, sections, code blocks)

#### slack/poller.py (~400 lines)
Inbound message polling and filtering:
- poll_for_messages() -- check channels for new messages
- Message deduplication (replace self-skip filter with message ID tracking)
- Socket Mode event handling (if enabled)
- Rate-limited polling with configurable interval (default 15s)

#### slack/identity.py (~200 lines)
Agent identity and message signing:
- AgentIdentity dataclass
- get_signing_prefix() -- project-specific message signatures
- is_own_message() -- self-message detection
- Multi-project identity support

#### slack/suspension.py (~200 lines)
Question posting and reply polling for human-in-the-loop:
- post_question() -- send question to orchestrator-questions channel
- poll_for_answer() -- wait for human reply
- IntakeState dataclass for 5-Whys flow
- Question history tracking

### Migration Approach

1. Create each slack module with extracted logic
2. Create a slack/__init__.py that re-exports SlackNotifier as a facade for backward
   compatibility (the old scripts call SlackNotifier methods directly)
3. Update plan-orchestrator.py to import from langgraph_pipeline.slack
4. Update auto-pipeline.py to import from langgraph_pipeline.slack (replacing the
   importlib.util-imported SlackNotifier)
5. Add unit tests for each slack module with mocked Slack API calls

### Verification

- SlackNotifier no longer exists as a monolithic class in plan-orchestrator.py
- Both scripts use langgraph_pipeline.slack imports
- Existing Slack functionality works identically (message posting, polling, questions)
- Each slack module has its own test file with mocked Slack API
- No Slack-related code remains in the main scripts except import statements

## Dependencies

- 01-langgraph-project-scaffold.md (needs the package structure to exist)
