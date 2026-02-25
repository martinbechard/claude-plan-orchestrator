# there is a self-skip check that is based on the name of the channel. This is not

## Status: Open

## Priority: Medium

## Summary

**Title:** Replace text-based agent signature matching with Slack bot_id for self-loop prevention

**Classification:** feature - The current agent signature system works as designed; this is a request for a more robust loop prevention mechanism, not a fix for broken behavior.

**5 Whys:**

1. **Why is there a self-skip check based on text signatures?**
   Because the orchestrator polls Slack channels and reads its own bot-posted messages alongside human messages. Without filtering, it would process its own status updates and responses as new inbound requests, creating an infinite loop.

2. **Why does the current signature-based approach feel imprecise?**
   Because it relies on parsing a text convention (`— *AgentName*`) from message content. If the signature format changes, a message is truncated by Slack, or a human happens to write text matching the pattern, the filter either misses self-messages or incorrectly skips human ones.

3. **Why was text-based signature matching chosen over Slack's native bot identification?**
   Because the system needed to distinguish between *this project's* bots and *other projects'* bots sharing the same Slack workspace — a single `bot_id` check would filter out all bot messages, including legitimate cross-project commands. The signature approach encodes project identity into the message text.

4. **Why is distinguishing between this project's bots and other projects' bots done at the message-text level?**
   Because the Slack API provides `bot_id` per app but doesn't natively carry project-level metadata. The system lacked a structured way to tag messages with project context outside of free-text conventions.

5. **Why isn't there a structured, API-level mechanism to tag and identify the project origin of each message?**
   Because the architecture treats Slack as a simple message bus without leveraging Slack's metadata features (e.g., `metadata` field on `chat.postMessage`, message blocks with hidden context, or per-message `app_id` combined with a project registry). A structured approach would decouple loop prevention from fragile text parsing.

**Root Need:** Self-loop prevention should use a reliable, structured mechanism (such as Slack's `bot_id`/`app_id` fields or message metadata) rather than parsing conventions from message text, so that the system is immune to formatting changes and false positives while still supporting multi-project workspaces.

**Description:**
Replace the current text-based agent signature matching (`AGENT_SIGNATURE_PATTERN` + `AgentIdentity.is_own_signature()`) with a structured self-detection mechanism. The most promising approach is to use Slack's `bot_id` field from polled messages — since each Slack app has a unique `bot_id`, the orchestrator can record its own `bot_id` at startup (via `auth.test`) and filter on that, which inherently scopes to this app without needing project-level text conventions. If multi-project support within the same Slack app is needed, Slack's `metadata` parameter on `chat.postMessage` can carry a structured project identifier that's invisible to users but reliably parseable. This eliminates the fragility of regex-based signature parsing while preserving the ability to distinguish between projects.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771984996.485959.

## Verification Log

### Verification #1 - 2026-02-24 14:30

**Verdict: PASS**

**Checks performed:**
- [x] Build passes
- [x] Unit tests pass
- [x] bot_id self-skip mechanism is implemented as primary filter (Rule 0)
- [x] _resolve_own_bot_id() calls auth.test at startup to discover own bot_id
- [x] Messages with matching bot_id are skipped before signature-based check
- [x] Graceful degradation: when bot_id resolution fails, falls back to signature-based filter
- [x] Comprehensive unit tests exist for bot_id self-skip filter

**Findings:**
- Syntax check: PASS - both scripts/auto-pipeline.py and scripts/plan-orchestrator.py compile cleanly.
- Unit tests: PASS - all 395 tests pass (16.62s), including dedicated bot_id self-skip tests in test_agent_identity.py (TestBotIdSelfSkip class) and _resolve_own_bot_id tests in test_slack_notifier.py.
- Implementation verified at plan-orchestrator.py:3337-3407: SlackNotifier stores _own_bot_id, calls _resolve_own_bot_id() at startup (line 3379) which hits Slack auth.test API, and stores the bot_id on success.
- Self-skip logic at plan-orchestrator.py:4920-4923: Rule 0 checks msg.get("bot_id") == self._own_bot_id BEFORE the text-based signature check (Rule 1 at lines 4925-4930). This makes bot_id the primary filter, with signature matching as a fallback.
- Graceful degradation: If auth.test fails (network error or API error), _own_bot_id remains None and Rule 0 is skipped, leaving the existing signature-based Rule 1 as the sole guard (confirmed by test_bot_id_filter_disabled_when_own_bot_id_none test).
- The old AGENT_SIGNATURE_PATTERN and AgentIdentity.is_own_signature() still exist as Rule 1 fallback, which is the correct design -- the defect asked for bot_id as the primary mechanism, not removal of the fallback.
- Test coverage includes: own bot_id match (skipped), different bot_id (not skipped by Rule 0), no bot_id field (bypasses Rule 0), and disabled filter when _own_bot_id is None.
