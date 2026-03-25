# Spec-Aware Validator with E2E Test Logging - Design Document (Completion)

## Overview

The spec-aware validator feature was partially implemented in a prior session. This
plan completes the remaining work. All read/parse infrastructure already exists;
what remains is wiring SPEC_DIR into the orchestrator config, injecting spec-aware
context into the validation prompt, updating the validator agent, and adding tests.

## Current State

### Already implemented

- `parse_verification_blocks(content)` helper in `scripts/plan-orchestrator.py`
- `DEFAULT_E2E_COMMAND` and `E2E_COMMAND` constants and config reading
- `.claude/agents/e2e-analyzer.md` agent
- `docs/templates/verification-block.md` reference template
- Unit tests for `parse_verification_blocks()`

### Still missing

1. `DEFAULT_SPEC_DIR = ""` constant and `SPEC_DIR = _config.get("spec_dir", ...)` in
   `plan-orchestrator.py` — the config opt-in mechanism
2. Spec-aware context block in `build_validation_prompt()` — injected when SPEC_DIR set
3. Spec-aware step in `.claude/agents/validator.md` — instructions to run git diff,
   read spec files, run E2E tests, and write timestamped JSON to logs/e2e/
4. Unit tests for the SPEC_DIR-gated spec_context in `build_validation_prompt()`

## Architecture

### Processing Flow

```
build_validation_prompt()         (plan-orchestrator.py)
    |
    +-- if SPEC_DIR configured:
    |       inject spec-aware context block into prompt
    v
validator agent session
    |
    +-- git diff --name-only HEAD~1 HEAD  (find changed spec files)
    +-- filter for files under SPEC_DIR
    +-- read spec files, parse ### Verification blocks
    +-- for each Testable block with Test file(s):
    |       run E2E_COMMAND <test_file> --reporter=json
    |       save JSON to logs/e2e/YYYY-MM-DDTHHMMSS.json
    |       parse pass/fail counts
    +-- include E2E results in verdict
```

### Project Opt-in

Projects opt in via `.claude/orchestrator-config.yaml`:

```yaml
spec_dir: docs/admin-functional-spec/
e2e_command: npx playwright test
```

When `spec_dir` is absent or empty, the validator skips E2E and falls back to
generic behavior. Zero impact for projects without functional specs.

## Key Design Decisions

1. **SPEC_DIR empty string default**: Empty string evaluates as falsy in Python,
   cleanly gates all spec-aware logic without a None check.

2. **Prompt injection, not Python logic**: The spec-aware step lives in the
   validator prompt and agent definition — not in Python code. Only the
   config values (SPEC_DIR, E2E_COMMAND) are passed from Python.

3. **Timestamped JSON capture**: `logs/e2e/YYYY-MM-DDTHHMMSS.json` — the
   directory is already in `REQUIRED_DIRS` in `plan-orchestrator.py`.

4. **E2E only when spec files changed**: The validator runs git diff first.
   Pure backend changes without spec file touches skip E2E entirely.

5. **WARN not FAIL for unrelated E2E failures**: E2E failures for tests not
   directly tied to the task's spec changes are WARN, not FAIL.

## Files Affected

### Modified

- `scripts/plan-orchestrator.py`
  - Add `DEFAULT_SPEC_DIR = ""` constant (after `DEFAULT_AGENTS_DIR`)
  - Add `SPEC_DIR = _config.get("spec_dir", DEFAULT_SPEC_DIR)` in config section
  - Update `build_validation_prompt()` to inject spec context when SPEC_DIR is set

- `.claude/agents/validator.md`
  - Insert spec-aware step between "Step 2: Unit Tests" and "Step 3: E2E Test"
  - Update verdict rules: E2E failures for unrelated tests = WARN, related = FAIL
  - Add constraint: save E2E output to `logs/e2e/<timestamp>.json`

### Tests

- `tests/test_plan_orchestrator.py`
  - `test_build_validation_prompt_includes_spec_context`: assert prompt includes
    "Spec-Aware Validation" when SPEC_DIR monkeypatched
  - `test_build_validation_prompt_omits_spec_when_unconfigured`: assert absent
    when SPEC_DIR is empty string
  - `test_build_validation_prompt_standard_checks_present_with_spec`: assert
    BUILD_COMMAND and TEST_COMMAND still appear alongside spec context

## Edge Cases

- **No spec config**: Validator falls back to generic behavior (no E2E tests run)
- **Spec files changed but no Testable blocks**: Validator notes this, skips E2E
- **E2E test command fails**: Validator captures error, includes FAIL finding
- **No JSON output produced**: Validator reports WARN (test ran, output missing)
- **Multiple spec files changed**: All verification blocks aggregated, all tests run
