# Design: Capture Raw Worker Console Output Per Item

**Work Item:** `docs/feature-backlog/43-capture-raw-worker-output-per-item.md`
**Date:** 2026-03-26

## Problem

When investigating why a pipeline agent made a bad decision, we need the raw
console output (tool calls, file reads, bash commands, Claude responses) that
was produced during that item's processing. Task logs already exist in
`.claude/plans/logs/task-YYYYMMDD-HHMMSS.log` but they are timestamped, not
linked to work items, and not accessible from the web UI.

## Architecture Overview

### Storage: Per-Item Output Directory

Create `docs/reports/worker-output/<slug>/` containing one log file per task
execution, named by task ID and timestamp:

```
docs/reports/worker-output/43-capture-raw-worker-output/
  task-1.1-20260326-143022.log
  task-1.2-20260326-143512.log
  task-1.1-attempt2-20260326-144001.log   (retry)
```

Each file contains the full raw stdout and stderr captured by OutputCollector,
plus a metadata header with model, cost, tokens, duration, and return code.

### Capture: Extend _write_task_log in task_runner.py

The existing `_write_task_log()` already writes full stdout/stderr. Extend it
to also write a slug-keyed copy when the slug is known. The slug is derivable
from `plan_path` (strip directory prefix and `.yaml` suffix).

Changes to `execute_task()` node:
- Derive slug from `state["plan_path"]`
- Pass slug and task_id to `_write_task_log()`
- Write the per-item output file alongside the existing timestamped log

Also extend `parallel.py` (`_run_claude_in_worktree`) which currently skips
log writing entirely.

### Web UI: Add console output section to /item/{slug}

Extend `item.py` route to discover log files in
`docs/reports/worker-output/<slug>/` and pass them to the template.

Add a new API endpoint `GET /item/{slug}/output/{filename}` that returns a log
file's raw content as `text/plain`.

Add a collapsible "Console Output" section to `item.html` listing all captured
log files with links to view raw content, plus an inline expandable preview.

## Key Files

| File | Action |
|------|--------|
| `langgraph_pipeline/executor/nodes/task_runner.py` | Modified -- add slug-keyed output writing |
| `langgraph_pipeline/executor/nodes/parallel.py` | Modified -- add output writing (currently missing) |
| `langgraph_pipeline/shared/paths.py` | Modified -- add WORKER_OUTPUT_DIR constant |
| `langgraph_pipeline/web/routes/item.py` | Modified -- load output files, add raw endpoint |
| `langgraph_pipeline/web/templates/item.html` | Modified -- add console output section |
| `docs/reports/worker-output/` | New directory (created by code) |

## Design Decisions

- **Per-slug directory**: Groups all output for one item together, making it
  trivial to find and clean up. The alternative (single flat dir with naming
  convention) gets unwieldy with retries and multiple tasks.
- **Keep existing timestamped logs**: The per-slug output is additive. Existing
  `.claude/plans/logs/` files remain for backward compatibility and debugging.
- **Raw text/plain endpoint**: Console output can be large. Serving it as plain
  text allows browser-native scrolling and search. The item page links to it
  rather than inlining megabytes of log text.
- **Cover parallel.py**: The parallel task runner currently skips log writing.
  This feature adds it so all execution paths produce output files.
