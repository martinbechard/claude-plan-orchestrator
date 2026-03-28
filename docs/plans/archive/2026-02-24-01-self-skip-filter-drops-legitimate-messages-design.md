# Design: Replace Self-Skip Filter with Dedup + Loop Detection

## Problem

The inbound message filtering in _handle_polled_messages() uses two identity-based
rules to prevent the orchestrator from processing its own messages:

- Rule 0: bot_id match (skips ALL messages from our bot)
- Rule 1: AGENT_SIGNATURE_PATTERN match (skips messages signed by our agents)

Both rules conflate "this message was sent by us" with "processing this message would
cause a loop." They silently drop legitimate content: cross-instance reports, status
updates posted by the bot to shared channels, and notifications.

## Design

Replace identity-based filtering with two targeted mechanisms:

### 1. Processed-Message Deduplication

Track the Slack timestamp (ts) of every message successfully routed by
_handle_polled_messages(). Before routing a message, check if its ts was already
processed. If so, skip it. This prevents the same message from being processed twice
across poll cycles.

Data structure: a set of ts strings, pruned periodically to cap memory usage.

### 2. Sent-Message Loop Detection

Track the ts of every message the bot sends to Slack. When a polled message's ts
appears in the sent set, we know it originated from us. Instead of blanket-skipping,
apply a rate-based circuit breaker: count how many self-originated messages have been
processed per channel in a sliding window. If the count exceeds a threshold, skip
with "loop detected" logging. Otherwise, allow processing.

This lets cross-instance reports and informational messages through while preventing
runaway self-reply chains.

## Key Files

- scripts/plan-orchestrator.py -- all changes are in SlackNotifier class

## Changes

### SlackNotifier.__init__()

Add three new instance variables:

- _processed_message_ts: set[str] -- timestamps of already-processed messages
- _own_sent_ts: set[str] -- timestamps of messages we sent
- _self_reply_window: dict[str, list[float]] -- channel_id to list of
  monotonic timestamps when we processed our own messages (for rate detection)

### _post_message() and _post_message_get_ts()

After a successful send, record the returned message ts in _own_sent_ts. For
_post_message() which currently returns bool, parse the ts from the response
(already available in the response JSON) and add it to the set.

### _handle_polled_messages()

Replace Rule 0 and Rule 1 with:

1. Dedup check: if msg ts in _processed_message_ts, skip with log
   "[SLACK] Filter: skip already-processed ts=..."
2. Self-origin check: if msg ts in _own_sent_ts:
   a. Check rate: count entries in _self_reply_window[channel] within
      the last LOOP_DETECTION_WINDOW_SECONDS
   b. If count >= MAX_SELF_REPLIES_PER_WINDOW, skip with log
      "[SLACK] Filter: skip loop-detected channel=..."
   c. Otherwise, log "[SLACK] Filter: accept self-origin" and continue
3. Add ts to _processed_message_ts after routing
4. If self-origin, record monotonic time in _self_reply_window[channel]

Keep Rules 2-4 (@AgentName addressing) unchanged -- they filter by content/
addressing, not sender identity.

### Cleanup

Add _prune_message_tracking() called at the start of each poll cycle. Remove
entries from _processed_message_ts and _own_sent_ts older than
MESSAGE_TRACKING_TTL_SECONDS (default 3600). Prune _self_reply_window entries
outside the detection window.

### Constants

- MAX_SELF_REPLIES_PER_WINDOW = 3 -- max self-originated messages per channel
  before circuit-breaking
- LOOP_DETECTION_WINDOW_SECONDS = 60 -- sliding window for rate detection
- MESSAGE_TRACKING_TTL_SECONDS = 3600 -- TTL for ts sets

### Logging

Two distinct skip reasons in logs:
- "skip already-processed" -- dedup hit (same message seen in prior poll cycle)
- "skip loop-detected" -- self-reply rate exceeded in channel

## Test Updates

Update tests/test_slack_notifier.py and tests/test_agent_identity.py:

- Remove tests for Rule 0 (bot_id blanket skip) and Rule 1 (signature skip)
- Add tests for dedup: same ts processed twice is skipped
- Add tests for sent-ts tracking: _post_message records ts in _own_sent_ts
- Add tests for self-origin allowed: message in _own_sent_ts is processed
  when under the rate limit
- Add tests for loop detection: exceeding MAX_SELF_REPLIES_PER_WINDOW triggers
  circuit breaker
- Add tests for cleanup: old entries are pruned correctly
