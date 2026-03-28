# Ideas Intake Pipeline - Completion Design

## Status: Active

## Overview

The core ideas intake pipeline shipped in v1.9.0 with `idea_classifier.py`,
`paths.py` constants, CLI scan-loop integration, and unit tests. One gap
remains: the parallel supervisor loop (`supervisor.py`) does not call
`process_ideas()`, so files dropped in `docs/ideas/` are ignored when the
pipeline runs with `max_parallel_items > 1`.

## Existing Implementation

| File | Status |
|------|--------|
| `langgraph_pipeline/pipeline/nodes/idea_classifier.py` | Complete |
| `langgraph_pipeline/shared/paths.py` (IDEAS_DIR, IDEAS_PROCESSED_DIR) | Complete |
| `langgraph_pipeline/cli.py` — sequential scan loop calls `process_ideas()` | Complete |
| `tests/test_idea_classifier.py` | Complete, all 12 tests pass |
| `docs/ideas/` + `docs/ideas/processed/` directories | Present, git-tracked |

## Remaining Gap

`supervisor.py:run_supervisor_loop()` is the code path executed when
`max_parallel_items > 1`. Its main iteration loop reaps finished workers and
dispatches new ones, but never calls `process_ideas()`. Ideas files will
therefore accumulate unprocessed whenever the pipeline runs in parallel mode.

## Fix

Add a `process_ideas(dry_run)` call at the top of each supervisor iteration,
matching the placement in the sequential scan loop:

```
while not shutdown_event.is_set():
    ideas_processed = process_ideas(dry_run)    # <-- add here
    if ideas_processed > 0:
        logger.info("Ideas intake: processed %d idea(s)", ideas_processed)
    # Step 1: Reap finished workers...
```

## Key Files

| Change | File |
|--------|------|
| Add `process_ideas()` call in supervisor iteration loop | `langgraph_pipeline/supervisor.py` |
| Add supervisor-mode ideas integration test | `tests/test_supervisor_ideas.py` |
| Version bump (patch) | `plugin.json`, `RELEASE-NOTES.md` |

## Design Decisions

- **No API change**: `process_ideas()` already accepts `dry_run`; the
  supervisor already carries that flag through its arguments.
- **Non-blocking**: `process_ideas()` returns quickly when no ideas exist
  (empty `docs/ideas/`), so it adds negligible overhead to the dispatch loop.
- **Same placement as sequential mode**: calling at the top of each iteration
  ensures ideas are processed before a new worker slot is filled, matching
  the sequential loop behavior.
