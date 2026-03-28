# Design: Remove SPEC_DIR Dead Code

## Overview

Remove the unused DEFAULT_SPEC_DIR constant and SPEC_DIR config-loading line from
plan-orchestrator.py, along with any test code that references them. These are remnants
of an unfinished spec-directory feature with zero runtime consumers.

## Affected Files

1. **scripts/plan-orchestrator.py**
   - Line 54: Delete DEFAULT_SPEC_DIR = ""
   - Line 293: Delete SPEC_DIR = _config.get("spec_dir", DEFAULT_SPEC_DIR)

2. **tests/test_plan_orchestrator.py**
   - Line 1089: Remove monkeypatch.setattr(mod, "SPEC_DIR", "docs/specs/") from
     test_build_validation_prompt_still_has_standard_checks (the test remains valid
     without this line since SPEC_DIR was never consumed by build_validation_prompt)

## Design Decisions

- **No deprecation needed**: Per project philosophy, dead code is deleted outright
  rather than deprecated. There are no external consumers.
- **Test preservation**: The test_build_validation_prompt_still_has_standard_checks
  test itself is still valuable (it verifies BUILD_COMMAND and TEST_COMMAND appear
  in the validation prompt). Only the dead monkeypatch line is removed.
- **Single task**: All three deletions are trivial and tightly coupled, so they belong
  in a single implementation task.
