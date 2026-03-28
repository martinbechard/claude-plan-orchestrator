# Design: Extract Shared Modules

## Date: 2026-02-25
## Source: docs/feature-backlog/02-extract-shared-modules.md

## Architecture Overview

Extract duplicated logic from auto-pipeline.py (125K) and plan-orchestrator.py (230K)
into importable modules under langgraph_pipeline/shared/. The shared/ directory already
exists with an empty __init__.py from the scaffold task.

The extraction eliminates the importlib.util hack in auto-pipeline.py (lines 44-52) that
loads the entire orchestrator module as a side effect just to import 4 symbols.

## Module Dependency Order

```
paths.py          (no deps - pure constants)
config.py         (depends on paths)
rate_limit.py     (standalone)
claude_cli.py     (standalone - OutputCollector, subprocess patterns)
git.py            (depends on paths, config)
budget.py         (depends on config, paths)
```

## Key Files

### New Files (langgraph_pipeline/shared/)
- paths.py - Centralized path constants (PLANS_DIR, PID_FILE_PATH, etc.)
- config.py - load_orchestrator_config() and defaults
- rate_limit.py - parse_rate_limit_reset_time(), check_rate_limit(), wait_for_rate_limit_reset()
- claude_cli.py - OutputCollector class, subprocess helpers
- git.py - stash, worktree, and commit helpers
- budget.py - Merged BudgetGuard/PipelineBudgetGuard, merged usage trackers

### New Test Files (tests/langgraph/shared/)
- test_paths.py
- test_config.py
- test_rate_limit.py
- test_claude_cli.py
- test_git.py
- test_budget.py

### Modified Files
- scripts/auto-pipeline.py - Replace importlib.util hack and inline definitions with shared imports
- scripts/plan-orchestrator.py - Replace inline definitions with shared imports

## Design Decisions

1. Module-per-concern: Each module is a single responsibility, matching the backlog spec.

2. Merge duplicates: BudgetGuard + PipelineBudgetGuard merge into one class.
   SessionUsageTracker + PlanUsageTracker merge with a scope parameter.

3. Extract-then-migrate: Create modules first with their own tests, then update the
   scripts to import from shared. This allows incremental verification.

4. Signature preservation: Functions keep their existing signatures to minimize script
   changes. The only API change is the budget class merges.

5. rate_limit API normalization: auto-pipeline.py returns Optional[float] from
   check_rate_limit while plan-orchestrator.py returns tuple[bool, Optional[datetime]].
   The shared version uses the richer tuple signature since both callers need the same
   information.

## Phasing

- Phase 1: Extract paths.py and config.py (foundational, no logic changes)
- Phase 2: Extract rate_limit.py and claude_cli.py (standalone logic)
- Phase 3: Extract git.py and budget.py (more complex, more dependencies)
- Phase 4: Migrate auto-pipeline.py imports (remove importlib hack)
- Phase 5: Migrate plan-orchestrator.py imports
