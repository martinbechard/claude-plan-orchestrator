---
title: Validator Marks Incomplete Work as Done — Design
date: 2026-03-26
work-item: .claude/plans/.claimed/19-validator-marks-incomplete-work-as-done.md
---

# Design: Validator Marks Incomplete Work as Done

## Problem

The validator agent passes work items that are only partially implemented.
Acceptance criteria involving end-to-end behavior (real data flowing through the
UI) are checked by reading code alone, not by testing the running system. The
validator also does not catch placeholder text, "not yet available" notes, or
test/dummy data left in the output.

## Fix

Update `.claude/agents/validator.md` — specifically **Step 5: Requirements** —
to add three explicit sub-checks before concluding a requirement is satisfied:

1. **Placeholder scan** — grep created/modified files and any referenced UI
   pages for `TODO`, `not yet available`, `placeholder`, `dummy`, `fake`, and
   related strings. Any hit = WARN (or FAIL if it maps to an unmet acceptance
   criterion).

2. **End-to-end gate** — for acceptance criteria that say "displays X", "shows
   Y", or "after at least one worker completes": if the validator cannot confirm
   the behavior against a running server, it MUST report WARN with the note
   "cannot verify at validation time — requires runtime confirmation" rather than
   silently passing.

3. **Test-data leak check** — grep for known test-fixture strings (e.g.
   `foo.py`, `12-test-item`, `test-slug`) in any source file or DB migration
   that should not contain them. Hit = WARN.

## Files Changed

| File | Change |
|------|--------|
| `.claude/agents/validator.md` | Add sub-checks to Step 5 |

## Design Decisions

- Keeping the fix to the agent prompt only avoids touching orchestrator logic.
- The checks are additive (WARN, not FAIL by default) so real build/test
  failures still dominate; the new checks surface overlooked completeness gaps
  without producing false FAILs on items that otherwise compile and test clean.
- Exact strings to scan are listed explicitly in the prompt so the agent does
  not need to infer them.
