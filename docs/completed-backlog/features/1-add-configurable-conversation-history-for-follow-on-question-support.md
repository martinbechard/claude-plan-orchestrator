# Add Configurable Conversation History for Follow-on Question Support

## Status: Open

## Priority: Medium

## Summary

Extend the orchestrator's question-answering flow to maintain a configurable rolling window of prior Q&A exchanges (e.g., last N turns), injecting that history into each new question's prompt. The window size should be configurable (defaulting to a sensible low value like 3–5 turns) to give users control over the cost/context trade-off. This enables iterative, follow-on questions without requiring users to restate background context each time, making the orchestrator genuinely useful for multi-step investigation and design exploration.

## 5 Whys Analysis

  1. **Why do we need conversation history?** Because each question to the orchestrator is currently stateless, so follow-on questions lose all prior context.
  2. **Why does losing prior context matter?** Because users must repeat background information in every question, making iterative investigation slow and tedious.
  3. **Why is iterative investigation important?** Because diagnosing complex pipeline issues or exploring feature designs requires building on previous answers, not starting fresh each time.
  4. **Why can't users work around this today?** Because the orchestrator's Q&A channel is the interface for interacting with the running system, and there is no external mechanism to inject prior context into it.
  5. **Why is a *rolling* (not full) history the right shape?** Because unbounded history would bloat token usage and cost on every question, while a configurable window lets users balance context depth against cost.

**Root Need:** Users need the orchestrator's Q&A interaction to behave like a real conversation — retaining enough recent context to support multi-step reasoning — without incurring unbounded token costs.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771419471.128489.
