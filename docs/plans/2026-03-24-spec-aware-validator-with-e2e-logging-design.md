# Spec-Aware Validator with E2E Test Logging - Completion Design

## Overview

The spec-aware validator feature is mostly implemented. This plan completes the
remaining gap: the `validator.md` agent definition still uses a generic pnpm E2E step
instead of the spec-aware pattern (read `### Verification` blocks from changed spec
files, run referenced Playwright tests, save timestamped JSON to `logs/e2e/`). Two
pre-existing unit test failures also need to be fixed before the version is bumped.

## Current State

### Already implemented

- `parse_verification_blocks(content)` helper in `langgraph_pipeline/executor/nodes/validator.py`
- `DEFAULT_SPEC_DIR = ""` and `SPEC_DIR` config reading from orchestrator config
- `DEFAULT_E2E_COMMAND` and `E2E_COMMAND` constants
- `_build_validator_prompt()` injects spec-aware context block when `SPEC_DIR` is set
- `.claude/agents/e2e-analyzer.md` — on-demand test log analyzer agent
- `docs/templates/verification-block.md` — reference template for spec authors
- Unit tests for `parse_verification_blocks()` (6 tests, all passing)
- Unit tests for `build_validation_prompt()` spec context injection (3 tests, all passing)

### Still missing

1. `validator.md` spec-aware step — the agent must be told to check git diff for
   spec file changes, read `### Verification` blocks, and run the referenced tests
2. Two failing unit tests from a zero-padding refactor in backlog item filenames
   (`1-` prefix changed to `01-`, tests still assert old format)
3. Plugin version bump and release notes for the completed feature set

## Architecture

### Validator spec-aware flow

```
validator agent session
    |
    +-- Step 3 (NEW): Spec-Aware E2E (only if validation prompt includes spec context)
    |   |
    |   +-- git diff --name-only HEAD~1 HEAD
    |   +-- filter files under SPEC_DIR from the prompt
    |   +-- for each changed spec file:
    |   |     read file, find ### Verification blocks
    |   |     for each block with Type: Testable:
    |   |       run E2E_COMMAND <test_file> --reporter=json > logs/e2e/<ts>.json
    |   |       parse pass/fail counts
    |   +-- if no spec files changed: note E2E skipped, continue
    |
    +-- Step 4: Code Review (was Step 3)
    +-- Step 5: Requirements (was Step 4)
```

### Project opt-in

Projects opt in via `.claude/orchestrator-config.yaml`:

```yaml
spec_dir: docs/admin-functional-spec/
e2e_command: npx playwright test
```

When `spec_dir` is absent or empty, the validator falls back to generic behavior.

## Key Design Decisions

1. **Spec-aware only when prompt has spec context**: The validator.md step reads
   the prompt to determine whether to apply spec-aware logic — it only runs when
   `build_validation_prompt()` injected the spec context block. This keeps the agent
   usable in projects without `spec_dir` configured.

2. **WARN not FAIL for unrelated E2E failures**: E2E failures for tests not tied
   to the task's spec changes are WARN. Only failures for tests directly referenced
   by the changed spec blocks count as FAIL.

3. **Timestamped JSON files**: Output goes to `logs/e2e/YYYY-MM-DDTHHMMSS.json`,
   which the `e2e-analyzer.md` agent later reads for trend analysis.

## Files Affected

### Modified

- `.claude/agents/validator.md`
  - Insert spec-aware step as Step 3 (between unit tests and code review)
  - Renumber existing Steps 3 and 4 to Steps 4 and 5
  - Add verdict rule: E2E failures for unrelated tests = WARN, related = FAIL
  - Add constraint: save E2E output to `logs/e2e/<timestamp>.json`

- `tests/langgraph/executor/nodes/test_validator.py`
  - Fix `test_create_backlog_item_returns_dict`: assert `startswith("01-")`
  - Fix `test_create_backlog_item_increments_number`: assert `startswith("02-")`

- `plugin.json` + `RELEASE-NOTES.md`
  - Bump minor version (1.9.0 → 1.10.0) for spec-aware validator feature
