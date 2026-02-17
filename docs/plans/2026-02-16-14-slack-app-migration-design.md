# Slack App Migration Design

> **For Claude:** REQUIRED SUB-SKILL: Use the implement skill to execute this plan task-by-task.

**Goal:** Replace the Incoming Webhook transport in SlackNotifier with a Slack App
using the Web API for sending and Socket Mode for receiving interactive responses.

**Architecture:** The migration is a transport-layer swap. The SlackNotifier public
API (send_status, send_defect, send_idea, send_question, process_agent_messages)
is preserved unchanged. Only the internal transport changes: _post_webhook becomes
_post_message using chat.postMessage with Bearer token auth, and the file-based
question polling gets optionally replaced by Socket Mode via slack-bolt. Sending
remains stdlib-only (urllib.request). The slack-bolt dependency is optional - if
not installed, questions fall back to the existing file-based polling.

**Tech Stack:** Python stdlib (urllib.request, json, threading), optional slack-bolt

---

## Key Design Decisions

1. **Sending stays stdlib-only.** The chat.postMessage API is nearly identical
   to the webhook POST - same JSON payload, just with an Authorization header
   and a channel field. No need for an SDK library just for sending.

2. **slack-bolt is optional.** Socket Mode requires a WebSocket client, which
   means a third-party library. But questions are an optional feature - most
   users only need one-way status notifications. Making slack-bolt optional
   keeps the zero-dependency sending path.

3. **Config schema changes.** The webhook_url field is replaced by three new
   fields: bot_token, app_token, channel_id. The channel field (display name)
   becomes channel_id (Slack channel ID, e.g., C0123456789). The notify and
   questions sub-sections remain unchanged.

4. **Socket Mode handler runs in a background thread.** When send_question is
   called, a SocketModeHandler is started (if not already running) in a daemon
   thread. It listens for block_actions events and signals the waiting
   send_question via a threading.Event.

5. **Backward-compatible removal.** Since no users exist yet, we do a clean
   swap: remove webhook_url, add bot_token/app_token/channel_id. No migration
   shim needed.

---

## Config Schema

Current (webhook-based):

    slack:
      enabled: true
      webhook_url: "https://hooks.slack.com/services/T.../B.../xxx"
      channel: "#orchestrator-updates"

New (Slack App):

    slack:
      enabled: true
      bot_token: "xoxb-..."
      app_token: "xapp-..."
      channel_id: "C0123456789"
      notify: ...
      questions: ...

---

## Files to Modify

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | SlackNotifier: replace _post_webhook with _post_message, update __init__ to read new config fields, add Socket Mode handler for questions |
| .claude/slack.local.yaml.template | Replace webhook_url with bot_token/app_token/channel_id, add Slack App setup instructions |
| tests/test_slack_notifier.py | Update all config fixtures to use new fields, add tests for _post_message and Socket Mode fallback |
| scripts/auto-pipeline.py | No code changes needed (uses SlackNotifier public API which is unchanged) |

---

## Phase 1: Config Template Update

### Task 1.1: Update config template

Replace .claude/slack.local.yaml.template with the new Slack App config fields
and add setup instructions as comments.

---

## Phase 2: SlackNotifier Transport Migration

### Task 2.1: Update SlackNotifier config loading and transport

In scripts/plan-orchestrator.py:
- Update SLACK_CONFIG_PATH constants (no change needed - path is the same)
- In __init__: replace self._webhook_url with self._bot_token, self._app_token,
  self._channel_id. Read from config["slack"]["bot_token"], etc.
- Replace _post_webhook with _post_message: POST to
  https://slack.com/api/chat.postMessage with Authorization: Bearer header
  and channel field in payload.
- Update send_status to call _post_message instead of _post_webhook.
- Update send_defect and send_idea to call _post_message.

### Task 2.2: Implement Socket Mode for questions

- Add optional import for slack_bolt at module level (try/except).
- Add SocketModeListener class that manages a background thread running
  SocketModeHandler. It registers a block_actions listener and signals
  pending questions via threading.Event.
- Update send_question to use Socket Mode if available, fall back to
  file-based polling otherwise.
- Post question messages with Block Kit action buttons (not just text).

---

## Phase 3: Unit Tests

### Task 3.1: Update unit tests for new transport

- Update all config fixtures: replace webhook_url with bot_token + channel_id.
- Replace test_post_webhook_called_on_send_status with test_post_message_called.
- Add test for _post_message method signature and behavior.
- Add test for Socket Mode fallback (slack-bolt not available).
- Add test for question message with Block Kit action buttons.
- Verify all existing behavioral tests still pass with new config schema.

---

## Phase 4: Verification

### Task 4.1: Syntax and test verification

- python3 -c "import py_compile; py_compile.compile(...)" for both scripts
- python3 -m pytest tests/ to verify all tests pass
- Dry-run to verify no startup errors
