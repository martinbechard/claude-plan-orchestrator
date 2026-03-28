# Design: Replace Rate-Limited Self-Skip with Unconditional Self-Origin Skip

## Problem

The self-skip filter in _handle_polled_messages() uses a rate-limited window
approach (MAX_SELF_REPLIES_PER_WINDOW=1, LOOP_DETECTION_WINDOW_SECONDS=300)
that is overly complex and was originally based on channel name matching,
then bot_id matching, and now ts-based self-origin detection with windowed
rate limiting.

The user reports that this filter drops legitimate messages it should not.
The windowing approach is unnecessary complexity - the bot should never need
to process its own output messages (status updates, notifications,
acknowledgments, etc.).

## Design Decision

Replace the rate-limited self-origin window with an unconditional self-origin
skip. The bot tracks every message it sends via _own_sent_ts. When polling,
any message whose ts is in _own_sent_ts is unconditionally skipped. This is:

1. Simpler - no window tracking, no rate counting, no per-channel state
2. Correct - the bot never needs to re-process its own output
3. Deterministic - no time-dependent behavior that can cause intermittent drops
4. Safe - self-origin only matches messages the bot actually sent via
   _post_message() / _post_message_get_ts(), so user messages are never affected

## Changes

### scripts/plan-orchestrator.py

1. Remove constants: MAX_SELF_REPLIES_PER_WINDOW, LOOP_DETECTION_WINDOW_SECONDS
2. Remove from __init__: self._self_reply_window dict
3. Simplify _handle_polled_messages() self-origin block:
   - Replace the window + rate-limit check with unconditional skip
   - Log: "[SLACK] Filter: skip self-origin #{channel}: {preview}"
4. Remove self-reply window tracking after routing (the window.append block)
5. Simplify _prune_message_tracking(): remove _self_reply_window pruning
6. Keep MESSAGE_TRACKING_TTL_SECONDS and _processed_message_ts / _own_sent_ts
   pruning unchanged

### tests/test_agent_identity.py

1. Remove tests for loop detection windowing / MAX_SELF_REPLIES_PER_WINDOW
2. Update self-origin tests to verify unconditional skip behavior
3. Verify non-self-origin messages are unaffected

## Files Modified

- scripts/plan-orchestrator.py
- tests/test_agent_identity.py
