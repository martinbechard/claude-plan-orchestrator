# Spec-Aware Validator with E2E Test Logging

## Status: Open

## Priority: High

## Summary

Enhance the validator agent to be functional-spec-aware. When validating a completed
coder task, the validator should read the project's functional specification files,
find the `### Verification` blocks that describe how each requirement is verified,
and run the referenced E2E tests. Results are captured in timestamped JSON files
for later analysis.

This closes the loop between functional specs (which describe what to verify) and
the validation pipeline (which performs verification). The 445 verification blocks
already annotated in the mpact-insight-questionnaire project serve as the template
for this pattern.

## Current State

- The validator agent (`validator.md`) runs build + unit tests + checks task
  requirements generically
- It does NOT look at functional specs or run E2E tests
- Playwright HTML reports get overwritten on each run (no history)
- No agent exists to analyze test results over time

## Proposed Changes

### 1. Enhance validator.md

Add a new validation step between "run unit tests" and "check requirements":

1. Check git diff for modified functional spec files
2. Read the `### Verification` blocks in those spec files
3. For blocks with `Type: Testable` and a `Test file(s):` reference, run those
   specific E2E tests
4. Capture results to a timestamped JSON file using `--reporter=json`
5. Parse the JSON to include E2E pass/fail in the verdict

The validator agent already has Bash access, so it can run:
```
npx playwright test tests/DG01*.spec.ts --reporter=json > logs/e2e/2026-02-18T143022.json
```

### 2. Project-side CLAUDE.md guidance

Projects opt into spec-aware validation by adding to their CLAUDE.md:

- Location of functional spec files (e.g., `docs/admin-functional-spec/`)
- Area code mapping conventions (e.g., DG = diagnostics, CV = conversation viewer)
- E2E test command template (e.g., `npx playwright test`)

### 3. Test results analyzer agent

Create an analyzer agent (`e2e-analyzer.md`) for on-demand review of accumulated
test logs. Capabilities:

- Summarize pass/fail/skip counts across runs
- Identify flaky tests (intermittent failures)
- Detect regressions (tests that started failing after a specific date)
- Compare results between runs

### 4. Verification block format

The validator should parse this structure in functional spec files:

```
### Verification

**Type:** Testable
**Test file(s):** tests/DG01-diagnostics-page-loads.spec.ts
**Status:** Pass

**Scenario:** Verify the diagnostics list page loads and shows the table.
- Route: /admin/diagnostics
- Steps: Sign in as admin, navigate to diagnostics page
- Assertions: Table is visible, at least one row exists
```

Key fields:
- **Type: Testable** = has an E2E test to run
- **Type: Non-E2E** = skip (verified by other means)
- **Type: Blocked** = skip (no UI/API exists yet)
- **Test file(s)** = which Playwright test file(s) to execute
- **Status** = expected result (Pass/Missing/Fail)

## Files Affected

- Modified: `.claude/agents/validator.md` (add spec-aware validation step)
- New: `.claude/agents/e2e-analyzer.md` (test results analyzer)
- New: `docs/templates/verification-block.md` (format reference for projects)

## Design Notes

- The validator runs E2E tests only when functional spec files were touched in the
  task's git diff. Pure backend changes without spec updates skip E2E.
- Timestamped JSON files go in `logs/e2e/` which the orchestrator auto-creates.
- The analyzer agent is invoked on-demand (not part of the validation pipeline).
- Projects without functional specs or verification blocks are unaffected; the
  validator falls back to its current generic behavior.
