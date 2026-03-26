# Workers cannot write task-status.json — blocked by Claude Code sensitive file protection

## Status: Open

## Priority: Critical

## Summary

The Claude CLI treats .claude/plans/task-status.json as a sensitive file and
blocks all writes even when running with --dangerously-skip-permissions. This
means workers can never report task completion. The worker retries Write, Bash
heredoc, and Edit — all denied — then gives up after burning tokens.

## Evidence

Worker log shows 6 consecutive permission denials:
"Claude requested permissions to edit .claude/plans/task-status.json which
is a sensitive file."

Permission mode is "bypassPermissions" but .claude/ paths are always
protected by Claude Code regardless of the mode setting.

## Impact

Without task-status.json, the executor cannot determine if a task succeeded
or failed. The task is treated as failed, triggering retries that also fail
the same way. This is a critical pipeline blocker.

## Fix Options

1. Move task-status.json outside the .claude/ directory (e.g. to a temp
   directory or the project root). This requires changes to both the agent
   prompts (coder.md, validator.md) and the executor code that reads the
   status file.

2. Use a different communication channel: write the status to stdout in a
   parseable format (e.g. a JSON line with a marker prefix) instead of a
   file. The streaming output parser already captures structured events.

3. Add .claude/plans/task-status.json to the allowed writes in the
   permission configuration. Check if --allowedTools or a permission rule
   can override the sensitive file protection for specific paths.

## Acceptance Criteria

- Can a worker write task-status.json without a permission denial?
  YES = pass, NO = fail
- Does the executor correctly read the task outcome from the new location
  or channel? YES = pass, NO = fail
- Do all existing tests pass? YES = pass, NO = fail

## LangSmith Trace: 65b0419e-d2b9-447d-ba14-3faf36038d1e
