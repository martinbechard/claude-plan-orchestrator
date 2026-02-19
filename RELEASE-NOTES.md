# Release Notes

## 1.4.0 (2026-02-18)

### New Features
- **Opus/Sonnet design loop**: UX designer agent now runs as Opus orchestrator invoking
  a Sonnet subagent for design generation. Handles Q&A rounds automatically, capped at
  3 rounds.
- **ux-implementer agent**: New Sonnet-based agent that produces design documents from
  design briefs using a structured STATUS protocol (STATUS: COMPLETE or STATUS: QUESTION).
- **Slack-based question suspension**: Work items can be suspended when a design question
  requires human input. Questions are posted to Slack; the pipeline continues processing
  other work items; answers resume the suspended item automatically.
- **Suspension marker files**: New `.claude/suspended/` directory for tracking suspended
  items with timeout and Slack thread correlation.

## 1.3.0 (2026-02-18)

### New Features
- **Spec-aware validator**: Validator agent reads functional spec verification blocks and
  runs referenced E2E tests when spec files are changed. Results are captured as
  timestamped JSON files in `logs/e2e/` for later analysis.
- **E2E analyzer agent**: New on-demand agent (`e2e-analyzer`) for reviewing accumulated
  E2E test logs to identify flaky tests, detect regressions, and summarize pass/fail trends
  across runs.
- **Verification block template**: Reference format for annotating functional specs with
  structured, machine-readable verification blocks that link specs to their test suites.

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
