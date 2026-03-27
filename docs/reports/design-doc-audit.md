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

*Batches 2, 3, and 4 will be appended by subsequent audit tasks.*
