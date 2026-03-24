# Design: Parallel Backlog Item Processing — Supervisor + Worker Model

**Date:** 2026-03-24
**Feature:** docs/feature-backlog/06-parallel-item-processing-supervisor-worker-model.md
**Status:** Draft

---

## Architecture Overview

The current pipeline processes one backlog item at a time in `_run_scan_loop()` inside
`cli.py`. This change adds a configurable worker pool so N items execute concurrently.

The model is a lightweight **supervisor** that owns scanning, dispatch, budget tracking,
and reporting, plus N **worker subprocesses** — one per active item — each running the
full pipeline graph in isolation.

```
Supervisor (cli.py / supervisor.py)
  ├─ scan backlog → claim item (atomic POSIX rename into .claimed/)
  ├─ spawn Worker-1 (item: bug-3)  → .claude/plans/worker-{pid}.result.json
  ├─ spawn Worker-2 (item: feat-1) → .claude/plans/worker-{pid}.result.json
  └─ on worker exit: read result, archive/re-queue, update budget, pick next item
```

---

## Key Files

### New files

| File | Purpose |
|------|---------|
| `langgraph_pipeline/worker.py` | Worker subprocess entry point; runs the pipeline graph for one item and writes a JSON result file |
| `langgraph_pipeline/supervisor.py` | Supervisor logic: dispatch loop, worker slot tracking, result aggregation, git-commit serialization |

### Modified files

| File | Change |
|------|--------|
| `langgraph_pipeline/shared/paths.py` | Add `CLAIMED_DIR` and `WORKER_RESULT_DIR` path constants |
| `langgraph_pipeline/shared/config.py` | Expose `get_max_parallel_items(config)` helper reading `pipeline.max_parallel_items` |
| `langgraph_pipeline/pipeline/nodes/scan.py` | Add `claim_item(path) -> bool` and `unclaim_item(claimed_path) -> None` using atomic `os.rename()` |
| `langgraph_pipeline/cli.py` | Route to supervisor when `max_parallel_items > 1`; single-item path stays unchanged |

---

## Design Decisions

### Item claiming

`claim_item(path)` performs `os.rename(path, .claude/plans/.claimed/<basename>)`.
Since POSIX `rename()` is atomic, the process that wins the rename processes the item;
all others see `FileNotFoundError` and skip it. `unclaim_item()` renames back on failure.

### Worker result handshake

Worker writes `.claude/plans/worker-{pid}.result.json` just before exit:

```json
{
  "success": true,
  "item_path": "docs/feature-backlog/01-foo.md",
  "cost_usd": 0.042,
  "input_tokens": 12000,
  "output_tokens": 3400,
  "duration_s": 87.3,
  "message": "Task completed"
}
```

Supervisor reads this after `waitpid()`. A non-zero exit code with no result file is
treated as a crash; the claimed item is un-claimed (renamed back to its backlog directory).

### Budget cap

Enforced exclusively in the supervisor after reading each worker result. Workers receive
no budget cap; they run to completion. The supervisor stops dispatching new items once
the cumulative session cost meets or exceeds the cap.

### Git isolation

Each worker runs `pipeline_graph()` inside its own git worktree (reusing the pattern
from `parallel.py`). The supervisor serializes `git commit` calls back to main via a
threading lock, preventing index corruption.

### Backwards compatibility

`pipeline.max_parallel_items` defaults to 1. At N=1 the supervisor dispatches a single
worker at a time, producing identical behavior to today's sequential scan loop.

---

## Config

Add to `orchestrator-config.yaml` (optional, defaults to 1):

```yaml
pipeline:
  max_parallel_items: 2
```

---

## Phased Implementation

| Phase | Scope |
|-------|-------|
| 1 | Foundation: paths, config helper, `claim_item`/`unclaim_item` in scan.py |
| 2 | Worker entry point: `langgraph_pipeline/worker.py` |
| 3 | Supervisor module (`supervisor.py`) and CLI integration (`cli.py`) |
| 4 | Unit tests for all new code |
