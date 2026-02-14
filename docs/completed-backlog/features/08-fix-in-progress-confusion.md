# Fix Subagent Confusion About in_progress Task Status

## Status: Open

## Priority: High

## Summary

When the orchestrator launches a Claude subagent for a task, the subagent reads the YAML
plan and sees its own task marked as in_progress. Combined with the prompt instruction
"a previous attempt may have failed", the subagent concludes it is resuming a failed
prior attempt and wastes turns investigating non-existent prior state. On attempt 1,
there is no prior state - the orchestrator simply sets in_progress before spawning Claude.

## Root Cause

Two things combine to cause the confusion:

1. The orchestrator sets task.status = "in_progress" in the YAML (line ~1917) and saves
   the file BEFORE launching the Claude subprocess (line ~1938). So when Claude reads
   the plan YAML as its first action, it sees its own task as in_progress.

2. The prompt template (build_claude_prompt, line ~1154) always includes:
   "First, verify the current state - a previous attempt may have failed"
   This primes Claude to interpret in_progress as evidence of a prior failed run.

## Observed Behavior

From orchestrator logs for task 6.1 (attempt 1):

Claude reads the plan YAML, sees status: in_progress, and says:
"Good - this is task 6.1, already marked as in_progress from a previous attempt.
The task-status.json doesn't exist, so the previous attempt didn't complete."

In this case Claude proceeded correctly, but it wasted turns on false investigation.
In worse cases, a subagent could decide to skip work it thinks was "partially done"
by a prior attempt.

## Proposed Fix

Pass the attempt number into build_claude_prompt (already available from task["attempts"])
and adjust the prompt accordingly:

- On attempt 1: Remove or replace the "previous attempt may have failed" instruction.
  Instead say something like: "The task status shows in_progress because the orchestrator
  assigned it to you. This is a fresh start."

- On attempt 2+: Keep the retry instruction but make it explicit: "This is attempt N.
  A previous attempt failed. Check the current state before proceeding - some work may
  already be done."

## Files Affected

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Pass attempt number to build_claude_prompt, conditionally include retry instructions |
