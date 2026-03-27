# Design: Validator Marks Incomplete Work as Done (#19)

## Problem

The validator agent was passing work items as complete when acceptance criteria
were only partially satisfied. Specifically, it checked code existence and test
pass/fail but did not detect placeholder content, test fixture data leaking
into production, or acceptance criteria requiring runtime verification.

## Prior Implementation

A previous fix added three sub-checks to Step 5 (Requirements) in
`.claude/agents/validator.md`:

- **5a. Placeholder scan** - greps for TODO, "not yet available", placeholder,
  dummy, fake, FIXME, lorem ipsum in created/modified files and UI pages
- **5b. End-to-end gate** - WARNs on "displays X" / "shows Y" criteria that
  cannot be confirmed without a running server
- **5c. Test-data leak check** - greps source files and databases for known
  test-fixture patterns (foo.py, test-item, suspicious round numbers, etc.)

## Current State Assessment

The validator.md already contains all three sub-checks. This review task needs to:

1. Verify the sub-checks are correctly structured and will trigger during
   validation (correct placement under Step 5, clear WARN/FAIL semantics)
2. Ensure the placeholder patterns list is comprehensive enough
3. Ensure the end-to-end gate covers common acceptance-criteria phrasings
4. Ensure test-data patterns catch realistic scenarios
5. Verify no regressions in other validator steps

## Key Files

| File | Action |
|------|--------|
| .claude/agents/validator.md | Review, potentially strengthen |

## Design Decisions

- **Keep sub-checks within Step 5**: The three sub-checks are gates that run
  before concluding a requirement is satisfied. This placement is correct.
- **WARN vs FAIL semantics**: Placeholder hits that map to unmet acceptance
  criteria are FAIL (not just WARN). End-to-end criteria that cannot be verified
  are WARN. Test data in production is FAIL. These escalation rules are already
  in place.
- **Single task**: Since this is a review-and-fix defect with a prior
  implementation, one task is sufficient to verify and address any gaps.
