# Design: Replace Signature-Based Self-Skip with Sent-Message Tracking

## Problem

The self-loop prevention filter in Slack message polling still drops legitimate
messages. The previous fix (adding bot_id as Rule 0) was correct but incomplete:
the fragile text-based AGENT_SIGNATURE_PATTERN filter was kept as Rule 1 fallback.
This regex-based filter matches any message ending with the agent signature pattern
regardless of source, causing false positives on:
- Human messages that quote or copy-paste bot responses
- Messages from other bots using similar formatting
- Cross-project messages in shared workspaces

The user explicitly asked for "a smarter rule or get rid of this rule altogether"
because "it's just ignoring a lot messages it shouldn't."

## Current Architecture

### Self-loop prevention filters (_handle_polled_messages)
- Rule 0: bot_id match (structural, reliable) -- skips messages from our own Slack app
- Rule 1: AGENT_SIGNATURE_PATTERN regex (text-based, fragile) -- skips messages
  ending with the em-dash + bold agent name pattern. THIS IS THE PROBLEM.
- Rules 2-4: @AgentName addressing (routing, not loop prevention)

### Message posting
- _post_message(): Posts via chat.postMessage, returns bool only
- _post_message_get_ts(): Posts via chat.postMessage, returns message ts
- _build_status_block(): Appends agent signature to message text for display

### Key file
- scripts/plan-orchestrator.py (all filtering and posting logic)

## Proposed Changes

### 1. Add sent-message timestamp tracking

Add a set to SlackNotifier that records the Slack ts of every message posted
by this bot instance:

- New constant: SENT_TS_CACHE_MAX = 500
- New field: self._sent_message_ts: set[str] = set()
- New method: _track_sent_ts(ts) adds ts to the set, clears when exceeding max
- Modify _post_message() to capture and track the returned ts
- Modify _post_message_get_ts() to track the returned ts

### 2. Replace Rule 1 with sent-ts filter

In _handle_polled_messages(), replace the AGENT_SIGNATURE_PATTERN-based Rule 1
with a sent-message-ts check:

- If msg["ts"] is in self._sent_message_ts, skip the message
- Log: "[SLACK] Filter: skip sent-message-ts"

This is structural (timestamp-based, not text-based) and has zero false positives:
only messages actually posted by this bot instance are skipped.

### 3. Keep bot_id (Rule 0) as primary filter

bot_id matching remains the primary self-loop prevention. The sent-ts filter
is the secondary fallback for the rare case where:
- auth.test failed at startup (_own_bot_id is None)
- A message was posted but lacks bot_id in conversations.history

### 4. Remove AGENT_SIGNATURE_PATTERN from filtering

- Remove Rule 1 signature matching code from _handle_polled_messages()
- Keep the AGENT_SIGNATURE_PATTERN constant and _sign_text() -- they are still
  used for OUTBOUND message signing (display purposes)
- Keep AgentIdentity.is_own_signature() -- may be used elsewhere
- Update the comment in poll_messages() about bot messages being allowed through

### 5. Update tests

- Remove tests that verify Rule 1 signature-based filtering
- Add tests for sent-message-ts tracking and filtering
- Update existing bot_id tests if needed

## Files to Modify

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Add sent-ts tracking, replace Rule 1, modify posting methods |
| tests/test_agent_identity.py | Remove/update signature filter tests, add sent-ts tests |
| tests/test_slack_notifier.py | Add tests for sent-ts tracking in posting methods |

## Design Decisions

1. **Sent-ts over signature regex**: The root cause of false message drops is
   text-based pattern matching. Sent-ts tracking is structural and can only
   match messages this bot instance actually posted. Zero false positives.

2. **Simple set with clear-on-overflow**: A set of ts strings with a max size
   of 500 provides O(1) lookup. When the cache exceeds max, clearing it is
   safe because entries older than ~500 messages are beyond the polling window.

3. **Keep outbound signing**: The signature appended to outbound messages
   (em-dash + bold agent name) serves a display purpose (users can see which
   agent posted). Only the inbound FILTERING on this pattern is removed.

4. **Two structural filters**: bot_id (Rule 0) + sent-ts (Rule 1) provide
   defense in depth using only structured Slack API data, never text parsing.
