# README: document setup guide for new projects using the orchestrator

## Summary

When setting up the orchestrator in a new project, there is no clear
documentation of what needs to be configured: .gitignore entries, directory
structure, config files, environment variables, and dependencies. This
information is scattered across code comments and tribal knowledge.

## What the README should cover

1. .gitignore entries needed:
   - tmp/plans/ (plan YAMLs, PID files, task logs, claimed items)
   - tmp/task-status.json
   - docs/reports/worker-output/ (planner logs, validation JSONs)
   - .claude/pipeline-state.db and worker DBs
   - .claude/orchestrator-traces.db (or wherever the proxy DB lives)

2. Directory structure to create:
   - docs/defect-backlog/
   - docs/feature-backlog/
   - docs/analysis-backlog/
   - docs/completed-backlog/{defects,features,analyses}/
   - docs/ideas/ and docs/ideas/processed/
   - docs/plans/ (design documents)
   - docs/reports/worker-output/
   - tmp/plans/

3. Configuration:
   - .claude/orchestrator-config.yaml (max_parallel_items, build_command,
     test_command, dev_server settings, web proxy settings)
   - Agent definitions in .claude/agents/
   - Slack setup (if using Slack integration)

4. Dependencies:
   - Python packages (langgraph, langsmith, fastapi, uvicorn, etc.)
   - Claude Code CLI with --dangerously-skip-permissions support
   - Optional: chromadb for RAG dedup, playwright for e2e tests

5. First run checklist:
   - Verify claude CLI works
   - Start pipeline with --dry-run first
   - Create a test backlog item and verify end-to-end

## Acceptance Criteria

- Does the README contain a setup section with .gitignore entries?
  YES = pass, NO = fail
- Does it list all directories that need to be created?
  YES = pass, NO = fail
- Can a new user follow the README to set up the orchestrator from scratch
  without asking questions? YES = pass, NO = fail
