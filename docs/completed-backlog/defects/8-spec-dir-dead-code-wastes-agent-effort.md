# SPEC_DIR dead code wastes agent effort

## Status: Archived (verification failed)

## Priority: Low

## Summary

DEFAULT_SPEC_DIR and SPEC_DIR configuration loading exist in plan-orchestrator.py
but are never referenced by any functional code path. A pipeline agent discovered
this dead code and wasted a turn rewriting tests around it instead of doing
productive work.

## Observed Behavior

During the feature-19 pipeline run, the orchestrator's Claude session found
DEFAULT_SPEC_DIR (line 54) and SPEC_DIR config loading (line 293) during test
cleanup. The agent spent a full turn investigating and rewriting test assertions
for code that has no runtime effect.

## Root Cause

DEFAULT_SPEC_DIR = "" at line 54 and SPEC_DIR = _config.get("spec_dir",
DEFAULT_SPEC_DIR) at line 293 are remnants of a spec directory feature that was
never completed. SPEC_DIR is not used in build_validation_prompt(), not passed to
any agent definition, and has no consumers anywhere in the codebase.

## Affected Code Paths

1. scripts/plan-orchestrator.py line 54: DEFAULT_SPEC_DIR = ""
2. scripts/plan-orchestrator.py line 293: SPEC_DIR config loading
3. Tests that monkeypatch SPEC_DIR to no effect

## Recommended Fix

1. Delete DEFAULT_SPEC_DIR declaration at line 54
2. Delete SPEC_DIR config loading at line 293
3. Remove any test assertions or monkeypatches that reference SPEC_DIR

## Source

Discovered during feature-19 pipeline run analysis (2026-02-19). The pipeline
agent wasted effort cleaning up test references to this dead code.
