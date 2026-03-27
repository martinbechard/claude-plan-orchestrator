# Design Document Audit Report

**Generated:** 2026-03-27
**Auditor:** code-reviewer agent
**Scope:** All design docs in docs/plans/ (218 total, split across 4 batches)

## Methodology

Each document was classified based on:

1. **References to deleted scripts** — `scripts/plan-orchestrator.py` was deleted; any doc referencing specific functions or line numbers in it is misleading to agents
2. **Outdated conventions** — tilde cost prefix (`~$`) was explicitly removed; docs recommending it would mislead agents
3. **Backlog item completion** — docs for completed items with no ongoing architectural value can be archived
4. **Reference validity** — docs referencing non-existent file paths, functions, or modules

### Classification Legend

| Class | Meaning |
|-------|---------|
| KEEP | Still accurate and useful as architecture reference |
| UPDATE | Useful but contains outdated references that need correction |
| ARCHIVE | Completed work, no longer useful as guidance; safe to move to archive |
| DELETE | Contains misleading outdated directives that could confuse agents |

### Key Facts Verified

- `scripts/plan-orchestrator.py` — **DELETED** (does not exist)
- `scripts/auto-pipeline.py` — **EXISTS**
- `docs/completed-backlog/` — EXISTS with defects/, features/, analyses/ subdirs
- `docs/analysis-backlog/` — EXISTS (read-only analysis workflow implemented)
- `docs/ideas/` — EXISTS (ideas intake implemented)
- Tilde cost prefix (`~$`) — **REMOVED** per MEMORY.md; correct format is `$0.0123`

---

## Batch 1: 2026-02-13 through 2026-02-18 (44 docs)

| # | File | Class | Issues |
|---|------|-------|--------|
| 1 | 2026-02-13-01-hardcoded-pnpm-in-verification-prompt-design.md | ARCHIVE | Completed defect; references deleted plan-orchestrator.py |
| 2 | 2026-02-13-02-agent-definition-framework-design.md | ARCHIVE | Completed feature; references deleted plan-orchestrator.py; agent files are current source of truth |
| 3 | 2026-02-13-06-token-usage-tracking-design.md | ARCHIVE | Completed feature; references deleted plan-orchestrator.py |
| 4 | 2026-02-13-07-quota-aware-execution-design.md | ARCHIVE | Completed feature; references deleted plan-orchestrator.py |
| 5 | 2026-02-13-03-per-task-validation-pipeline-design.md | ARCHIVE | Completed feature; references deleted plan-orchestrator.py |
| 6 | 2026-02-13-04-design-agents-design.md | ARCHIVE | Completed feature; references deleted plan-orchestrator.py; agent files are current source of truth |
| 7 | 2026-02-13-08-fix-in-progress-confusion-design.md | DELETE | Completed fix; references only deleted plan-orchestrator.py with specific line numbers; purely misleading |
| 8 | 2026-02-13-05-plugin-packaging-design.md | KEEP | Completed feature; no references to deleted scripts; describes current plugin architecture (plugin.json, marketplace.json) |
| 9 | 2026-02-14-04-design-agents-design.md | ARCHIVE | Updated version of doc 6; same rationale |
| 10 | 2026-02-14-06-token-usage-tracking-design.md | ARCHIVE | Updated version of doc 3; same rationale |
| 11 | 2026-02-14-07-quota-aware-execution-design.md | ARCHIVE | Updated version of doc 4; same rationale |
| 12 | 2026-02-14-09-move-completed-outside-backlog-design.md | ARCHIVE | Completed feature (docs/completed-backlog/ exists); references only auto-pipeline.py |
| 13 | 2026-02-16-10-tiered-model-escalation-design.md | DELETE | References only deleted plan-orchestrator.py with specific function/line details; no corresponding completed backlog item found; misleading implementation context |
| 14 | 2026-02-16-11-qa-audit-pipeline-design.md | UPDATE | qa-auditor agent still active in system; references deleted plan-orchestrator.py for keyword inference — remove dead refs, keep agent design intent |
| 15 | 2026-02-16-12-spec-verifier-ux-reviewer-agents-design.md | UPDATE | spec-verifier and ux-reviewer agents still active; references deleted plan-orchestrator.py for keyword inference — remove dead refs |
| 16 | 2026-02-16-13-slack-agent-communication-design.md | UPDATE | Slack integration still active; references deleted plan-orchestrator.py extensively — remove dead refs, update for langgraph pipeline |
| 17 | 2026-02-16-14-slack-app-migration-design.md | UPDATE | Slack migration may still be pending; references deleted plan-orchestrator.py — remove dead refs, verify current Socket Mode state |
| 18 | 2026-02-16-15-slack-inbound-message-polling-design.md | UPDATE | Slack polling active per MEMORY.md; references deleted plan-orchestrator.py — remove dead refs, update for langgraph architecture |
| 19 | 2026-02-16-02-unnecessary-completed-slugs-scan-design.md | ARCHIVE | Completed defect; references only auto-pipeline.py |
| 20 | 2026-02-16-1-i-want-to-be-able-to-use-separate-slack-channels-depending-on-the-project-by-de-design.md | ARCHIVE | Implemented (channels work per MEMORY.md); references deleted plan-orchestrator.py |
| 21 | 2026-02-17-2-i-want-to-be-able-to-use-separate-slack-channels-depending-on-the-project-by-de-design.md | DELETE | Verification status doc for completed feature; references deleted plan-orchestrator.py; no standalone value |
| 22 | 2026-02-17-03-noisy-log-output-from-long-plan-filenames-design.md | ARCHIVE | Completed defect; references deleted plan-orchestrator.py and auto-pipeline.py |
| 23 | 2026-02-17-5-slack-bot-provides-truncated-unhelpful-responses-when-defect-submission-fails-validation-design.md | DELETE | Stale status doc with references to failing tests in deleted plan-orchestrator.py context; misleading to agents |
| 24 | 2026-02-17-6-new-defect-when-a-defect-or-feature-is-received-the-agent-is-supposed-to-do-a-design.md | DELETE | References deleted plan-orchestrator.py with specific line numbers (3695, 3758, etc.); implementation context no longer valid |
| 25 | 2026-02-17-5-new-enhancement-when-accepting-the-feature-via-slack-you-need-to-acknowledge-w-design.md | DELETE | References deleted plan-orchestrator.py (_run_intake_analysis, send_status at specific lines); implementation context gone |
| 26 | 2026-02-17-6-new-feature-when-modifying-the-code-for-the-auto-pipeline-you-need-to-have-som-design.md | ARCHIVE | Completed feature (hot-reload implemented); mentions plan-orchestrator.py only as child process being monitored |
| 27 | 2026-02-17-7-weve-done-a-lot-of-changes-to-the-code---make-sure-to-update-the-documentation-design.md | ARCHIVE | Documentation sync task; historical only; line counts and feature lists from Feb 2026 are now stale |
| 28 | 2026-02-17-6-there-seems-to-be-a-problem-with-a-defect-not-being-archived-please-investigate-design.md | ARCHIVE | Completed fix; references only auto-pipeline.py |
| 29 | 2026-02-17-1-auto-restart-pipeline-process-when-pipeline-code-is-modified-design.md | ARCHIVE | Superseded by hot-reload implementation; references deleted plan-orchestrator.py as child process |
| 30 | 2026-02-17-7-pipeline-agent-commits-unrelated-working-tree-changes-design.md | DELETE | References deleted plan-orchestrator.py for git_stash_working_changes() and git_stash_pop() implementation; misleading |
| 31 | 2026-02-17-8-use-sonnet-4-6-for-ui-design-and-judging-design.md | ARCHIVE | Frontend-coder agent exists; feature implemented; references deleted plan-orchestrator.py |
| 32 | 2026-02-18-1-add-configurable-conversation-history-for-follow-on-question-support-design.md | DELETE | References deleted plan-orchestrator.py (QA_HISTORY_DEFAULT_MAX_TURNS, answer_question()); implementation context gone |
| 33 | 2026-02-18-1-archiving-fails-when-backlog-items-are-moved-to-completed-subfolder-mid-pipeline-design.md | ARCHIVE | Completed defect; references only auto-pipeline.py |
| 34 | 2026-02-18-2-prevent-premature-completed-subfolder-moves-and-ensure-archive-runs-exactly-once-design.md | ARCHIVE | Likely completed alongside archival fixes; references only auto-pipeline.py |
| 35 | 2026-02-18-3-fix-git-stash-pop-failure-when-task-statusjson-has-uncommitted-changes-design.md | DELETE | References deleted plan-orchestrator.py for git_stash_pop() modification; implementation impossible to apply |
| 36 | 2026-02-18-1-persistent-logging-system-with-per-item-detail-files-and-summary-progress-log-design.md | ARCHIVE | Logging implemented (logs/ directory exists); references auto-pipeline.py primarily; plan-orchestrator.py only mentioned as "no changes required" |
| 37 | 2026-02-18-1-announce-completed-items-in-their-type-specific-slack-channels-featuresdefects-design.md | ARCHIVE | Implemented (defects/features channels active per MEMORY.md); references deleted plan-orchestrator.py |
| 38 | 2026-02-18-1-new-defect-reported-in-another-project-design.md | ARCHIVE | Completed defect; references only auto-pipeline.py |
| 39 | 2026-02-18-auto-create-dependent-directories-design.md | ARCHIVE | Directories exist in codebase; references deleted plan-orchestrator.py |
| 40 | 2026-02-18-ideas-intake-pipeline-design.md | ARCHIVE | Implemented (docs/ideas/ exists); references only auto-pipeline.py |
| 41 | 2026-02-18-spec-aware-validator-with-e2e-logging-design.md | UPDATE | Spec-aware validation concept still relevant for langgraph pipeline; references deleted plan-orchestrator.py — remove dead refs, port concepts to langgraph |
| 42 | 2026-02-18-9-ux-designer-opus-sonnet-loop-with-slack-suspension-design.md | UPDATE | Complex suspension/Q&A feature; Slack integration is active; references deleted plan-orchestrator.py — remove dead refs, verify current suspension state in langgraph |
| 43 | 2026-02-18-16-least-privilege-agent-sandboxing-design.md | UPDATE | Important security architecture concept; references deleted plan-orchestrator.py — remove dead refs, determine if implemented in langgraph |
| 44 | 2026-02-18-17-read-only-analysis-task-workflow-design.md | ARCHIVE | Implemented (docs/analysis-backlog/ exists); references deleted plan-orchestrator.py |

### Batch 1 Summary

| Classification | Count |
|---------------|-------|
| KEEP | 1 |
| UPDATE | 8 |
| ARCHIVE | 26 |
| DELETE | 9 |
| **Total** | **44** |

### Batch 1 UPDATE Details

Documents classified as UPDATE require the following corrections:

| Doc | Required Updates |
|-----|-----------------|
| 2026-02-16-11-qa-audit-pipeline | Remove plan-orchestrator.py keyword inference refs; update agent dispatch for langgraph |
| 2026-02-16-12-spec-verifier-ux-reviewer-agents | Remove plan-orchestrator.py keyword inference refs; update agent dispatch for langgraph |
| 2026-02-16-13-slack-agent-communication | Remove plan-orchestrator.py SlackNotifier refs; update for langgraph slack/ module |
| 2026-02-16-14-slack-app-migration | Remove plan-orchestrator.py refs; verify Socket Mode state in langgraph slack/ module |
| 2026-02-16-15-slack-inbound-message-polling | Remove plan-orchestrator.py refs; update poll_messages design for langgraph |
| 2026-02-18-spec-aware-validator-with-e2e-logging | Remove plan-orchestrator.py refs; port DEFAULT_SPEC_DIR, DEFAULT_E2E_COMMAND concepts to langgraph |
| 2026-02-18-9-ux-designer-opus-sonnet-loop | Remove plan-orchestrator.py refs; verify suspension state in langgraph pipeline |
| 2026-02-18-16-least-privilege-agent-sandboxing | Remove plan-orchestrator.py refs; verify AGENT_PERMISSION_PROFILES in langgraph |

---

*Batches 3 and 4 will be appended by subsequent audit tasks.*

---

## Batch 2: 2026-02-19 through 2026-02-26 (29 docs)

### Additional Facts Verified for Batch 2

- `langgraph_pipeline/` — EXISTS with pipeline/, executor/, slack/, shared/ subpackages
- `langgraph_pipeline/slack/` — EXISTS with identity.py, notifier.py, poller.py, suspension.py
- `langgraph_pipeline/executor/` — EXISTS with state.py, edges.py, escalation.py, circuit_breaker.py, nodes/
- `langgraph_pipeline/shared/` — EXISTS with paths.py, config.py, rate_limit.py, claude_cli.py, git.py, budget.py, langsmith.py
- `scripts/run-pipeline.py` — EXISTS (thin wrapper calling langgraph_pipeline.cli.main())
- `langgraph_pipeline/cli.py` — EXISTS (full pipeline CLI logic)
- `langgraph_pipeline/__main__.py` — EXISTS
- `INTAKE_CLARITY_THRESHOLD` in slack/suspension.py — EXISTS (intake quality gate implemented)
- `MINIMUM_INTAKE_MESSAGE_LENGTH` in slack/poller.py — EXISTS
- Deadlock detection in executor/nodes/task_selector.py — EXISTS
- `execute_plan.py` uses executor subgraph (not subprocess bridge to plan-orchestrator.py)
- `ProgressReporter` / `CompletionTracker` — NOT in auto-pipeline.py (feature never implemented)
- `step_notifications` / `STEP_NOTIFICATION_THRESHOLD` — NOT in auto-pipeline.py (feature never implemented)
- `sweep_uncommitted_archival_artifacts` — NOT in codebase (feature never implemented)
- `_extract_completion_summary` — NOT in auto-pipeline.py (feature never implemented)
- `infer_agent_for_task` / `REVIEWER_KEYWORDS` — NOT in langgraph_pipeline/ (plan-orchestrator.py deleted)

| # | File | Class | Issues |
|---|------|-------|--------|
| 1 | 2026-02-19-18-periodic-progress-reporter-design.md | ARCHIVE | Feature designed for auto-pipeline.py; ProgressReporter never implemented; superseded by langgraph migration |
| 2 | 2026-02-19-17-read-only-analysis-task-workflow-design.md | ARCHIVE | Completed feature (analysis-backlog exists); references deleted plan-orchestrator.py for Slack channel config |
| 3 | 2026-02-19-19-optional-step-by-step-notifications-design.md | ARCHIVE | References plan-orchestrator.py with line numbers (5311-5317, 5156-5161); step_notifications not in auto-pipeline.py; superseded by langgraph |
| 4 | 2026-02-19-8-spec-dir-dead-code-wastes-agent-effort-design.md | ARCHIVE | Cleanup task for plan-orchestrator.py (deleted lines 54, 293); moot as whole file is gone |
| 5 | 2026-02-19-9-auto-stash-creates-merge-conflicts-on-plan-yamls-design.md | ARCHIVE | Fix for git_stash_working_changes/git_stash_pop in deleted plan-orchestrator.py (lines 1790, 1831); langgraph uses different approach |
| 6 | 2026-02-19-1-cpo-pipeline-feature-request-improve-verbose-mode-logging-for-inbound-slack-me-design.md | ARCHIVE | Verbose logging for deleted plan-orchestrator.py (lines 4826-4843); ported to langgraph/slack/ |
| 7 | 2026-02-20-1-theres-something-odd---i-see-the-cheapoville-pipeline-agent-complaining-that-th-design.md | ARCHIVE | Fix for infer_agent_for_task() in deleted plan-orchestrator.py; agent selection now uses explicit YAML agent: field |
| 8 | 2026-02-21-1-include-root-cause-and-fix-summary-in-defect-completion-slack-notifications-design.md | ARCHIVE | Feature designed for auto-pipeline.py; _extract_completion_summary not implemented; superseded by langgraph |
| 9 | 2026-02-21-1-bulb-feature-request-improve-readme-docs-on-cross-project-slack-defect-repor-design.md | ARCHIVE | Documentation-only task (README.md, docs/setup-guide.md); likely completed; no code refs |
| 10 | 2026-02-21-1-bug-defect-infinite-loop-when-failed-task-blocks-dependents-deadlock-not-de-design.md | ARCHIVE | Deadlock detection implemented in langgraph executor/nodes/task_selector.py; plan-orchestrator.py refs dead |
| 11 | 2026-02-21-2-document-single-command-onboarding-path-for-adding-orchestrator-to-existing-slack-workspaces-design.md | ARCHIVE | Documentation-only task (README.md, docs/setup-guide.md, scripts/setup-slack.py); likely completed |
| 12 | 2026-02-24-1-bug-defect-sandbox-mode-missing---permission-mode-flag-causing-headless-ses-design.md | ARCHIVE | Fix for build_permission_flags() in deleted plan-orchestrator.py (line 725); langgraph uses different permission model |
| 13 | 2026-02-24-1-update-narrative-and-readme-to-document-post-v170-improvements-feb-20-24-design.md | ARCHIVE | Documentation narrative task; references stale line counts for now-deleted plan-orchestrator.py (~5809 lines) |
| 14 | 2026-02-24-1-pipeline-lacks-startup-sweep-for-uncommitted-archival-artifacts-design.md | ARCHIVE | Feature designed for auto-pipeline.py; sweep_uncommitted_archival_artifacts never implemented; superseded by langgraph |
| 15 | 2026-02-24-1-there-is-a-self-skip-check-that-is-based-on-the-name-of-the-channel-this-is-not-design.md | ARCHIVE | bot_id self-skip approach (iteration #2) implemented in deleted plan-orchestrator.py; superseded by dedup+loop detection then langgraph/slack/ |
| 16 | 2026-02-24-01-self-skip-filter-drops-legitimate-messages-design.md | ARCHIVE | Dedup+loop detection (iteration #3) implemented in deleted plan-orchestrator.py; now in langgraph/slack/poller.py |
| 17 | 2026-02-25-01-langgraph-project-scaffold-design.md | KEEP | Accurately describes current langgraph_pipeline/ package structure (pipeline/, executor/, slack/, shared/); no stale refs |
| 18 | 2026-02-25-02-extract-shared-modules-design.md | ARCHIVE | Shared modules exist in langgraph_pipeline/shared/; migration from plan-orchestrator.py is complete (script deleted) |
| 19 | 2026-02-25-1-there-is-a-self-skip-check-that-was-based-on-the-name-of-the-channel--the-idea-design.md | ARCHIVE | Dead code cleanup for plan-orchestrator.py (AGENT_SIGNATURE_PATTERN, is_own_signature); script is deleted entirely |
| 20 | 2026-02-25-2-insufficient-context--try-again-is-not-an-actionable-defect-request-design.md | ARCHIVE | Feature implemented in langgraph/slack/ (INTAKE_CLARITY_THRESHOLD in suspension.py, MINIMUM_INTAKE_MESSAGE_LENGTH in poller.py); plan-orchestrator.py refs dead |
| 21 | 2026-02-26-3-there-is-a-self-skip-check-that-was-based-on-the-name-of-the-channel-the-idea-w-design.md | ARCHIVE | Final self-skip simplification for deleted plan-orchestrator.py; superseded by langgraph/slack/poller.py |
| 22 | 2026-02-26-03-extract-slack-modules-design.md | UPDATE | Module architecture (identity.py, notifier.py, poller.py, suspension.py) is accurate and current; migration steps referencing plan-orchestrator.py line numbers are dead — remove migration section |
| 23 | 2026-02-26-04-pipeline-graph-nodes-design.md | UPDATE | Graph topology accurate but execute_plan.py now uses executor subgraph (not subprocess bridge to plan-orchestrator.py as doc states) — update execute_plan description |
| 24 | 2026-02-26-1-cpo-pipeline-feature-request-improve-verbose-mode-logging-for-inbound-slack-me-design.md | ARCHIVE | Second version of verbose logging design for deleted plan-orchestrator.py; superseded by langgraph/slack/ migration |
| 25 | 2026-02-26-05-task-execution-subgraph-design.md | KEEP | Accurately describes current langgraph_pipeline/executor/ subgraph (state.py, edges.py, escalation.py, circuit_breaker.py, nodes/); plan-orchestrator.py ref is historical context only |
| 26 | 2026-02-26-06-langsmith-observability-design.md | KEEP | Accurately describes current LangSmith integration in langgraph_pipeline/shared/langsmith.py; no stale refs |
| 27 | 2026-02-26-17-read-only-analysis-task-workflow-design.md | ARCHIVE | Third version of analysis workflow design; feature implemented; plan-orchestrator.py refs dead (SLACK_CHANNEL_ROLE_SUFFIXES) |
| 28 | 2026-02-26-20-unified-langgraph-runner-design.md | UPDATE | run-pipeline.py and cli.py architecture accurate; "Unchanged Files" section lists plan-orchestrator.py as unchanged but it is deleted — remove that ref |
| 29 | 2026-02-26-21-main-module-entry-point-design.md | KEEP | Accurately describes current langgraph_pipeline/__main__.py and cli.py entry point structure; no stale refs |

### Batch 2 Summary

| Classification | Count |
|---------------|-------|
| KEEP | 4 |
| UPDATE | 3 |
| ARCHIVE | 22 |
| DELETE | 0 |
| **Total** | **29** |

### Batch 2 UPDATE Details

Documents classified as UPDATE require the following corrections:

| Doc | Required Updates |
|-----|-----------------|
| 2026-02-26-03-extract-slack-modules | Remove migration steps referencing plan-orchestrator.py line numbers (lines 3623-5655, 1559, etc.); the module architecture section is current and accurate |
| 2026-02-26-04-pipeline-graph-nodes | Update execute_plan.py description from "Subprocess bridge to plan-orchestrator.py" to "Invokes executor subgraph in-process"; remove plan-orchestrator.py subprocess bridge references |
| 2026-02-26-20-unified-langgraph-runner | Remove plan-orchestrator.py from "Unchanged Files" section (script is deleted); update comment to reflect plan-orchestrator.py is fully replaced by langgraph pipeline |

---

## Batch 3: 2026-03-23 through 2026-03-25 (33 docs)

### Additional Facts Verified for Batch 3

- `scripts/plan-orchestrator.py` — **DELETED** (all March 2026 references to it are dead)
- `langgraph_pipeline/shared/quota.py` — EXISTS (quota exhaustion detection)
- `langgraph_pipeline/shared/hot_reload.py` — EXISTS (hot reload implemented)
- `langgraph_pipeline/shared/cost_log.py` — **DOES NOT EXIST** (cost log not yet ported to langgraph)
- `langgraph_pipeline/shared/progress.py` — **DOES NOT EXIST** (progress reporter not implemented)
- `langgraph_pipeline/worker.py` — EXISTS (parallel worker entry point)
- `langgraph_pipeline/supervisor.py` — EXISTS (supervisor module)
- `langgraph_pipeline/web/server.py` — EXISTS (embedded web server)
- `langgraph_pipeline/web/proxy.py` — EXISTS (LangSmith tracing proxy)
- `langgraph_pipeline/web/dashboard_state.py` — EXISTS (dashboard state)
- `langgraph_pipeline/web/routes/dashboard.py` — EXISTS (dashboard routes)
- `langgraph_pipeline/web/cost_log_reader.py` — EXISTS (cost log reader for UI)
- `langgraph_pipeline/web/routes/analysis.py` — EXISTS (analysis UI route)
- `langgraph_pipeline/pipeline/nodes/idea_classifier.py` — EXISTS (ideas intake)
- `langgraph_pipeline/slack/poller.py` — EXISTS with `_bot_user_id` (identity filter implemented)
- `scripts/setup-project.py` — EXISTS (project setup script)
- `emit_tool_call_traces`, `ToolCallRecord` — EXISTS in claude_cli.py and langsmith.py
- `create_root_run`, `finalize_root_run`, `langsmith_root_run_id` — EXISTS in langsmith.py and state files
- `after_intake`, `after_create_plan` — EXISTS in pipeline/edges.py (quota routing)
- `_post_pending_suspension_questions`, `_reinstate_answered_suspensions` — EXISTS in cli.py
- `find_free_port`, `write_port_to_config` — EXISTS in web/server.py and cli.py
- `CompletionTracker`, `ProgressReporter` — **DO NOT EXIST** in codebase
- `docs/completed-backlog/features/06-parallel-item-processing-supervisor-worker-model.md` — EXISTS (parallel processing completed)

| # | File | Class | Issues |
|---|------|-------|--------|
| 1 | 2026-03-23-01-intake-single-digit-prefix-design.md | DELETE | Instructs fixing `_create_backlog_item()` in deleted plan-orchestrator.py (line 4523); LangGraph path (poller.py) already correct; misleading directive to modify non-existent file |
| 2 | 2026-03-23-01-langsmith-tool-call-tracing-design.md | KEEP | Accurately describes current LangSmith tool call tracing architecture (ToolCallRecord, emit_tool_call_traces in claude_cli.py, langsmith.py, task_runner.py); no stale refs |
| 3 | 2026-03-24-01-detect-when-were-out-of-quota-in-claude-code-and-dont-process-any-further-ite-design.md | ARCHIVE | Initial quota exhaustion design; quota.py, state fields, cli.py probe loop all implemented |
| 4 | 2026-03-24-01-calculate-tool-call-duration-from-timestamps-instead-of-relying-on-reported-duration-design.md | ARCHIVE | Duration tracking via tool_use_id pairing implemented in ToolCallRecord (claude_cli.py); superseded by doc 03 which confirms completion |
| 5 | 2026-03-24-02-detect-claude-code-quota-exhaustion-and-pause-pipeline-processing-design.md | ARCHIVE | Remaining quota gaps resolved; after_intake and after_create_plan exist in pipeline/edges.py; circuit_check and task_selector guards implemented |
| 6 | 2026-03-24-01-in-the-mpact-project-i-submitted-a-feature-request-and-the-orchestrator-respons-design.md | ARCHIVE | Bot user ID self-skip filter implemented in langgraph_pipeline/slack/poller.py (_bot_user_id present); plan-orchestrator.py refs are moot (script deleted) |
| 7 | 2026-03-24-03-track-tool-call-durations-in-langsmith-traces-design.md | ARCHIVE | Explicitly states "Status: Implementation Already Complete"; all described fields (duration_s, tool_use_id, start_time) present in ToolCallRecord |
| 8 | 2026-03-24-06-parallel-item-processing-supervisor-worker-model-design.md | ARCHIVE | Parallel processing fully implemented; worker.py, supervisor.py exist; item in docs/completed-backlog/features/ |
| 9 | 2026-03-24-01-quota-exhaustion-not-detected-in-create-plan-causes-false-archival-design.md | ARCHIVE | Quota detection extended to intake_analyze and create_plan; after_intake and after_create_plan exist in pipeline/edges.py and graph.py |
| 10 | 2026-03-24-02-worktree-copy-back-restores-files-deleted-in-main-since-worktree-creation-design.md | ARCHIVE | Defect fix for langgraph_pipeline/shared/git.py (_file_exists_in_ref guard); git.py exists; fix implemented |
| 11 | 2026-03-24-07-hot-reload-on-code-change-detection-design.md | ARCHIVE | Hot reload implemented; langgraph_pipeline/shared/hot_reload.py exists with CodeChangeMonitor and _perform_restart |
| 12 | 2026-03-24-08-periodic-progress-report-while-work-is-queued-design.md | KEEP | Feature NOT yet implemented; langgraph_pipeline/shared/progress.py does not exist; CompletionTracker and ProgressReporter not in codebase; valid specification for future work; no stale refs |
| 13 | 2026-03-24-09-langsmith-per-item-root-trace-aggregation-design.md | ARCHIVE | Per-item root trace aggregation implemented; langsmith_root_run_id exists in pipeline/state.py and executor/state.py; create_root_run, finalize_root_run in langsmith.py; scan.py and archival.py wired |
| 14 | 2026-03-24-10-ux-designer-opus-sonnet-loop-with-slack-suspension-design.md | ARCHIVE | Both parts implemented; _post_pending_suspension_questions and _reinstate_answered_suspensions exist in cli.py; suspension infrastructure complete |
| 15 | 2026-03-24-03-backlog-slug-pattern-too-strict-silently-ignores-items-design.md | ARCHIVE | Defect fix for BACKLOG_SLUG_PATTERN in scan.py; fix implemented |
| 16 | 2026-03-24-11-spec-aware-validator-with-e2e-logging-design.md | UPDATE | Spec-aware validation concept valid for langgraph pipeline; "Already implemented" section points to plan-orchestrator.py (deleted) for SPEC_DIR/build_validation_prompt/parse_verification_blocks — remove dead refs; validator.md step and E2E log pattern remain accurate |
| 17 | 2026-03-24-12-structured-execution-cost-log-and-analysis-design.md | ARCHIVE | Original cost log design for plan-orchestrator.py (deleted); superseded by 2026-03-24-04 which describes porting to langgraph_pipeline/shared/cost_log.py |
| 18 | 2026-03-24-ideas-intake-pipeline-design.md | ARCHIVE | Ideas intake pipeline fully implemented; idea_classifier.py, paths constants (IDEAS_DIR, IDEAS_PROCESSED_DIR), cli.py scan-loop integration all exist |
| 19 | 2026-03-24--cost-analysis-design.md | UPDATE | Cost analysis task design valid; but instructs importing SlackNotifier from deleted plan-orchestrator.py — update to use langgraph_pipeline.slack.notifier instead |
| 20 | 2026-03-24-spec-aware-validator-with-e2e-logging-design.md | UPDATE | Completion design; "Already implemented" section references plan-orchestrator.py lines 15, 19, etc. (script deleted) — remove dead refs; validator.md spec-aware step and test fix logic remain accurate |
| 21 | 2026-03-24-04-planner-targets-legacy-script-instead-of-langgraph-pipeline-design.md | KEEP | cost_log.py NOT yet created in langgraph_pipeline/shared/; accurate diagnosis that Feature 12 was implemented in deleted plan-orchestrator.py and needs porting; no stale refs |
| 22 | 2026-03-24-05-max-validation-attempts-silently-passes-instead-of-warning-design.md | ARCHIVE | Fix applied; validator.py returns WARN at max attempts; patch version bump completed |
| 23 | 2026-03-25-13-embedded-web-server-infrastructure-design.md | ARCHIVE | Web server fully implemented; langgraph_pipeline/web/server.py, web/__init__.py, templates/base.html all exist |
| 24 | 2026-03-25-14-langsmith-tracing-proxy-design.md | ARCHIVE | Tracing proxy fully implemented; web/proxy.py, web/routes/proxy.py, templates/proxy_list.html all exist |
| 25 | 2026-03-25-05-max-validation-attempts-silently-passes-instead-of-warning-design.md | ARCHIVE | Duplicate of 2026-03-24-05; fix already applied; patch version bump completed |
| 26 | 2026-03-25-06-supervisor-spawns-duplicate-workers-for-same-item-design.md | ARCHIVE | Defect fix for supervisor.py and scan.py claim_item; same-path guard, scan filter, and sidecar fixes implemented |
| 27 | 2026-03-25-15-pipeline-activity-dashboard-design.md | ARCHIVE | Dashboard fully implemented; web/dashboard_state.py, web/routes/dashboard.py, templates/dashboard.html exist |
| 28 | 2026-03-25-16-tool-call-timing-and-cost-analysis-ui-design.md | UPDATE | UI correctly implemented (cost_log_reader.py, routes/analysis.py exist); schema section states "Files are written by write_execution_cost_log() in scripts/plan-orchestrator.py" — script is deleted; update to reference langgraph_pipeline/shared/cost_log.py (pending creation per doc #21) |
| 29 | 2026-03-25-ideas-intake-pipeline-design.md | ARCHIVE | Supervisor integration complete; supervisor.py calls process_ideas(); no gap remains |
| 30 | 2026-03-25-spec-aware-validator-with-e2e-logging-design.md | UPDATE | Spec-aware validator design valid for langgraph; "Already Implemented" section cites plan-orchestrator.py lines 62-63, 377-378, 412, 1765 (script deleted) and references CompletionTracker removed from auto_pipeline.py — remove all deleted-file refs; SPEC_DIR config needs to be ported to langgraph_pipeline/ |
| 31 | 2026-03-25-17-project-setup-script-design.md | ARCHIVE | Setup script implemented; scripts/setup-project.py exists |
| 32 | 2026-03-25-22-dynamic-web-server-port-allocation-design.md | ARCHIVE | Dynamic port allocation implemented; find_free_port in web/server.py and write_port_to_config in cli.py exist |
| 33 | 2026-03-25-00-trace-smoke-test-design.md | ARCHIVE | One-shot smoke test task to verify end-to-end tracing; no architectural value; no code changes required |

### Batch 3 Summary

| Classification | Count |
|---------------|-------|
| KEEP | 3 |
| UPDATE | 5 |
| ARCHIVE | 24 |
| DELETE | 1 |
| **Total** | **33** |

### Batch 3 UPDATE Details

Documents classified as UPDATE require the following corrections:

| Doc | Required Updates |
|-----|-----------------|
| 2026-03-24-11-spec-aware-validator-with-e2e-logging | Remove "Already implemented" refs to plan-orchestrator.py (SPEC_DIR, build_validation_prompt, parse_verification_blocks); update to describe porting to langgraph_pipeline/ config; keep validator.md E2E step description |
| 2026-03-24--cost-analysis-design | Replace `from scripts/plan-orchestrator.py import SlackNotifier` with `from langgraph_pipeline.slack.notifier import SlackNotifier` |
| 2026-03-24-spec-aware-validator-with-e2e-logging | Remove "Already Implemented" plan-orchestrator.py line references (62-63, 377-378, 412, 1765); update to describe langgraph_pipeline/ equivalent; keep validator.md spec-aware step and test fix logic |
| 2026-03-25-16-tool-call-timing-and-cost-analysis-ui | Update schema section: change "Files are written by write_execution_cost_log() in scripts/plan-orchestrator.py" to reference langgraph_pipeline/shared/cost_log.py (pending creation) |
| 2026-03-25-spec-aware-validator-with-e2e-logging | Remove plan-orchestrator.py line refs in "Already Implemented"; remove CompletionTracker/auto_pipeline.py test refs; port SPEC_DIR/E2E_COMMAND to langgraph_pipeline/ config approach |

---

## Batch 4a: 2026-03-26 (62 docs)

### Additional Facts Verified for Batch 4

- `scripts/plan-orchestrator.py` — **DELETED** (all references in -26/-27 docs are dead)
- `langgraph_pipeline/web/routes/queue.py` — EXISTS (queue page implemented)
- `langgraph_pipeline/web/routes/item.py` — EXISTS (work item detail page implemented)
- `langgraph_pipeline/web/routes/completions.py` — EXISTS (completions page implemented)
- `langgraph_pipeline/web/routes/sessions.py` — EXISTS (session tracking implemented)
- `langgraph_pipeline/web/routes/cost.py` — EXISTS (cost POST endpoint implemented)
- `langgraph_pipeline/web/routes/analysis.py` — EXISTS (cost analysis page implemented)
- `langgraph_pipeline/web/routes/proxy.py` — EXISTS (tracing proxy routes implemented)
- `langgraph_pipeline/web/dashboard_state.py` — EXISTS with `DashboardErrorHandler`
- `langgraph_pipeline/cli.py` — EXISTS with `DashboardErrorHandler` installed
- `ORCHESTRATOR_WEB_URL` — EXISTS in `shared/paths.py` and set in `cli.py`
- `verification_notes` — EXISTS in `pipeline/nodes/execute_plan.py` and `worker.py`
- `WorkerInfo.current_velocity()` / `get_velocity_series()` — EXISTS in `dashboard_state.py`
- `sessions` table / session lifecycle — EXISTS in `proxy.py` and `routes/sessions.py`
- `YYYY-MM-DD-feature-template.md` — EXISTS (one file, feature template placeholder)

| # | File | Class | Issues |
|---|------|-------|--------|
| 1 | 2026-03-26-01-audit-design-docs-for-validity-design.md | UPDATE | Meta-doc for this audit; references plan-orchestrator.py as subject of deletion — accurate context but could mislead agents into looking for the script |
| 2 | 2026-03-26-01-trace-smoke-test-design.md | ARCHIVE | One-off smoke test (write sentinel file); no ongoing architectural value |
| 3 | 2026-03-26-01-traces-model-filter-broken-design.md | ARCHIVE | "Implementation Status: Review Required" — fix complete in proxy.py; no ongoing architectural value |
| 4 | 2026-03-26-02-hello-world-test-design.md | ARCHIVE | Trivial smoke test (write "hello world"); no architectural value |
| 5 | 2026-03-26-02-traces-runs-named-langgraph-design.md | ARCHIVE | Implementation confirmed complete; fix for root run naming in langsmith.py already applied; still in .claimed/ |
| 6 | 2026-03-26-03-cost-analysis-db-backend-design.md | UPDATE | References deleted plan-orchestrator.py for `write_execution_cost_log()` — updated version exists as 2026-03-27-03 |
| 7 | 2026-03-26-03-dashboard-items-stuck-running-design.md | KEEP | Describes supervisor + DashboardState dead-PID cleanup architecture; ongoing reference for worker lifecycle |
| 8 | 2026-03-26-04-dashboard-scrolling-timeline-view-design.md | KEEP | Timeline view (Gantt/card toggle) architecture; renderTimeline() and localStorage design |
| 9 | 2026-03-26-04-timeline-duplicate-labels-and-elapsed-time-design.md | ARCHIVE | Bug fix for proxy_trace.html tick labels and elapsed time; implemented |
| 10 | 2026-03-26-05-queue-page-design.md | KEEP | Queue page architecture; describes FastAPI router + polling + backlog directory scanning |
| 11 | 2026-03-26-05-traces-trace-id-column-and-filter-design.md | ARCHIVE | Trace ID column and LIKE filter feature; implemented in proxy.py and routes/proxy.py |
| 12 | 2026-03-26-06-dashboard-drill-down-to-trace-design.md | KEEP | Run UUID threading from worker through SSE to dashboard links; ongoing architecture |
| 13 | 2026-03-26-06-work-item-detail-page-design.md | KEEP | Work item detail page data sources and priority chain; key UI component architecture |
| 14 | 2026-03-26-07-completions-paged-table-design.md | KEEP | Completions page architecture with pagination, filters, and summary stats |
| 15 | 2026-03-26-07-timeline-bar-colors-too-similar-design.md | ARCHIVE | UI color palette change; single-file CSS fix; implemented |
| 16 | 2026-03-26-08-timeline-sub-second-precision-lost-design.md | ARCHIVE | Bug fix for datetime.fromisoformat() precision; implemented in routes/proxy.py |
| 17 | 2026-03-26-08-tracing-proxy-narrative-and-guid-generation-design.md | KEEP | Narrative document on tracing proxy origin; investigative doc with ongoing architectural context |
| 18 | 2026-03-26-09-completions-finished-invalid-date-design.md | ARCHIVE | JS type-check bug fix for dashboard.js fmtFinished(); implemented |
| 19 | 2026-03-26-09-verification-notes-in-work-item-page-design.md | KEEP | Verification notes threading from validator through pipeline to item page; key data flow |
| 20 | 2026-03-26-10-error-stream-always-empty-design.md | KEEP | DashboardErrorHandler architecture; logging handler for dashboard error stream |
| 21 | 2026-03-26-10-trace-cost-analysis-page-design.md | KEEP | Cost analysis page architecture; SQL json_extract() queries from traces table |
| 22 | 2026-03-26-11-nav-active-item-styling-design.md | ARCHIVE | CSS pill styling for nav active item; single-rule change; implemented |
| 23 | 2026-03-26-11-tool-call-cost-attribution-design.md | KEEP | Tool call cost attribution architecture; post-hoc proportional estimation design |
| 24 | 2026-03-26-12-inclusive-cost-precomputation-design.md | KEEP | Two-pass inclusive cost query optimization; important performance architecture decision |
| 25 | 2026-03-26-13-timeline-all-items-show-as-other-design.md | ARCHIVE | Bug fix for Gantt bar color classification; exact-match vs substring strategy; implemented |
| 26 | 2026-03-26-13-trace-observability-gaps-design.md | KEEP | Trace metadata enrichment for executor nodes; returncode, failure_reason, verdict capture |
| 27 | 2026-03-26-14-dashboard-timeline-wall-clock-with-navigation-design.md | KEEP | Wall-clock timeline with live/history toggle architecture; key UI feature |
| 28 | 2026-03-26-14-intake-analysis-silent-failure-design.md | ARCHIVE | Bug fix for ClaudeResult.failure_reason visibility; implemented |
| 29 | 2026-03-26-15-session-tracking-and-cost-history-design.md | KEEP | Session lifecycle architecture; sessions table, startup/shutdown, /sessions page |
| 30 | 2026-03-26-15-traces-timestamps-utc-not-local-design.md | ARCHIVE | Client-side UTC-to-local conversion via &lt;time&gt; element; implemented |
| 31 | 2026-03-26-16-tool-calls-missing-from-traces-design.md | ARCHIVE | Bug fix for grandchild trace fetching; implemented in routes/proxy.py |
| 32 | 2026-03-26-16-worker-velocity-tracking-design.md | KEEP | Worker velocity (tokens/min) architecture; WorkerInfo methods, SSE payload, completions table |
| 33 | 2026-03-26-17-trace-expand-chevron-duplicate-and-inline-design.md | ARCHIVE | UI bug fix for CSS marker suppression; implemented |
| 34 | 2026-03-26-17-work-item-status-clarity-design.md | KEEP | Pipeline stage waterfall (9-condition derivation) architecture; key for understanding item lifecycle |
| 35 | 2026-03-26-18-work-item-duplicate-traces-design.md | ARCHIVE | Bug fix; unique index and ON CONFLICT upsert for traces deduplication; implemented |
| 36 | 2026-03-26-19-validator-marks-incomplete-work-as-done-design.md | KEEP | Validator prompt rigor design; binary YES/NO criteria; ongoing reference for validation quality |
| 37 | 2026-03-26-20-worker-trace-link-finds-nothing-design.md | ARCHIVE | Bug fix for async run_id discovery in claimed files; implemented |
| 38 | 2026-03-26-21-intake-throttle-warns-but-doesnt-block-design.md | KEEP | Intake throttle blocking enforcement architecture; shutdown event integration |
| 39 | 2026-03-26-22-cost-data-gaps-in-traces-design.md | KEEP | Cost capture architecture; ClaudeResult.total_cost_usd wiring for all Claude nodes |
| 40 | 2026-03-26-25-migrate-tests-off-legacy-plan-orchestrator-design.md | ARCHIVE | Task complete; plan-orchestrator.py deleted; tests/test_agent_identity.py migrated; no ongoing value |
| 41 | 2026-03-26-26-remove-tilde-cost-prefix-from-templates-design.md | ARCHIVE | Cleanup task; 19 tilde-prefix occurrences replaced in templates; implemented |
| 42 | 2026-03-26-27-tool-call-cost-attribution-dummy-data-design.md | UPDATE | References plan-orchestrator.py executor nodes — update to reference langgraph_pipeline/executor/nodes/; wiring architecture otherwise valid |
| 43 | 2026-03-26-28-cost-by-node-type-display-bugs-design.md | ARCHIVE | Display bug fixes for SVG bar chart (float values, padding); implemented |
| 44 | 2026-03-26-29-duplicate-trace-rows-start-and-end-events-design.md | ARCHIVE | Bug fix; ON CONFLICT deduplication for trace rows; implemented |
| 45 | 2026-03-26-30-cost-posting-uses-wrong-env-var-and-is-never-wired-design.md | KEEP | ORCHESTRATOR_WEB_URL architecture; env var design for cost data pipeline wiring |
| 46 | 2026-03-26-31-validation-criteria-must-be-checklist-with-clear-outcomes-design.md | KEEP | Planner/validator prompt policy; binary YES/NO acceptance criteria; ongoing reference |
| 47 | 2026-03-26-32-test-data-cleanup-and-random-values-policy-design.md | KEEP | Test data hygiene policy; coder.md and validator.md test-data leak check |
| 48 | 2026-03-26-33-wire-up-real-cost-data-pipeline-design.md | KEEP | Cost data pipeline wiring; ENV_ORCHESTRATOR_WEB_URL flow from cli.py to task_runner/validator |
| 49 | 2026-03-26-34-remove-tilde-cost-prefix-third-attempt-design.md | ARCHIVE | Duplicate of 26-remove-tilde; same task (third attempt number); implemented |
| 50 | 2026-03-26-35-work-item-page-missing-requirements-from-backlog-file-design.md | ARCHIVE | "Implementation Status: COMPLETE"; priority chain fix for _find_requirements_file(); implemented |
| 51 | 2026-03-26-36-cost-analysis-ui-polish-design.md | KEEP | UI polish decisions for cost analysis page; tooltip vs collapsible, pagination choices |
| 52 | 2026-03-26-37-ui-quality-process-lost-in-langgraph-migration-design.md | KEEP | UI quality process restoration; ux-designer/frontend-coder workflow; ongoing reference |
| 53 | 2026-03-26-38-tool-call-attribution-table-missing-attribution-column-design.md | ARCHIVE | "Implementation Status: Review Required" — tilde prefix fix in attribution table; implemented |
| 54 | 2026-03-26-39-scan-backlog-trace-confusing-inputs-outputs-design.md | ARCHIVE | UI relabeling for scan_backlog trace; context-aware labels; implemented |
| 55 | 2026-03-26-40-remove-redundant-scan-backlog-node-design.md | KEEP | Graph topology change; scan_backlog node removal rationale and new entry point |
| 56 | 2026-03-26-41-rename-misleading-graph-nodes-design.md | ARCHIVE | Code renames complete (verify_symptoms→verify_fix, etc.); no ongoing value |
| 57 | 2026-03-26-42-task-status-json-blocked-by-sensitive-file-protection-design.md | KEEP | tmp/task-status.json relocation policy; ongoing reference for orchestrator file handling |
| 58 | 2026-03-26-43-capture-agent-traces-per-item-for-review-design.md | KEEP | Per-item Claude Code trace capture architecture; future feature design |
| 59 | 2026-03-26-43-capture-raw-worker-output-per-item-design.md | KEEP | Worker console output capture to docs/reports/worker-output/; ongoing architectural reference |
| 60 | 2026-03-26-44-cost-analysis-disclaimer-use-tooltip-not-collapsible-design.md | ARCHIVE | UI pattern decision (inline tooltip vs collapsible section); implemented |
| 61 | 2026-03-26-46-item-page-show-last-run-and-velocity-design.md | KEEP | Item page last trace link and velocity badge architecture |
| 62 | 2026-03-26-47-velocity-badge-on-item-page-design.md | KEEP | Velocity badge with live override for active workers architecture |

### Batch 4a Summary (2026-03-26)

| Classification | Count |
|---------------|-------|
| KEEP | 30 |
| UPDATE | 3 |
| ARCHIVE | 29 |
| DELETE | 0 |
| **Total** | **62** |

### Batch 4a UPDATE Details

Documents classified as UPDATE require the following corrections:

| Doc | Required Updates |
|-----|-----------------|
| 2026-03-26-01-audit-design-docs-for-validity | Clarify plan-orchestrator.py references are historical context (subject of deletion audit), not instructions to call the script |
| 2026-03-26-03-cost-analysis-db-backend | Remove `write_execution_cost_log()` in `scripts/plan-orchestrator.py` reference; the 2026-03-27 version already corrects this |
| 2026-03-26-27-tool-call-cost-attribution-dummy-data | Replace plan-orchestrator.py executor node references with `langgraph_pipeline/executor/nodes/task_runner.py` and `validator.py` |

---

## Batch 4b: 2026-03-27 (50 docs) + Template (1 doc)

Note: 2026-03-27 documents are revised/updated versions of their 2026-03-26 counterparts. Where a -27 doc explicitly confirms implementation as complete ("Status: Review Required", "Previously implemented"), it is classified ARCHIVE. Where it improves on a stale -26 doc (fixing plan-orchestrator.py refs), the -27 version is KEEP. New docs (54, 55, 99) are classified on their own merits.

| # | File | Class | Issues |
|---|------|-------|--------|
| 1 | 2026-03-27-01-audit-design-docs-for-validity-design.md | UPDATE | Same as -26 version; still references plan-orchestrator.py as historical subject; see -26 UPDATE notes |
| 2 | 2026-03-27-01-traces-model-filter-broken-design.md | ARCHIVE | Previously implemented; model filter and column fix confirmed complete in proxy.py |
| 3 | 2026-03-27-02-traces-runs-named-langgraph-design.md | ARCHIVE | Previously implemented; root run naming fix confirmed complete; still in .claimed/ for validation |
| 4 | 2026-03-27-03-cost-analysis-db-backend-design.md | KEEP | Improved version of -26 doc; removes plan-orchestrator.py reference; accurate description of current cost_tasks DB + POST /api/cost architecture |
| 5 | 2026-03-27-03-dashboard-items-stuck-running-design.md | KEEP | Same architectural content as -26 KEEP; no stale refs; ongoing reference for supervisor/DashboardState lifecycle |
| 6 | 2026-03-27-04-dashboard-scrolling-timeline-view-design.md | KEEP | Architecture reference for timeline view; same as -26 KEEP |
| 7 | 2026-03-27-04-timeline-duplicate-labels-and-elapsed-time-design.md | ARCHIVE | Previously implemented; bug fix for proxy_trace.html tick labels |
| 8 | 2026-03-27-05-queue-page-design.md | KEEP | Queue page architecture reference |
| 9 | 2026-03-27-05-traces-trace-id-column-and-filter-design.md | ARCHIVE | Previously implemented; trace_id column and filter feature complete |
| 10 | 2026-03-27-06-dashboard-drill-down-to-trace-design.md | KEEP | Run UUID threading architecture reference |
| 11 | 2026-03-27-06-work-item-detail-page-design.md | ARCHIVE | "Implementation Status: Complete"; work item detail page fully implemented |
| 12 | 2026-03-27-07-completions-paged-table-design.md | KEEP | Completions page architecture reference |
| 13 | 2026-03-27-07-timeline-bar-colors-too-similar-design.md | ARCHIVE | Previously implemented; color palette change applied |
| 14 | 2026-03-27-08-timeline-sub-second-precision-lost-design.md | ARCHIVE | Previously implemented; datetime.fromisoformat() fix applied |
| 15 | 2026-03-27-08-tracing-proxy-narrative-and-guid-generation-design.md | KEEP | Narrative and architectural context for tracing proxy; ongoing reference |
| 16 | 2026-03-27-09-completions-finished-invalid-date-design.md | ARCHIVE | Previously implemented; dashboard.js fmtFinished() type-check applied |
| 17 | 2026-03-27-09-verification-notes-in-work-item-page-design.md | KEEP | Verification notes data flow architecture reference |
| 18 | 2026-03-27-10-error-stream-always-empty-design.md | KEEP | DashboardErrorHandler architecture reference |
| 19 | 2026-03-27-10-trace-cost-analysis-page-design.md | KEEP | Cost analysis page architecture reference; json_extract() query design |
| 20 | 2026-03-27-11-nav-active-item-styling-design.md | ARCHIVE | Previously implemented; pill styling applied |
| 21 | 2026-03-27-11-tool-call-cost-attribution-design.md | KEEP | Tool call cost attribution architecture reference |
| 22 | 2026-03-27-12-inclusive-cost-precomputation-design.md | KEEP | Two-pass inclusive cost query optimization architecture |
| 23 | 2026-03-27-13-timeline-all-items-show-as-other-design.md | ARCHIVE | Previously implemented; bar color exact-match fix applied |
| 24 | 2026-03-27-13-trace-observability-gaps-design.md | KEEP | Trace metadata enrichment architecture; returncode, failure_reason |
| 25 | 2026-03-27-14-dashboard-timeline-wall-clock-with-navigation-design.md | KEEP | Wall-clock timeline architecture reference |
| 26 | 2026-03-27-14-intake-analysis-silent-failure-design.md | ARCHIVE | Previously implemented; ClaudeResult.failure_reason wiring complete |
| 27 | 2026-03-27-15-session-tracking-and-cost-history-design.md | KEEP | Describes sessions table + /sessions page architecture; sessions.py EXISTS (fully implemented) but doc provides architectural reference for ongoing maintenance |
| 28 | 2026-03-27-15-traces-timestamps-utc-not-local-design.md | ARCHIVE | Previously implemented; UTC-to-local conversion applied |
| 29 | 2026-03-27-16-tool-calls-missing-from-traces-design.md | ARCHIVE | Previously implemented; grandchild trace fetching applied |
| 30 | 2026-03-27-16-worker-velocity-tracking-design.md | ARCHIVE | "Status: Review and fix gaps" — WorkerInfo velocity methods, SSE payload, completions column all exist; feature complete |
| 31 | 2026-03-27-17-trace-expand-chevron-duplicate-and-inline-design.md | ARCHIVE | Previously implemented; CSS marker suppression applied |
| 32 | 2026-03-27-17-work-item-status-clarity-design.md | ARCHIVE | "Previously implemented"; pipeline stage waterfall and _derive_pipeline_stage() complete |
| 33 | 2026-03-27-18-work-item-duplicate-traces-design.md | ARCHIVE | Previously implemented; ON CONFLICT deduplication for traces applied |
| 34 | 2026-03-27-19-validator-marks-incomplete-work-as-done-design.md | KEEP | Validator prompt rigor reference; binary YES/NO criteria design |
| 35 | 2026-03-27-20-worker-trace-link-finds-nothing-design.md | ARCHIVE | Previously implemented; async run_id discovery fix applied |
| 36 | 2026-03-27-22-cost-data-gaps-in-traces-design.md | KEEP | Cost capture architecture reference; ClaudeResult.total_cost_usd design |
| 37 | 2026-03-27-25-migrate-tests-off-legacy-plan-orchestrator-design.md | ARCHIVE | "Previously implemented"; plan-orchestrator.py deleted; all 64 tests migrated; no ongoing value |
| 38 | 2026-03-27-27-tool-call-cost-attribution-dummy-data-design.md | KEEP | Improved version of -26 UPDATE doc; provides accurate wiring architecture for cost attribution |
| 39 | 2026-03-27-28-cost-by-node-type-display-bugs-design.md | ARCHIVE | Previously implemented; SVG bar chart display bugs fixed |
| 40 | 2026-03-27-29-duplicate-trace-rows-start-and-end-events-design.md | ARCHIVE | "Implementation Status: COMPLETE"; ON CONFLICT deduplication complete |
| 41 | 2026-03-27-30-cost-posting-uses-wrong-env-var-and-is-never-wired-design.md | KEEP | ORCHESTRATOR_WEB_URL architecture reference; env var set in cli.py |
| 42 | 2026-03-27-33-wire-up-real-cost-data-pipeline-design.md | KEEP | Cost data pipeline end-to-end flow; ENV_ORCHESTRATOR_WEB_URL integration |
| 43 | 2026-03-27-35-work-item-page-missing-requirements-from-backlog-file-design.md | ARCHIVE | "Previously implemented"; priority chain fix for _find_requirements_file() complete |
| 44 | 2026-03-27-37-ui-quality-process-lost-in-langgraph-migration-design.md | KEEP | UI quality process documentation; ux-designer/frontend-coder workflow reference |
| 45 | 2026-03-27-38-tool-call-attribution-table-missing-attribution-column-design.md | ARCHIVE | "Status: Review Required" — tilde prefix fix in attribution table complete |
| 46 | 2026-03-27-40-remove-redundant-scan-backlog-node-design.md | KEEP | Graph topology change; scan_backlog removal rationale; architectural reference |
| 47 | 2026-03-27-41-rename-misleading-graph-nodes-design.md | ARCHIVE | Code renames complete in source and tests; documentation cleanup the only remaining work (minimal value) |
| 48 | 2026-03-27-54-validator-should-run-e2e-tests-for-ui-criteria-design.md | KEEP | New feature; e2e-test-agent + Playwright configuration architecture; not yet implemented |
| 49 | 2026-03-27-55-readme-setup-guide-for-new-projects-design.md | KEEP | Documentation gap fix; setup-guide.md improvements; ongoing reference for onboarding |
| 50 | 2026-03-27-99-test-val-v2-design.md | ARCHIVE | One-off smoke test (comment addition in paths.py); no ongoing architectural value |
| 51 | YYYY-MM-DD-feature-template.md | KEEP | Template for new design docs; ongoing reference for document structure |

### Batch 4b Summary (2026-03-27 + template)

| Classification | Count |
|---------------|-------|
| KEEP | 25 |
| UPDATE | 1 |
| ARCHIVE | 25 |
| DELETE | 0 |
| **Total** | **51** |

### Batch 4b UPDATE Details

Documents classified as UPDATE require the following corrections:

| Doc | Required Updates |
|-----|-----------------|
| 2026-03-27-01-audit-design-docs-for-validity | Same as -26 UPDATE: clarify plan-orchestrator.py references are historical context (the subject of deletion), not instructions to use the script |

---

## Audit Complete — All 218+ Documents Classified

