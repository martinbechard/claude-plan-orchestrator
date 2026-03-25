# Supervisor spawns duplicate workers for the same backlog item

## Status: Open

## Priority: High

## Summary

When the pipeline is restarted while workers are active, the supervisor spawns
multiple workers processing the same backlog item simultaneously. Observed: 3–4
workers all launched with the same `--item-path .claude/plans/.claimed/<slug>.md`
and different `--result-file` UUIDs. This wastes quota, produces race conditions
on git operations, and blocks other backlog items from starting.

## Observed Behaviour

```
PID 52121  worker --item-path .claimed/03-improve-the-ux.md  --item-type feature
PID 60324  worker --item-path .claimed/03-improve-the-ux.md  --item-type analysis
PID 60527  worker --item-path .claimed/03-improve-the-ux.md  --item-type analysis
```

Three workers running concurrently on the same item, two with conflicting
`--item-type` values (`feature` vs `analysis`). All slots (max_workers=4) were
consumed, so other items (including analyses) never started.

## Root Causes

Two separate issues combine to produce this failure:

### RC-1 — No startup cleanup of orphaned claims (fixed in 36b3bacb)

`run_supervisor_loop` starts with `active_workers = {}` and never inspects
`.claimed/`. When the supervisor restarts after a crash, items claimed by
now-dead workers remain in `.claimed/` invisibly — `scan_backlog` only scans
the backlog directories, not `.claimed/`. Those items are permanently stuck and
never processed again.

**Fix already applied (36b3bacb):** `_unclaim_orphaned_items()` is called once
at supervisor startup and moves every `.md` in `.claimed/` back to its original
backlog directory, so they re-enter the normal priority queue.

### RC-2 — `claim_item()` silently succeeds when source == destination (open)

`claim_item(item_path)` uses `os.rename(item_path, claimed_path)` where
`claimed_path = CLAIMED_DIR / basename(item_path)`. On macOS (APFS) and Linux,
`os.rename(path, path)` where source and destination are the **same path** is a
no-op that returns successfully without raising `FileNotFoundError`.

This means: if `scan_backlog` ever returns a path that is already inside
`.claimed/` (e.g., via a stale in-progress plan resume or a second pipeline
instance rescanning), `claim_item` returns `True` and a duplicate worker is
spawned.

**Trigger sequence:**
1. Supervisor A starts, moves item to `.claimed/`, spawns worker W1.
2. Supervisor A is killed (SIGKILL or pipeline restart).
3. Supervisor B starts. `_unclaim_orphaned_items` moves item back to backlog.
4. Dispatch loop: `_scan_next_item()` finds the item, `claim_item` succeeds →
   worker W2 spawned. Loop continues (`len(active_workers)=1 < max_workers`).
5. For reasons not yet fully understood, `_scan_next_item()` returns the same
   item a second time (possibly from in-progress plan detection pointing to the
   now-claimed path, or a filesystem cache), `claim_item(.claimed/x, .claimed/x)`
   no-ops → W3 spawned.

## Proposed Fix for RC-2

In `claim_item()`, detect the case where source and destination are the same
path and return `False` (item already claimed) instead of silently succeeding:

```python
def claim_item(item_path: str) -> bool:
    os.makedirs(CLAIMED_DIR, exist_ok=True)
    basename = os.path.basename(item_path)
    claimed_path = os.path.join(CLAIMED_DIR, basename)

    # Guard: if item_path is already the claimed path, it's already claimed.
    if os.path.abspath(item_path) == os.path.abspath(claimed_path):
        return False

    try:
        os.rename(item_path, claimed_path)
        return True
    except FileNotFoundError:
        return False
```

Additionally, `_scan_next_item()` should never return a path inside `CLAIMED_DIR`.
A defensive guard in `_scan_directory` (or in `scan_backlog`) that skips any
path whose parent is `CLAIMED_DIR` would prevent the issue even if `claim_item`
is called with a claimed path.

## Additional Observation — Item Type Conflict

Duplicate workers were spawned with conflicting `--item-type` values (`feature`
vs `analysis`) for the same item. This indicates `_unclaim_orphaned_items` (RC-1
fix) inferred the wrong type for at least one orphan. The type-inference heuristic
(check for "defect" or "analysis" in the path string) is fragile — item slugs
rarely contain those words. A more robust approach: store the item type alongside
the claimed path (e.g., in a sidecar `.json` file written at claim time) so that
unclaim always restores to the correct directory.

## Reproduction Steps

1. Start the pipeline with a non-empty backlog.
2. While a worker is active (`ps aux | grep langgraph_pipeline.worker`), kill
   the supervisor process (`kill <pipeline_pid>`).
3. Restart the pipeline immediately.
4. Observe `ps aux | grep langgraph_pipeline.worker` — multiple workers will be
   processing the same `--item-path`.

## Impact

- **Quota waste:** duplicate workers burn Claude API quota on identical work.
- **Git conflicts:** concurrent workers committing to the same branch produce
  merge failures or lost commits.
- **Starvation:** all `max_workers` slots consumed by duplicates; other backlog
  items (lower priority, e.g., analyses) never start.
- **Wrong item type:** misclassified unclaim can permanently strand an item in
  the wrong backlog directory.

## LangSmith Trace: 648a361a-17f6-48e1-bf57-aee2e19c62bc
