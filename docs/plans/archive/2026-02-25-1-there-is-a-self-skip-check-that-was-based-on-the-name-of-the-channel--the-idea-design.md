# Design: Fix Self-Skip Filter Dropping Legitimate Messages

## Background

The Slack inbound message filter in _handle_polled_messages() went through three
iterations of self-skip logic:

1. Channel-name-based check (original, too broad)
2. bot_id blanket skip + signature pattern skip (still too broad)
3. Dedup + loop detection (current code, correct approach)

The code for iteration #3 is already implemented in plan-orchestrator.py
(lines ~4183-4268). However, two issues remain:

- Dead code from iterations #1 and #2 still exists (AGENT_SIGNATURE_PATTERN regex,
  is_own_signature method)
- Tests still reference the old Rule 0 (bot_id blanket skip) and Rule 1
  (signature skip) logic that no longer exists
- No tests cover the new dedup + loop detection mechanism

## Current Architecture

The current filtering logic in _handle_polled_messages():

1. **Dedup check**: Skip messages whose ts is already in _processed_message_ts
2. **Self-origin + loop detection**: If ts is in _own_sent_ts, count recent
   self-replies per channel. Skip only if exceeding MAX_SELF_REPLIES_PER_WINDOW
   (3) within LOOP_DETECTION_WINDOW_SECONDS (60s)
3. **Rules 2-4**: @AgentName addressing logic (unchanged, still correct)
4. **Post-routing tracking**: Add ts to _processed_message_ts, record
   self-reply window timestamps

Supporting infrastructure:
- _own_sent_ts: populated in _post_message() and _post_message_get_ts()
- _prune_message_tracking(): cleans stale entries from all tracking sets
- Constants: MAX_SELF_REPLIES_PER_WINDOW, LOOP_DETECTION_WINDOW_SECONDS,
  MESSAGE_TRACKING_TTL_SECONDS

## Changes Required

### 1. Remove dead code from plan-orchestrator.py

- Remove AGENT_SIGNATURE_PATTERN constant (line 183) - no longer referenced
  in filtering logic
- Remove is_own_signature() method from AgentIdentity class (line 1027-1029) -
  no longer called from _handle_polled_messages

### 2. Update tests in test_agent_identity.py

- Remove TestBotIdSelfSkipFilter class (tests Rule 0 bot_id blanket skip that
  no longer exists)
- Remove is_own_signature tests from TestAgentIdentity (tests dead code)
- Remove AGENT_SIGNATURE_PATTERN tests from TestRegexPatterns
- Add new test class for dedup + loop detection:
  - Dedup: same ts processed twice is skipped on second encounter
  - Self-origin accepted: message in _own_sent_ts processed when under rate limit
  - Loop detected: message in _own_sent_ts skipped when exceeding window threshold
  - Prune: old entries removed from tracking sets
  - _post_message records ts in _own_sent_ts

## Key Files

- scripts/plan-orchestrator.py - remove dead code
- tests/test_agent_identity.py - replace old tests with new ones

## Design Decisions

- The code implementation is correct and already in place; this plan focuses on
  cleanup and test alignment
- Keep the approach simple: single task for dead code removal, single task for
  test updates
- No new features or behavior changes needed
