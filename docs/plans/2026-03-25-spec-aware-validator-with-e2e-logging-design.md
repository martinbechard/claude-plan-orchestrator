# Spec-Aware Validator with E2E Test Logging - Completion Design

## Overview

Completion pass for the spec-aware validator feature. Core infrastructure
(plan-orchestrator.py changes, e2e-analyzer agent, verification block template)
was implemented in February 2026 but the plan had merge conflicts that left
`validator.md` unmodified. Additional test regressions appeared since then.

## Already Implemented

- `scripts/plan-orchestrator.py`:
  - `DEFAULT_SPEC_DIR`, `DEFAULT_E2E_COMMAND` constants (lines 62-63)
  - `SPEC_DIR`, `E2E_COMMAND` config values read from orchestrator-config.yaml (lines 377-378)
  - `parse_verification_blocks()` helper function (line 412)
  - `build_validation_prompt()` includes spec-aware context when SPEC_DIR is set (line 1765)
- `.claude/agents/e2e-analyzer.md`: On-demand analyzer for accumulated E2E test logs.
- `docs/templates/verification-block.md`: Reference format for verification blocks.

## What Remains

### 1. validator.md — spec-aware E2E step

Add a new `### Step 3: Spec-Aware E2E Tests` between the current Step 2 and Step 3,
gated on the presence of a `## Spec-Aware Validation` section in the prompt:

1. Run `git diff --name-only HEAD~1 HEAD` to find changed files
2. Filter for files under the spec directory named in the prompt
3. For each changed spec file, find `### Verification` blocks with `Type: Testable`
   and a `Test file(s):` reference
4. Run the E2E test command with `--reporter=json`, save to `logs/e2e/<YYYY-MM-DDTHHMMSS>.json`
5. Parse pass/fail counts and include in findings as [PASS] or [FAIL] lines
6. If no spec files changed, note that E2E tests were skipped

Renumber existing Step 3 (E2E Test), Step 4 (Code Review), Step 5 (Requirements)
to Step 4, Step 5, Step 6.

Verdict rule additions:
- WARN: E2E failures for tests not directly related to the task's spec changes
- FAIL: E2E failures for tests directly referenced by the task's changed spec files

Constraint additions:
- Always use `--reporter=json` and save to `logs/e2e/` with YYYY-MM-DDTHHMMSS filename
- Only run spec-aware E2E when the prompt contains `## Spec-Aware Validation`

### 2. Test failures

Two categories require fixes:

- `tests/test_plan_orchestrator.py`: 2 assertion failures — backlog filename format
  changed from `1-slug.md` to `01-slug.md` (zero-padded) but test assertions
  were not updated.

- `tests/test_auto_pipeline.py` and `tests/test_completed_archive.py`: Collection
  errors because `CompletionTracker` was removed from `auto_pipeline.py` but the
  tests still reference it at import time.

### 3. Plugin version bump

Bump `plugin.json` from `1.9.3` to `1.10.0` (minor — spec-aware validation is
now fully wired end-to-end) and add a `RELEASE-NOTES.md` entry.

## Architecture Reference

```
build_validation_prompt()  (plan-orchestrator.py)
    |
    v  (includes spec_dir + e2e_command from config when SPEC_DIR set)
validator agent session
    |
    +---> git diff --name-only  (find changed spec files)
    +---> Read spec files, parse ### Verification blocks
    +---> Filter: Type: Testable blocks with Test file(s) references
    +---> Run E2E tests with --reporter=json
    +---> Write timestamped JSON to logs/e2e/
    +---> Include E2E pass/fail in verdict
```

## Files Affected

| File | Action |
|------|--------|
| `.claude/agents/validator.md` | Modify — add spec-aware step |
| `tests/test_plan_orchestrator.py` | Modify — fix zero-padded filename assertions |
| `tests/test_auto_pipeline.py` | Modify — remove or fix CompletionTracker reference |
| `tests/test_completed_archive.py` | Modify — remove or fix CompletionTracker reference |
| `plugin.json` | Modify — version 1.9.3 to 1.10.0 |
| `RELEASE-NOTES.md` | Modify — add 1.10.0 entry |
