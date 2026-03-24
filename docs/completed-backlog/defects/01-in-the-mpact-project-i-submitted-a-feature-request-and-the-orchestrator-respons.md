# in the mpact project, I submitted a feature request and the orchestrator respons

## Status: Open

## Priority: Medium

## Summary

**Title:** Orchestrator's feature-acknowledgment response is not recognized as a bot notification, causing self-intake loop

**Classification:** defect - The orchestrator's own response is being misclassified as a user feature request, creating a feedback loop in the bot-message detection logic.

**5 Whys:**
1. **Why was the orchestrator's acknowledgment treated as a new feature?** Because the message "Here is my understanding of your feature:" was routed to the LLM classifier, which interpreted it as a feature request and returned `create_feature`.
2. **Why did the LLM classifier not recognize this as a bot notification?** Because the LLM prompt's instruction only lists specific phrases ("Feature created", "Feature received", etc.) and this acknowledgment message doesn't match any of them.
3. **Why wasn't the message caught by the regex-based `BOT_NOTIFICATION_PATTERN` filter before reaching the LLM?** Because `BOT_NOTIFICATION_PATTERN` only matches narrow phrases like "Feature received", "Feature created", "Pipeline: processing" — it has no branch for orchestrator acknowledgment formats like "Here is my understanding of your feature."
4. **Why does the bot notification filter rely on matching specific known phrases rather than filtering by message author?** Because the filter is content-based rather than identity-based — it was built incrementally as specific loop patterns were observed, without a fundamental "ignore all messages from self" architectural check.
5. **Why isn't the bot's own user ID used as the primary filter?** Because the Slack poller was never designed with a self-identity check — the bot's own user ID is not resolved at startup and compared against incoming message authors, so there is no identity-based filtering layer at all.

**Root Need:** The Slack poller needs an identity-based filter that unconditionally skips all messages authored by the orchestrator's own bot user, rather than relying solely on fragile content-pattern matching that breaks whenever the bot produces a new message format.

**Description:**
The Slack poller's bot-message detection relies on regex patterns and LLM prompt instructions that enumerate known bot message phrases. When the orchestrator produces a new message format (e.g., "Here is my understanding of your feature:"), it bypasses both filters and gets classified as a user feature request, creating a self-intake loop. The fix should resolve the bot's own Slack user ID at startup and add a primary filter that skips any message from that author, making content-based filters a secondary belt-and-suspenders defense.

## Source

Created from Slack message by U0AEWQYSLF9 at 1774368039.915599.
