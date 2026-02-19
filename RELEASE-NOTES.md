# Release Notes

## 1.2.0 (2026-02-18)

### New Features
- **Ideas intake pipeline**: Drop rough notes in `docs/ideas/` and they are automatically
  classified and converted into properly formatted backlog items (features or defects)
  stored in the appropriate backlog directory.

## 1.1.0 (2026-02-18)

### New Features
- **Persistent logging system**: `auto-pipeline.py` now writes a per-item detail log
  (`logs/<slug>.log`) capturing full console output for each backlog item's lifecycle,
  and a summary log (`logs/pipeline.log`) with structured one-line events (STARTED,
  COMPLETED, FAILED, etc.). Logs append across restarts with timestamped session headers.
- **Configurable build/test commands**: `orchestrator-config.yaml` now accepts
  `build_command`, `test_command`, and `dev_server_command` so projects are not locked
  to `pnpm`.
- **Dependency tracking**: Auto-pipeline respects task `depends_on` ordering in YAML plans.
- **Stop semaphore check after each item**: Pipeline checks for `.claude/plans/.stop`
  after completing each item, not just at startup.
- **Project-level settings**: `orchestrator-config.yaml` added for per-project
  configuration of commands and pipeline behaviour.

### Fixes
- Removed hardcoded `pnpm` references from verification prompt template.
- Strip `CLAUDECODE` env var so orchestrator runs correctly when launched from within
  Claude Code.

## 1.0.0 (initial release)

Initial release of Claude Plan Orchestrator.
