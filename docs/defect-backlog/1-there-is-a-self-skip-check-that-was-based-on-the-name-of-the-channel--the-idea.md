# there is a self-skip check that was based on the name of the channel.  The idea 

## Status: Open

## Priority: Medium

## Summary

there is a self-skip check that was based on the name of the channel.  The idea was to avoid going into an infinite loop however  now it’s just ignoring a lot messages it shouldn’t. when I reported this issue, you just replaced the name check with an id check. This doesn’t address the real issue. Come up with a smarter rule or get rid of this rule altogether. Remember we just want to avoid looping so you can use a different check altogether that doesn’t regularly drop messages

## Source

Created from Slack message by U0AEWQYSLF9 at 1771991860.114539.

## Verification Log

### Task 1.1 - FAIL (2026-02-25 03:50)
  - Validator 'validator' failed to execute: No status file written by Claude

### Verification #1 - 2026-02-25 14:30

**Verdict: PASS**

**Checks performed:**
- [x] Build passes (py_compile on both scripts: SYNTAX OK)
- [x] Unit tests pass (593 passed in 10.43s, including all 33 agent_identity tests)
- [x] Old channel-name-based self-skip removed (no channel_name== or bot_user_id skip logic found)
- [x] Old bot-ID-based self-skip removed (confirmed absent from plan-orchestrator.py)
- [x] New smarter loop detection implemented (dedup via _processed_message_ts + rate-limited self-origin via _own_sent_ts with sliding window)
- [x] Non-self messages are never dropped by loop detection logic
- [x] Self-origin messages are accepted unless rate exceeds MAX_SELF_REPLIES_PER_WINDOW (3) within LOOP_DETECTION_WINDOW_SECONDS (60s)

**Findings:**
The old channel-name and bot-ID based self-skip checks have been completely removed and replaced with a two-layer approach:
1. Dedup layer: skips messages already processed (by timestamp), preventing double-processing
2. Loop detection layer: only skips self-origin messages when rate exceeds 3 per 60s window per channel, acting as a circuit-breaker rather than a blanket filter
This means legitimate messages (including self-origin ones) are processed normally, and only rapid self-reply loops trigger the skip. The reported symptom (messages being incorrectly dropped) is resolved.
