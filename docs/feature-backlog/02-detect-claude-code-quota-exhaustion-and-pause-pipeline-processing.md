# Detect Claude Code quota exhaustion and pause pipeline processing

## Status: Open

## Priority: Medium

## Summary

Add quota-exhaustion detection to the pipeline by parsing the specific error output Claude Code produces when the subscription usage cap is hit. When detected, the pipeline should immediately pause processing of further backlog items (similar to rate-limit backoff but without retry) and optionally send a Slack notification. Processing should resume automatically once a new quota window begins or when manually unpaused.

## 5 Whys Analysis

  1. **Why do we need to detect when we're out of quota?** Because the pipeline currently continues trying to process backlog items even when Claude Code has no remaining quota, leading to wasted cycles and failed tasks.
  2. **Why do items fail when quota is exhausted?** Because Claude Code CLI invocations return errors or produce no useful output when the account has hit its usage cap, but the pipeline doesn't distinguish this from other transient failures.
  3. **Why doesn't the pipeline already distinguish quota exhaustion from other errors?** Because the existing error handling focuses on rate limits (429/retry-after patterns) and budget ceilings, not on the distinct "out of quota" signal that Claude Code emits when the subscription cap is reached.
  4. **Why is it harmful to keep processing after quota exhaustion?** Because each attempted item burns wall-clock time on doomed subprocess calls, may trigger retry loops, and could corrupt task state by recording incomplete results — requiring manual cleanup later.
  5. **Why can't the operator just stop the pipeline manually?** Because the pipeline is designed to run autonomously (overnight, unattended), and the whole point of automation is to handle predictable failure modes without human intervention — quota exhaustion is a predictable, detectable condition.

**Root Need:** The autonomous pipeline needs to gracefully detect and respond to Claude Code quota exhaustion as a distinct stop condition, pausing all further item processing until quota is restored, to prevent wasted cycles and corrupted task state during unattended runs.

## Source

Created from Slack message by U0AFA7SAEMC at 1774329222.308499.
