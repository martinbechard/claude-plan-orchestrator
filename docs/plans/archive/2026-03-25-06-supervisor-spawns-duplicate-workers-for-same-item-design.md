# Supervisor Spawns Duplicate Workers for Same Item - Design

## Overview

When the pipeline supervisor restarts while workers are active, it can spawn
multiple workers for the same backlog item. RC-1 (startup orphan cleanup) was
fixed in commit 36b3bacb. This plan addresses RC-2 and the associated item-type
misclassification.

## Root Cause RC-2

`claim_item(item_path)` computes `claimed_path = CLAIMED_DIR / basename(item_path)`.
When `item_path` is already inside `CLAIMED_DIR`, source and destination are identical.
On macOS (APFS) and Linux, `os.rename(path, path)` is a no-op: it returns without
error instead of raising `FileNotFoundError`. So `claim_item` returns `True` and the
supervisor spawns a duplicate worker.

The trigger: `scan_backlog` calls `_find_in_progress_plans()`, which reads each plan
YAML's `meta.source_item`. Plans are created after claiming, so `source_item` often
points into `.claimed/`. When that path exists, `scan_backlog` returns it as the
next item, `_try_dispatch_one` calls `claim_item(.claimed/x)`, the same-path rename
no-ops, and a second worker is spawned.

## Root Cause — Item Type Conflict

`_unclaim_orphaned_items()` infers item type from the slug string ("defect" or
"analysis" substring). Most slugs contain neither word, so items default to "feature"
regardless of their true type. This can permanently strand items in the wrong backlog
directory and assigns a conflicting `--item-type` to a duplicate worker.

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/pipeline/nodes/scan.py` | `claim_item()` same-path guard; scan filter for CLAIMED_DIR paths; sidecar read/write in claim/unclaim |
| `langgraph_pipeline/supervisor.py` | Pass `item_type` to `claim_item()`; sidecar cleanup in `_unclaim_orphaned_items()` |
| `tests/langgraph/test_parallel_items.py` | New tests for same-path guard, scan filter, and sidecar |
| `plugin.json` | Patch version bump |
| `RELEASE-NOTES.md` | New entry for this fix |

## Design Decisions

### Fix 1 — `claim_item()` same-path guard

Add an `item_type: str = "feature"` parameter. Before attempting `os.rename`, compare
`os.path.abspath(item_path)` with `os.path.abspath(claimed_path)`. If equal, return
`False` immediately — the item is already claimed.

Default value for `item_type` preserves backward compatibility with existing call sites
that omit it (tests, legacy paths).

### Fix 2 — Defensive scan filter for CLAIMED_DIR paths

In `_scan_directory()`, add a guard at the top of the file loop that skips any file
whose resolved parent path equals the resolved `CLAIMED_DIR`. This prevents
`_find_in_progress_plans` returns (or any future scan path) from being fed back into
the claim cycle.

Additionally, in `scan_backlog`, when processing an in-progress plan's `source_item`,
skip (and log a warning) if the source_item path is inside `CLAIMED_DIR`. The item is
already being worked on.

### Fix 3 — Item-type sidecar

At claim time, `claim_item()` writes a sidecar file
`{basename}.claim-meta.json` beside the claimed `.md` file, containing `{"item_type": item_type}`.

At `unclaim_item()` time, the sidecar is removed alongside the `.md` file.

In `_unclaim_orphaned_items()`, the sidecar is read to obtain the correct `item_type`
before calling `unclaim_item`. If the sidecar is missing (legacy or corrupted), fall
back to the existing slug-heuristic.

The sidecar suffix is defined as a manifest constant `CLAIM_META_SUFFIX = ".claim-meta.json"`.

### Why not a single fix?

The same-path guard alone prevents duplicate spawning for the `source_item` path case.
The scan filter adds defense-in-depth against any future code path that could return a
CLAIMED_DIR path. The sidecar fix is independent: it prevents item-type conflicts on
unclaim, which would otherwise strand items in the wrong backlog directory.
