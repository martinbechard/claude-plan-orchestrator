# Design: Replace Text-Based Agent Signature Matching with Slack bot_id

## Problem

Self-loop prevention in the Slack polling pipeline relies on parsing a text
convention (em-dash + bold agent name) from message content. This is fragile:
a format change, Slack truncation, or a human writing matching text can break
the filter. The Slack API provides a reliable, structured alternative via the
bot_id field on messages and the auth.test endpoint.

## Current Architecture

### Outbound (signing)
- SlackNotifier._sign_text() appends " --- *AgentName*" to every posted message
- AgentIdentity.name_for_role() generates the name from project + role config

### Inbound (filtering)
- poll_messages() fetches via conversations.history; bot messages are allowed through
- _handle_polled_messages() Rule 1: extracts signature via AGENT_SIGNATURE_PATTERN
  regex, then calls AgentIdentity.is_own_signature() to check if it belongs to us
- bot_id is only checked in check_suspension_reply() for thread replies, not in
  the main polling loop

### Key file
- scripts/plan-orchestrator.py (all of the above)

## Proposed Changes

### 1. Retrieve own bot_id at startup via auth.test

Add a method to SlackNotifier that calls Slack's auth.test API. This returns
the bot's own bot_id (and user_id). Store as self._own_bot_id.

Call this during SlackNotifier initialization (after token is validated) so
the bot_id is available before any polling begins.

### 2. Add bot_id-based self-skip as the primary filter

In _handle_polled_messages(), add a new Rule 0 (before the existing Rule 1):

- Check if the message has a "bot_id" field
- If message bot_id == self._own_bot_id, skip the message (self-loop)
- Log the skip with a clear label: "[SLACK] Filter: skip own-bot-id"

This is the fast, reliable path: no regex parsing, no text conventions.

### 3. Keep signature-based filter as secondary fallback

Do NOT remove the existing AGENT_SIGNATURE_PATTERN / is_own_signature logic.
Keep it as Rule 1 (now secondary). Reasons:
- Defense in depth: if auth.test fails or bot_id is missing from a message
  for any reason, the text filter still catches it
- Zero-risk migration: existing behavior is preserved exactly

### 4. Log auth.test result at startup

Print the resolved bot_id at startup so operators can verify the identity
is correct. If auth.test fails, log a warning but continue (the text-based
filter still works).

### 5. Update tests

Add tests for:
- auth.test call and bot_id storage
- bot_id-based self-skip in _handle_polled_messages
- Fallback to signature-based filter when bot_id is unavailable
- auth.test failure graceful degradation

## Files to Modify

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Add auth.test call in SlackNotifier, add bot_id filter rule in _handle_polled_messages |
| tests/test_agent_identity.py | Add tests for bot_id-based filtering |
| tests/test_slack_notifier.py | Add tests for auth.test call and bot_id storage |

## Design Decisions

1. **bot_id over app_id**: bot_id is per-app and present on every bot-posted
   message. app_id requires extra API calls. bot_id is the right granularity.

2. **Keep signature filter**: Defense in depth. The text filter becomes a
   secondary safety net rather than the primary mechanism.

3. **No message metadata changes**: The defect asks about Slack metadata as an
   option, but bot_id alone is sufficient for self-loop prevention. Message
   metadata would add complexity for multi-project-same-app scenarios which
   are not currently supported.

4. **Graceful degradation**: If auth.test fails at startup (e.g., network
   issue), the system continues with the existing text-based filter, logging
   a warning. No hard failure.
