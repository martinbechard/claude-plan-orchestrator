# Design: Bot Self-Identity Filter for Slack Poller

## Problem

The Slack poller lacks an identity-based filter. When the orchestrator
sends an acknowledgment message (e.g., "Here is my understanding of your
feature:"), the poller polls it back from the channel, does not recognize
it as self-sent, and routes it to the LLM classifier. The classifier
returns `create_feature`, creating a self-intake loop.

The existing guards are content-based and break whenever the bot produces
a new message format:

- `BOT_NOTIFICATION_PATTERN` regex only matches known notification phrases
- `_is_own_signed_message` only matches messages bearing an agent signature
- `_own_sent_ts` is in-memory and lost on process restart

## Design

Resolve the bot's own Slack user ID at startup via `auth.test` and store it
on the object. In `_handle_polled_messages`, add a primary guard that
unconditionally skips any message whose `user` field equals the bot's own
user ID. Content-based guards remain as a secondary defense.

This is immune to message format changes and process restarts because the
bot's user ID is a stable, external fact (not derived from message content).

## Key Files

- `scripts/plan-orchestrator.py` -- `SlackNotifier` class
- `langgraph_pipeline/slack/poller.py` -- `SlackPoller` class
- `tests/test_agent_identity.py` -- SlackNotifier filter tests
- `tests/langgraph/slack/test_poller.py` -- SlackPoller filter tests

## Changes

### scripts/plan-orchestrator.py -- SlackNotifier

**`__init__`**: Add `self._bot_user_id: Optional[str] = None`.

**New method `_resolve_own_bot_id()`**: Call `auth.test` using `self._bot_token`.
Parse the `user_id` field from the response. On success, set
`self._bot_user_id`. On any error (network, API), log a warning and leave
`self._bot_user_id` as None (graceful degradation).

**Call site**: Invoke `_resolve_own_bot_id()` in `__init__`, after the
config is loaded and `self._bot_token` is set.

**`_handle_polled_messages()`**: Add a check immediately after the dedup
check (before `BOT_NOTIFICATION_PATTERN`):

    if self._bot_user_id and msg.get("user") == self._bot_user_id:
        print(f"[SLACK] Filter: skip own-bot-user #{ch_log}: {preview!r}")
        if ts:
            self._processed_message_ts.add(ts)
        continue

Label this as "A0: Identity-based self-skip" in comments.

### langgraph_pipeline/slack/poller.py -- SlackPoller

Same changes as above, applied to `SlackPoller`:

- `__init__`: Add `self._bot_user_id: Optional[str] = None`.
- Add `_resolve_own_bot_id()` method.
- Call it in `__init__` after token is set.
- Add the user ID check in `_handle_polled_messages()` after the dedup check.

### Test changes

**tests/test_agent_identity.py**: Add a `TestBotUserIdSelfSkip` class with:
- `test_own_user_id_message_is_skipped`: message with `user == bot_user_id`
  is skipped and ts added to `_processed_message_ts`
- `test_different_user_id_passes_filter`: message from a different user
  passes the A0 filter (not skipped by identity check)
- `test_no_bot_user_id_passes_filter`: when `_bot_user_id` is None,
  message is not skipped by A0 (graceful degradation)
- `test_resolve_own_bot_id_sets_user_id`: mock `auth.test` response
  with `user_id`; assert `_bot_user_id` is set correctly
- `test_resolve_own_bot_id_graceful_on_failure`: when `auth.test` raises,
  `_bot_user_id` remains None, no exception propagates

**tests/langgraph/slack/test_poller.py**: Mirror the same test cases for
`SlackPoller`.

## Design Decisions

1. **`user` field, not `bot_id`**: Slack messages from bots carry both `bot_id`
   (the app component ID) and `user` (the bot user ID). `auth.test` returns the
   `user_id`. Using `user` aligns with what `auth.test` provides. A previous
   implementation used `bot_id` (removed in the 2026-02-24 self-skip redesign);
   `user_id` is equally authoritative.

2. **Unconditional skip, no rate limit**: Unlike the ts-based self-origin check
   (which allows the first self-reply through), the identity-based filter skips
   all messages from our own bot user. The only legitimate reason to process a
   self-sent message is cross-project reports from OTHER bot users, which have
   different user IDs. If two orchestrators share the same bot user ID, they
   cannot meaningfully communicate through their shared channels anyway.

3. **Graceful degradation**: If `auth.test` fails, `_bot_user_id` stays None
   and A0 is simply skipped. The existing content-based guards continue to work.

4. **Both implementations**: The monolith and the LangGraph SlackPoller are both
   actively used. Both must be fixed identically to prevent the loop in either
   deployment mode.
