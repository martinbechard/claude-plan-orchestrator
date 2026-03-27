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

*Batch 3 and 4 will be appended by subsequent audit tasks.*
