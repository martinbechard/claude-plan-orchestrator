# Self-skip filter drops legitimate messages

## Status: Open

## Priority: High

## Summary

**Title:** Replace overly aggressive self-skip filter with a loop-prevention mechanism that does not drop legitimate messages

**Description:**
The inbound message filtering in _handle_polled_messages() has a self-skip check that was originally based on channel name, then replaced with a bot_id check (Rule 0), and a signature-based text check (Rule 1). The intent is to prevent the orchestrator from processing its own messages in an infinite loop. However, the current approach is too broad --- it drops many messages that should be processed.

The bot_id check (Rule 0) skips ALL messages from the bot, regardless of whether processing them would cause a loop. The signature check (Rule 1) skips messages matching a text pattern, which can false-positive on legitimate content. Both approaches conflate "this message was sent by us" with "processing this message would cause a loop", and those are not the same thing.

## Root Cause

The self-skip logic assumes that any message originating from the bot should be ignored. This is incorrect. The actual problem to solve is loop prevention: the bot should not re-process a message in a way that causes it to generate the same message again, creating an infinite cycle. Many bot-originated messages (status updates, notifications, cross-project reports) are informational and do not trigger re-processing. Skipping all of them silently drops content that other parts of the system or other instances may need to act on.

## Expected Behavior

The system should prevent infinite message-processing loops WITHOUT dropping legitimate messages. A smarter approach could include:

- Tracking which message timestamps have already been processed (deduplication) rather than filtering by sender identity
- Using a "processing context" flag so the bot knows when it is acting on a polled message vs. generating an original outbound message
- Rate-limiting or circuit-breaking on rapid self-replies to the same thread rather than blanket-skipping by sender
- Any other mechanism that targets the actual loop condition instead of the message origin

The key insight: the goal is to avoid processing the SAME message twice or reacting to our own reaction, not to ignore everything we ever said.

## Actual Behavior

Rule 0 (bot_id match) and Rule 1 (signature pattern match) silently skip messages that the bot posted. This causes:

1. Cross-instance messages posted by this bot to shared channels are ignored when polled back
2. Status updates and notifications are dropped if they happen to match the filter criteria
3. Legitimate inbound content is lost with no indication to the user

## Fix Required

1. Remove the bot_id blanket skip (Rule 0) and the signature-based skip (Rule 1) entirely --- these are all variations of the same wrong approach (skip by sender identity)
2. Implement a true infinite loop detector that targets the actual loop condition: the bot re-processing a message it already processed, or reacting to its own reaction in a cycle. For example, track processed message timestamps and skip only exact duplicates, or detect rapid self-reply chains in the same thread
3. Ensure legitimate bot-originated messages (status updates, cross-instance reports, notifications) are processed normally
4. Add logging that distinguishes "skipped: already processed" from "skipped: loop detected"

## Verification

- Send a message from the bot to a monitored channel and verify it is processed when polled (not silently dropped)
- Verify that the system does not enter an infinite loop when it processes its own status updates
- Verify that cross-instance messages are not dropped
- Check logs for clear indication of why any message was skipped

## Prior Attempts

1. **bot_id check (completed):** Added bot_id as Rule 0, kept signature as Rule 1 fallback. Same wrong approach encoded differently --- still blanket-skips by sender identity.
2. **sent-message-ts tracking (in progress, stale):** Replaced signature regex with timestamp set lookup. More reliable than text matching but still the same wrong approach --- skips all messages the bot posted rather than detecting actual loops. The plan YAML at .claude/plans/1-there-is-a-self-skip-check-that-was-based-on-the-name-of-the-channel--the-idea.yaml should be cleaned up.

## Verification Log

### Task 1.1 - FAIL (2026-02-25 00:07)
  - Validator 'validator' failed to execute: No status file written by Claude
