# detect when we’re out of quota in claude code, and don’t process any further ite

## Status: Open

## Priority: Medium

## Summary

**Title:** Graceful quota-exhaustion handling: pause pipeline and block intake when LLM is unavailable

**Classification:** feature - Adds new quota-exhaustion detection and coordinated pause/resume behavior that doesn't exist in the current pipeline.

**5 Whys:**

1. **Why do we need to detect when we're out of quota?** Because the pipeline currently continues dispatching work from Slack and backlog folders even when Claude Code has no LLM capacity, leading to failed task executions and wasted cycles.

2. **Why do failed task executions during quota exhaustion cause problems beyond just wasting cycles?** Because the existing failure-handling logic doesn't distinguish "LLM unavailable" from "task itself failed," so quota exhaustion gets misclassified — items may be incorrectly archived, retry counters increment for the wrong reason, and circuit breakers trip on infrastructure issues rather than real defects.

3. **Why doesn't the existing error handling distinguish LLM unavailability from task failure?** Because the system was designed around two failure modes — API rate limits (429s with known reset times) and budget ceilings — but subscription quota exhaustion is a third, unmodeled failure mode with no predictable reset time and system-wide scope.

4. **Why can't the existing rate-limit or budget-ceiling mechanisms be extended to cover quota exhaustion?** Because rate limits are per-request with server-provided retry-after headers, and budget ceilings are locally computed thresholds — both are scoped and predictable. Quota exhaustion is an opaque, account-wide state with no reset signal, requiring a fundamentally different strategy: periodic probing with safe idling rather than timed waits or threshold checks.

5. **Why does the pipeline need to idle safely rather than simply stop and require manual restart?** Because the pipeline is designed for autonomous, long-running operation. Manual intervention defeats its purpose. It needs to self-heal by periodically probing for quota restoration and resuming automatically, while ensuring in-flight plans pause at safe checkpoints rather than being interrupted mid-execution.

**Root Need:** The pipeline needs a system-wide LLM-availability circuit breaker that cleanly separates infrastructure unavailability from task-level failures, enabling autonomous safe idling during quota exhaustion with automatic resume — without corrupting backlog state or interrupting in-flight plans.

**Description:**
Add a global LLM-availability check that detects Claude Code quota exhaustion and puts the pipeline into a paused state. While paused: block new intake from Slack and backlog folder scanning, prevent archiving of backlog items, and allow in-flight plan execution to complete its current step before pausing rather than interrupting mid-plan. Periodically probe for quota restoration and automatically resume normal operation when the LLM becomes available again.

## Source

Created from Slack message by U0AEWQYSLF9 at 1774329137.358479.
