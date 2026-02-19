# Release Notes

## 1.6.1 (2026-02-19)

### Fixes
- **Infinite loop on archived items**: `archive_item()` now removes the source
  file from the backlog when the destination already exists, preventing the
  scanner from re-discovering completed items every cycle.
- **Circuit breaker for completed items**: Main pipeline loop tracks
  `completed_items` alongside `failed_items` so successfully processed items
  are never re-processed within the same session, even if archive cleanup fails.
- **`force_pipeline_exit()` central exit function**: Unrecoverable errors
  (e.g. stale source removal failure) now call a single function that creates
  the stop semaphore, sends a Slack error notification, and exits the process.

## 1.6.0 (2026-02-19)

### New Features
- **Pipeline PID file**: `auto-pipeline.py` now writes its PID to
  `.claude/plans/.pipeline.pid` at startup and removes it on shutdown.
  This allows external tools (and AI assistants) to identify and stop the
  correct pipeline instance without accidentally killing pipelines running
  in other project directories.

## 1.5.0 (2026-02-18)

### Improvements
- **Cognitive specialization documented**: Narrative chapter 14 covers the model audit
  across all 11 agents, the cascade multiplier reasoning behind promoting planner and
  ux-designer to Opus, the Opus/Sonnet design loop pattern, the agent teams vs subagent
  trade-off analysis, and the Slack suspension problem.
- **Narrative README restructured**: "The Core Insight" section moved before the Document
  Index so new readers encounter the architectural rationale before the chapter list.
- **Plugin versioning policy**: `CLAUDE.md` establishes that `plugin.json` version must
  be bumped for every meaningful change and `RELEASE-NOTES.md` kept in sync, as if the
  plugin were published in the marketplace.
- **Completed backlog captured**: Completion records for all 29 shipped features and
  defects committed to `docs/completed-backlog/`, making the full delivery history
  browsable without digging through git log.

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
