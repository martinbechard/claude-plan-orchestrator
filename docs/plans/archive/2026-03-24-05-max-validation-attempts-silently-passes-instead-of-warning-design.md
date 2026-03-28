# Max Validation Attempts Silently Passes Instead of Warning - Design

## Overview

When `max_validation_attempts` is exceeded in `validate_task`, the node was returning
`last_validation_verdict: "PASS"` and logging "treating as PASS". This hides real
validation failures behind a false success signal.

The fix returns `WARN` instead of `PASS`, which exits the retry loop cleanly (since
`retry_check` treats any non-FAIL verdict as `ROUTE_PASS`) while accurately recording
in the plan YAML that validation was abandoned — not passed.

## Current State

The fix is already applied as an unstaged change in:
`langgraph_pipeline/executor/nodes/validator.py` (lines 317-322)

- Log message changed from "treating as PASS" to "treating as WARN"
- Return value changed from `"PASS"` to `"WARN"`

The unit test `test_returns_warn_when_max_validation_attempts_exceeded` already
asserts `WARN` behavior and will pass once the change is committed.

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/executor/nodes/validator.py` | Already modified (unstaged) |
| `plugin.json` | Patch version bump (1.9.0 → 1.9.1) |
| `RELEASE-NOTES.md` | New entry for 1.9.1 |

## Design Decisions

**WARN not FAIL**: Using `FAIL` would trigger another task execution retry, causing
an infinite loop (validator immediately exceeds the limit again). `WARN` exits the
loop while signaling inconclusive validation to operators via `validation_findings`.

**No schema changes**: `WARN` is an existing valid verdict value. No state or graph
changes are required.
