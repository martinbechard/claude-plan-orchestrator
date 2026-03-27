# Design: README Setup Guide for New Projects

## Problem

The existing setup guide (docs/setup-guide.md) and README are missing several items
that a new user would need to set up the orchestrator from scratch:

1. **Incomplete .gitignore entries** -- Missing: tmp/plans/, tmp/task-status.json,
   docs/reports/worker-output/, .claude/pipeline-state.db, .claude/orchestrator-traces.db
2. **Incomplete directory structure** -- Step 5 only creates backlog dirs. Missing:
   docs/analysis-backlog/, docs/completed-backlog/analyses/, docs/ideas/,
   docs/ideas/processed/, docs/plans/, docs/reports/worker-output/, tmp/plans/
3. **Incomplete dependencies** -- Only lists pyyaml and watchdog. Missing: langgraph,
   langsmith, fastapi, uvicorn, and optional deps (chromadb, playwright)
4. **No first-run checklist** -- Step 7 starts the pipeline but lacks a structured
   verification checklist

## Approach

Update docs/setup-guide.md to fill the gaps identified above. The README already
links to the setup guide, so no README changes are needed beyond ensuring the
link remains correct.

## Key Files to Modify

- docs/setup-guide.md -- Main file to update with complete .gitignore, directory
  structure, dependencies, and first-run checklist

## Design Decisions

- Update the existing setup guide rather than creating a separate document
- Keep the numbered step format already in use
- Add all directories from the backlog item to the mkdir command in step 5
- Expand .gitignore section with all transient files from the backlog item
- Add complete dependency list (required + optional) to step 1
- Add a first-run checklist section after step 7
