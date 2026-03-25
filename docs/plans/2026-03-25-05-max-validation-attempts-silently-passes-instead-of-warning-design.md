# Max Validation Attempts Silently Passes Instead of Warning - Design

## Overview

When `max_validation_attempts` is exceeded in `validate_task`, the node was returning
`last_validation_verdict: "PASS"` and logging "treating as PASS". This hides real
validation failures behind a false success signal.

The fix returns `WARN` instead of `PASS`, which exits the retry loop cleanly (since
`retry_check` treats any non-FAIL verdict as `ROUTE_PASS`) while accurately recording
in the plan YAML that validation was abandoned, not passed.

## Current State

All three changes are already present as unstaged modifications in the working tree:

- `langgraph_pipeline/executor/nodes/validator.py`: log message and return value changed
  from "treating as PASS" / `"PASS"` to "treating as WARN" / `"WARN"`
- `tests/langgraph/executor/nodes/test_validator.py`: test renamed and assertion updated
  to expect `"WARN"`

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/executor/nodes/validator.py` | Return WARN instead of PASS at max attempts |
| `tests/langgraph/executor/nodes/test_validator.py` | Assert WARN, rename test accordingly |
| `plugin.json` | Patch version bump (1.9.0 → 1.9.1) |
| `RELEASE-NOTES.md` | New entry for 1.9.1 |

## Design Decisions

**WARN not FAIL**: Using `FAIL` would trigger another task execution retry, creating
an infinite loop (validator immediately exceeds the limit again → FAIL → retry → repeat).
`WARN` exits the loop while signaling inconclusive validation to operators via
`validation_findings`.

**No schema changes**: `WARN` is an existing valid verdict value. No state or graph
changes are required.
