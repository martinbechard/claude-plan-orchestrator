# @CPO-Pipeline Feature request: Improve verbose mode logging for inbound Slack me

## Status: Open

## Priority: Medium

## Summary

**Title:** Add verbose logging for agent identity message filtering decisions

**Classification:** feature - This is a new observability capability; the filtering logic works correctly but provides no diagnostic output.

**5 Whys:**

1. **Why do we need verbose logging for inbound Slack message filtering?**
   Because when messages are silently skipped via `continue` statements in the agent identity filtering block (lines 4826-4843), operators have zero visibility into why a message was accepted or rejected.

2. **Why is there zero visibility into these filtering decisions?**
   Because the filtering block was implemented as pure guard clauses — each rule either `continue`s or falls through — without any `verbose_log()` calls, unlike other subsystems (task finding, permissions) that already use the verbose logging convention.

3. **Why weren't verbose logs included when the agent identity filtering was originally built?**
   Because the implementation prioritized correctness of the four filtering rules (skip-own, skip-addressed-to-others, process-addressed-to-us, process-broadcast), and multi-instance setups that would expose the observability gap weren't yet in active use.

4. **Why does the lack of logging become a problem specifically in multi-instance setups?**
   Because shared Slack channels carry messages from multiple orchestrator instances with different agent identities, and a single misrouted or silently dropped message can stall a cross-project workflow with no diagnostic trail.

5. **Why is an undiagnosed message drop so damaging to cross-project workflows?**
   Because the pipeline operates autonomously — no human is watching in real-time — so a silently filtered question or request only surfaces later as a stalled plan or unanswered query, and without logs the root cause is invisible, requiring manual channel archaeology to reconstruct what happened.

**Root Need:** Autonomous multi-instance pipelines require auditable message routing decisions so that silent message drops can be diagnosed without human real-time monitoring.

**Description:**
Add `verbose_log()` calls to each branch of the agent identity filtering block in `_process_inbound_messages()` (plan-orchestrator.py, lines 4826-4843). Each of the four filtering outcomes — skip-own-agent, skip-addressed-to-others, process-addressed-to-us, and process-broadcast — should emit a structured log line including the channel name, the parsed signature or addressee, and the decision rationale. This aligns the message filtering subsystem with the existing `verbose_log()` convention used throughout the codebase, enabling operators to diagnose cross-instance routing issues by simply enabling `--verbose`.

## Source

Created from Slack message by U0AFJJ9KZQW at 1771556073.098519.
