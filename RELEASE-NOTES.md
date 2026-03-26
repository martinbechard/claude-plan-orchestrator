# Release Notes

## 1.10.5 (2026-03-26)

### Bug Fixes
- **Web server auto-enable when port is configured:** `cli.py` now enables the web
  server automatically when `web.port` is set in `orchestrator-config.yaml`, even if
  `web.enabled` is not explicitly set to `true`. Previously the check required an
  explicit `enabled: true` flag, causing cost data to never reach the web UI when
  users only configured the port.

## 1.10.4 (2026-03-26)

### Bug Fixes
- **Cost posting uses dedicated env var:** Introduced `ORCHESTRATOR_WEB_URL` as the
  canonical env var for the local web server URL. `_post_cost_to_api()` in task_runner
  and validator now reads this var instead of `LANGCHAIN_ENDPOINT`, so cost data is
  posted whenever the web server is running regardless of LangSmith tracing configuration.
  The CLI sets `ORCHESTRATOR_WEB_URL` after the web server starts so all worker
  subprocesses inherit it automatically.

## 1.10.3 (2026-03-26)

### Improvements
- **Test data discipline policies:** Added policies to coder, validator, and planner
  agents requiring cleanup of test data after implementation and use of random/UUID
  values for test fixtures. Prevents leftover placeholder data from being mistaken
  for real results by validators or users.

## 1.10.2 (2026-03-26)

### Improvements
- **Checklist-style validation criteria:** Planner agent now generates acceptance
  criteria as binary YES/NO questions (e.g. "Does X exist? YES = pass, NO = fail")
  rather than prose statements, eliminating ambiguous validator interpretations.
- **Literal answer requirement for validator:** Validator agent now must answer each
  criterion question literally (YES/NO) and record the answer before determining
  the final verdict, preventing false PASSes on unverified criteria.

## 1.10.1 (2026-03-25)

### Bug Fixes
- **Worker DB cleanup on quota exhaustion:** Pipeline worker subprocesses now remove
  their SQLite checkpoint DB when failing due to Claude quota exhaustion, preventing
  accumulation of orphaned `.claude/pipeline-worker-*.db` files.

## 1.10.0 (2026-03-25)

### New Features
- **Spec-aware validator:** `validator.md` now reads functional spec verification
  blocks and runs referenced Playwright E2E tests when spec files are changed.
  Results are captured as timestamped JSON files in `logs/e2e/` for trend analysis.
- **E2E analyzer agent:** New on-demand agent (`e2e-analyzer`) for reviewing
  accumulated E2E test logs to identify flaky tests, detect regressions, and
  summarize pass/fail trends across runs.
- **Verification block template:** Reference format for annotating functional specs
  with structured, machine-readable verification blocks at
  `docs/templates/verification-block.md`.

## 1.9.3 (2026-03-25)

### Fixes
- **Ideas intake in parallel mode:** `run_supervisor_loop()` now calls
  `process_ideas(dry_run)` at the top of each iteration, matching the placement
  in the sequential scan loop. Ideas dropped in `docs/ideas/` are processed
  regardless of whether the pipeline runs with `max_parallel_items == 1` or
  `max_parallel_items > 1`.

## 1.9.2 (2026-03-25)

### Fixes
- **Prevent duplicate worker spawning:** `claim_item()` now detects when the source
  path equals the claimed path and skips the redundant move, preventing the supervisor
  from spawning two workers for the same item.
- **Filter in-progress items from backlog scan:** `scan_backlog()` now excludes paths
  under `CLAIMED_DIR` so items already being processed are not re-claimed in a
  subsequent scan cycle.
- **Restore orphans to correct backlog directory:** A item-type sidecar file is written
  at claim time so the orphan unclaim logic knows which backlog directory to restore
  the item to, rather than defaulting to the wrong location.

## 1.9.1 (2026-03-25)

### Fixes
- **Max validation attempts returns WARN:** When validation is abandoned after
  exhausting all retry attempts, the verdict is now WARN instead of PASS,
  accurately reflecting inconclusive validation in the plan record.

## 1.9.0 (2026-03-24)

### New Features
- **Ideas intake pipeline:** Drop rough notes in docs/ideas/ and they are
  automatically classified (feature, defect, or invalid) and converted into
  properly formatted backlog items by a Claude session. Includes an
  idea_classifier module with keyword and heuristic-based classification,
  comprehensive unit tests, and seamless integration with the existing
  auto-pipeline backlog directories.

## 1.8.2 (2026-03-24)

### Improvements
- **Spec-aware validator (complete):** Validator now reads SPEC_DIR from
  orchestrator-config.yaml, runs E2E tests referenced in Verification blocks
  of changed functional spec files, and saves timestamped JSON results to
  logs/e2e/. Validation prompts are enriched with spec context extracted from
  functional specifications matching changed files.

## 1.8.1 (2026-02-25)

### Improvements
- **Disk-persisted backlog creation throttle:** `create_backlog_item()` now checks a
  disk-persisted throttle file before writing any backlog file. Limits: 20 defects/hour
  and 20 features/hour. Survives process restarts (unlike the in-memory A4 rate limiter,
  which is kept as a fast pre-filter). The throttle is the authoritative safety net at
  the single chokepoint where every backlog file is created.
- **LangGraph v2 safety requirements:** Features 03, 04, and 05 now include Safety
  Requirements sections documenting the loop prevention layers, intake throttling, and
  RAG deduplication that must be ported from v1.8.0.

## 1.8.0 (2026-02-25)

### Fixes
- **Slack notification feedback loop prevention**: Four redundant layers prevent
  the bot from re-processing its own notification messages, which previously caused
  17,000+ recursive defect filings:
  - **Chain detection (A1):** On-disk history of recently created backlog items;
    messages referencing known item numbers or slugs are skipped. Survives restarts.
  - **Tighter self-reply window (A2):** Reduced from 3 per 60s to 1 per 300s per
    channel, blocking cascading self-replies.
  - **Content-based notification filter (A3):** Regex matching bot notification
    formats (emoji + "Defect received" etc.) skips them before LLM routing.
  - **Global intake rate limiter (A4):** Hard cap of 10 intakes per 5 minutes.
  - **LLM routing hint (A5):** MESSAGE_ROUTING_PROMPT tells the LLM to classify
    notification-format messages as "none".
- **Bogus backlog cleanup:** Deleted 132 recursive loop artifact files from
  docs/defect-backlog/ (items 17561-17687).
- **Defect #01 resolved:** Self-skip filter replaced with loop detection per the
  defect's own recommendation (no bot_id filtering).

### New Features
- **ChromaDB RAG for intake deduplication (Phase B):** Incoming defect/feature
  requests are checked against a semantic vector index of existing backlog items.
  Duplicates are consolidated into the existing item with an "Additional Report"
  section appended. Uses ChromaDB embedded (no server), stores in .claude/chroma/.
- **BacklogRAG class:** index_backlog(), index_specs(), query_similar(), add_item(),
  update_item() methods for semantic search over the backlog.

## 1.7.0 (2026-02-19)

### New Features
- **Agent Identity Protocol**: When multiple projects share Slack channels, each
  agent now signs outbound messages with its display name (e.g., `CPO-Orchestrator`)
  and filters inbound messages by address. Self-loop prevention, directed `@Agent`
  addressing, and broadcast routing are all handled automatically.
- **Configurable identity**: Add an `identity` section to `orchestrator-config.yaml`
  to set project name and per-role display names. Defaults are derived from the
  current directory name when not configured.
- **Role switching**: Intake analysis and QA answering run under their own agent
  roles (`CPO-Intake`, `CPO-QA`), so messages are signed with the correct identity
  for the operation being performed.

### Fixes
- **Bot messages no longer blanket-filtered**: The poll filter previously rejected
  all messages with a `bot_id`, which silently dropped messages from other
  projects' orchestrator bots. Now only system/subtype messages are filtered;
  self-loop prevention is handled by the agent identity signature check.

## 1.6.3 (2026-02-19)

### New Features
- **Cross-instance Slack collaboration**: Multiple orchestrator instances can
  listen to each other's Slack channels to discover new versions, submit defects
  and features, and ask questions across projects.

### Improvements
- **README updated**: Graceful stop docs reflect mid-task semaphore checking,
  PID-based termination documented, cross-instance collaboration section added.
- **Race condition documented**: Comment in plan-orchestrator.py explains the
  stop semaphore startup-clear timing and why SIGTERM via PID file is the most
  reliable stop method.

## 1.6.2 (2026-02-19)

### Improvements
- **Mid-task stop semaphore check**: The orchestrator now checks for the stop
  semaphore every second during Claude subprocess execution, not just between
  tasks. A stop request mid-task terminates the subprocess within 1 second
  instead of waiting for the full task to complete (which could take 30+ minutes).

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
