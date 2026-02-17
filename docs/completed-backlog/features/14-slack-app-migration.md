# Migrate Slack Integration from Webhook to Slack App

## Status: Open

## Priority: High

## Summary

Replace the Incoming Webhook transport in SlackNotifier with a Slack App using the
Web API for sending and Socket Mode for receiving. This eliminates the need for a
separate webhook URL configuration - a single Slack App provides bidirectional
communication using only outbound connections (no public endpoint needed, works
behind NAT/firewalls on a local desktop).

The existing SlackNotifier public API, lifecycle hooks, and test structure are
preserved. Only the transport layer changes.

## Problem

The current implementation (feature 13) uses Slack Incoming Webhooks for sending
and file-based polling for receiving answers. This has two issues:

1. **Two configurations needed**: The webhook URL is a separate artifact from any
   Slack App. If we want bidirectional communication (questions with button answers),
   we need both a webhook AND something else (Socket Mode or polling).

2. **File-based polling is fragile**: The `send_question` method writes a JSON file,
   then polls for an answer file every 30 seconds. This requires an external process
   to watch Slack and write the answer file, which doesn't exist yet.

A single Slack App with Socket Mode solves both: one app, one config, true
bidirectional communication.

## What Changes

### Transport Layer (replace)

| Current | New |
|---------|-----|
| `_post_webhook()` using webhook URL | `_post_message()` using `chat.postMessage` API |
| `webhook_url` in config | `bot_token` + `app_token` + `channel_id` in config |
| File-based polling in `send_question` | Socket Mode listener for interactive responses |

### Config Schema (update)

Current `.claude/slack.local.yaml`:

    slack:
      enabled: true
      webhook_url: "https://hooks.slack.com/services/T.../B.../xxx"

New:

    slack:
      enabled: true
      bot_token: "xoxb-..."         # Bot User OAuth Token (chat:write scope)
      app_token: "xapp-..."         # App-Level Token (connections:write scope)
      channel_id: "C0123456789"     # Channel ID to post to
      notify: ...                   # unchanged
      questions: ...                # unchanged

### What Stays the Same (no changes)

- `is_enabled()`, `_should_notify()`, `_build_status_block()` - config/formatting logic
- `send_status()`, `send_defect()`, `send_idea()` - public API (calls `_post_message`
  instead of `_post_webhook`, same signature)
- `process_agent_messages()` - dispatch logic
- All lifecycle hooks in `plan-orchestrator.py` and `auto-pipeline.py`
- `.gitignore` entries
- Most unit tests (config loading, formatting, disabled mode, agent messages)

## Proposed Design

### Sending: Web API via urllib (stdlib only)

The `chat.postMessage` endpoint is a simple HTTP POST, just like the webhook
but with an Authorization header and a channel field:

    def _post_message(self, payload: dict) -> bool:
        if not self._bot_token or not self._channel_id:
            return False
        payload["channel"] = self._channel_id
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {self._bot_token}"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)

This keeps the zero-dependency approach (stdlib only for sending).

### Receiving: Socket Mode via slack-bolt

For receiving interactive message responses (button clicks on questions), use
the `slack-bolt` library with Socket Mode:

    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

The Socket Mode handler runs in a background thread, listening for action
events (button clicks) via an outbound WebSocket. When a button is clicked,
it writes the answer and signals the waiting `send_question` method.

This is the only part that requires an external dependency (`slack-bolt`).
Make it optional: if `slack-bolt` is not installed, questions fall back to
the existing file-based polling. Sending always works (stdlib only).

    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
        SOCKET_MODE_AVAILABLE = True
    except ImportError:
        SOCKET_MODE_AVAILABLE = False

### Question Flow with Socket Mode

1. `send_question()` posts a message with Block Kit action buttons
2. Socket Mode handler listens for `block_actions` events
3. When user clicks a button, handler receives the action
4. Handler writes the answer to a threading.Event or shared variable
5. `send_question()` (blocked on the Event) receives the answer and returns

If `slack-bolt` is not installed, fall back to the current file-based polling.

### Slack App Setup (one-time, documented)

Users create a Slack App once:
1. Go to api.slack.com/apps, create new app
2. Enable Socket Mode (generates app_token)
3. Add Bot Token Scopes: `chat:write`, `channels:read`
4. Install to workspace (generates bot_token)
5. Invite bot to channel, note the channel_id
6. Put tokens in `.claude/slack.local.yaml`

Document this as a step-by-step guide in the config template.

## Verification

- Update config template with new token fields
- Replace `_post_webhook` with `_post_message`, verify sending works
- Install `slack-bolt`, verify Socket Mode receives button clicks
- Verify fallback to file polling when `slack-bolt` is not installed
- Update unit tests for new config keys and transport method
- Verify all lifecycle hooks still work (plan start/complete, task events)
- Verify disabled mode still works (no config file = silent no-ops)

## Files Likely Affected

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | SlackNotifier transport swap, Socket Mode handler |
| .claude/slack.local.yaml.template | New config fields (bot_token, app_token, channel_id) |
| tests/test_slack_notifier.py | Update config fixtures, add transport tests |

## Dependencies

- 13-slack-agent-communication.md (completed): Existing SlackNotifier infrastructure
