# Parallel backlog item processing via supervisor + worker model

## Status: Open

## Priority: Medium

## Summary

The pipeline currently processes one backlog item at a time. Add a configurable worker
pool so N items can execute concurrently. The recommended architecture is a
supervisor + worker model: a lightweight supervisor process owns backlog scanning,
item dispatch, budget tracking, Slack reporting, and the PID file; it spawns one worker
subprocess per item running a stripped-down executor-only entry point. Workers report
completion, cost, and outcome back to the supervisor via a small JSON result file.
The supervisor aggregates results, enforces the budget cap centrally, and picks the next
item only when a worker slot is free. Parallelism degree is a config parameter
(pipeline.max_parallel_items) defaulting to 1 for backwards compatibility.

## Architecture

```
Supervisor
  ├─ scan backlog, pick up to N items
  ├─ spawn Worker-1 (item: bug-3)  →  result file: {cost, success, duration}
  ├─ spawn Worker-2 (item: feat-1) →  result file: {cost, success, duration}
  └─ on worker exit: read result, archive item, update budget, pick next item
```

## Key Design Decisions

- **Backlog item claiming**: atomic POSIX rename of the item file into a `.claimed/`
  staging directory; only the process that wins the rename processes that item.
- **Budget cap**: enforced exclusively in the supervisor after each worker result is
  read; no per-worker budget check needed.
- **Git isolation**: each worker runs in its own git worktree (reuses the existing
  pattern from `parallel.py`); the supervisor serializes `git commit` back to main.
- **Worker result handshake**: worker writes a JSON result file to a known path
  (e.g. `.claude/plans/worker-{pid}.result.json`) on exit; supervisor reads it after
  `waitpid()`.
- **Crash handling**: a worker subprocess that exits non-zero with no result file is
  treated as a failure; the supervisor re-queues or marks the item failed.
- **Backwards compatibility**: `max_parallel_items: 1` (default) produces identical
  behaviour to today's single-item loop.

## 5 Whys Analysis

1. **Why process only one item at a time?** The current pipeline is a single sequential
   LangGraph invocation loop with no dispatch mechanism and shared mutable state that
   is not safe for concurrent access.
2. **Why is that a bottleneck?** Each item spends most of its wall-clock time waiting
   on Claude CLI subprocess I/O; CPU is idle while Claude executes, so sequential
   processing wastes parallelism headroom.
3. **Why not just use threads?** A hung Claude subprocess blocks its thread slot, and a
   crash in a worker thread can destabilize the whole process; subprocess isolation is
   safer for long-running autonomous work.
4. **Why supervisor + worker rather than N independent pipeline processes?** Shared
   state (budget cap, Slack reporting, progress tracking, PID file) needs a single
   authoritative owner; splitting it across N processes requires inter-process
   synchronization that is harder to reason about than in-process state.
5. **Why is the existing codebase a good fit?** The pipeline already has a clean
   two-level graph split (pipeline graph → executor graph), and `parallel.py` already
   uses the git worktree subprocess pattern that workers would reuse.

**Root Need:** Let the pipeline saturate available Claude quota by running multiple
items concurrently while keeping budget enforcement, Slack reporting, and state
management centrally owned by a single supervisor.

## Implementation Notes

- New config key: `pipeline.max_parallel_items` (int, default 1) in
  `orchestrator-config.yaml`.
- Supervisor logic lives in `langgraph_pipeline/cli.py` (or a new
  `langgraph_pipeline/supervisor.py`); the existing scan/sleep loop becomes a
  dispatch loop.
- Worker entry point: `langgraph_pipeline/worker.py` — accepts a single item path
  and runs the executor graph directly, writing the result file on exit.
- Backlog claiming: introduce `claim_item(path) -> bool` in
  `langgraph_pipeline/pipeline/nodes/scan.py` using `os.rename()` into a
  `.claude/plans/.claimed/` directory.
- The `ProgressReporter` (backlog item 05) should be updated to aggregate across
  all active workers.

## Source

Proposed during architecture discussion, 2026-03-24. Option C from a three-option
parallelism analysis (Options A: multi-process file claiming; B: thread pool;
C: supervisor + workers).
