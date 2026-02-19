# Spec-Aware Validator with E2E Test Logging - Design Document

## Overview

Enhance the validator agent to be functional-specification-aware. When validating
a completed coder task, the validator reads the project's functional spec files,
finds `### Verification` blocks, and runs referenced E2E tests. Results are
captured in timestamped JSON files for later analysis. A new e2e-analyzer agent
provides on-demand review of accumulated test logs.

## Architecture

### Processing Flow

```
build_validation_prompt()  (plan-orchestrator.py)
    |
    v  (includes spec_dir + e2e_command from config)
validator agent session
    |
    +---> git diff --name-only  (find changed spec files)
    +---> Read spec files, parse ### Verification blocks
    +---> Filter: Type: Testable blocks with Test file(s) references
    +---> Run E2E tests with --reporter=json
    +---> Write timestamped JSON to logs/e2e/
    +---> Include E2E pass/fail in verdict
```

### Project Opt-in

Projects opt into spec-aware validation via orchestrator-config.yaml:

```yaml
spec_dir: docs/admin-functional-spec/
e2e_command: npx playwright test
area_code_mapping:
  DG: diagnostics
  CV: conversation-viewer
```

When spec_dir is not configured, the validator falls back to its current generic
behavior. This is a zero-impact change for projects without functional specs.

### Verification Block Format

The validator parses this structure from functional spec files:

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

Type values:
- Testable = has an E2E test to run
- Non-E2E = skip (verified by other means)
- Blocked = skip (no UI/API exists yet)

## Key Design Decisions

1. **Config-driven opt-in**: The orchestrator passes spec_dir and e2e_command to
   the validator prompt. Projects without config are unaffected.

2. **Validator prompt enrichment, not code**: The validation logic is in the agent
   prompt (validator.md). The only Python change is passing config values into
   build_validation_prompt().

3. **Timestamped JSON logs**: E2E results go to logs/e2e/YYYY-MM-DDTHHMMSS.json.
   The logs/e2e/ directory already exists in REQUIRED_DIRS.

4. **Separate analyzer agent**: The e2e-analyzer is on-demand, not part of the
   validation pipeline. It reads accumulated JSON logs to identify flaky tests,
   regressions, and trends.

5. **Spec changes only trigger E2E**: The validator checks git diff for files
   under spec_dir. If no spec files changed, E2E tests are skipped (existing
   generic validation still runs).

6. **Verification block parsing helper**: A small Python helper
   parse_verification_blocks() is added to plan-orchestrator.py. While the
   agent could parse markdown itself, having a utility function enables reliable
   testing and consistent parsing across agents.

## Files Affected

### Modified

- `.claude/agents/validator.md` - Add spec-aware validation section with
  instructions for reading verification blocks, running E2E tests, and capturing
  JSON results.
- `scripts/plan-orchestrator.py`:
  - Add DEFAULT_SPEC_DIR, DEFAULT_E2E_COMMAND constants
  - Read spec_dir, e2e_command from orchestrator config
  - Add parse_verification_blocks() helper function
  - Update build_validation_prompt() to include spec-aware context when configured

### New

- `.claude/agents/e2e-analyzer.md` - On-demand test results analyzer agent
- `docs/templates/verification-block.md` - Reference format for verification
  blocks in functional spec files

### Tests

- `tests/test_plan_orchestrator.py` - Add tests for parse_verification_blocks()
  and the updated build_validation_prompt()

## Edge Cases

- **No spec config**: Validator falls back to generic behavior (no E2E tests)
- **Spec files changed but no Testable blocks**: Validator notes this, skips E2E
- **E2E test command fails**: Validator captures the error, includes FAIL finding
- **No JSON output**: Validator reports WARN (test ran but output was missing)
- **Empty spec_dir**: Treated as unconfigured (skip E2E)
- **Multiple spec files changed**: All verification blocks from all changed files
  are aggregated and their tests are run
