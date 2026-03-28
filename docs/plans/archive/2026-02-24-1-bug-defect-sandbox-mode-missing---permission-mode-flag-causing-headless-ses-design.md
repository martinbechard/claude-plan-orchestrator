# Design: Sandbox mode missing --permission-mode flag fix

## Problem

When sandbox mode is enabled, `build_permission_flags()` in both
`plan-orchestrator.py` and `auto-pipeline.py` passes `--allowedTools` but omits
`--permission-mode acceptEdits`. The Claude CLI defaults `--permission-mode` to
`"default"` (prompt-for-approval), which deadlocks when the process runs with
`stdin=subprocess.DEVNULL`.

The non-sandbox fallback (`--dangerously-skip-permissions`) implicitly suppresses
all interactive prompts, masking the two-axis permission model:

1. **Tool availability** (`--allowedTools`) -- which tools can be used
2. **Approval behavior** (`--permission-mode`) -- whether tool use requires
   interactive confirmation

## Fix

Add `--permission-mode acceptEdits` to the flags returned by
`build_permission_flags()` in both files when sandbox is enabled.

### Files to Modify

- `scripts/plan-orchestrator.py` -- `build_permission_flags()` at line 725
- `scripts/auto-pipeline.py` -- `build_permission_flags()` at line 427
- `tests/test_plan_orchestrator.py` -- update existing permission flag tests
- `tests/test_auto_pipeline.py` -- update existing permission flag tests

### Change Detail

In both `build_permission_flags()` functions, after building the `--allowedTools`
list and `--add-dir` scope, append `["--permission-mode", "acceptEdits"]` to
the flags list.

### Design Decisions

1. **acceptEdits is the correct permission mode** -- it allows Write/Edit without
   prompting while still requiring approval for other sensitive operations. This
   matches the sandbox intent of controlled tool access.
2. **Single-task fix** -- both files and their tests are tightly coupled in this
   change. Fixing them together avoids a window where one file works and the
   other does not.
3. **No startup assertion** -- the defect report suggests adding a headless
   compatibility check, but this adds complexity for a single flag. The test
   suite coverage is sufficient to catch regressions.
