# Design: Remove Unnecessary completed_slugs() Scan on Every Pipeline Cycle

## Date: 2026-02-16
## Defect: docs/defect-backlog/02-unnecessary-completed-slugs-scan.md
## Status: Draft

## Problem

The auto-pipeline calls `completed_slugs()` inside `scan_all_backlogs()` on
every scan cycle. After feature 09 moved all completed items to a separate
directory (`docs/completed-backlog/`), the completed slugs never overlap with
scan results because `scan_directory()` only reads from `docs/defect-backlog/`
and `docs/feature-backlog/`. However, `completed_slugs()` still serves a
purpose: **dependency resolution**. Backlog items can declare dependencies via
a `## Dependencies` section, and the pipeline uses the completed set to check
whether those dependencies are satisfied.

The issue is:
1. The verbose log line (`Completed slugs: {...}`) grows unbounded and provides
   no operational value.
2. `completed_slugs()` is called unconditionally even when no items have
   dependencies, adding unnecessary filesystem I/O.

## Architecture Overview

The call chain is:

```
main_loop() -> scan_all_backlogs() -> completed_slugs()
                                   -> parse_dependencies() per item
```

`completed_slugs()` scans `docs/completed-backlog/defects/` and
`docs/completed-backlog/features/` and returns a `set[str]` of stems. This set
is then used to check whether each item's declared dependencies are satisfied.

### Key Observation

The defect's original proposal to "remove `completed_slugs()` call and filtering"
is partially correct. The filtering of completed items from scan results is
indeed unnecessary (they are in a separate directory). But the dependency check
against the completed set is still meaningful functionality and must be preserved.

## Design Decision

**Optimize, don't delete.** We will:

1. **Remove the noisy verbose log** (line 450) that prints the full completed set.
2. **Lazy-evaluate `completed_slugs()`**: only call it when at least one item
   declares dependencies, avoiding filesystem I/O on cycles with no dependencies.
3. **Keep the function and the dependency filtering logic** - they provide real
   value for items that depend on other completed work.
4. **Update the test for `completed_slugs`** if needed, and add a regression test
   for the lazy-evaluation behavior.

## Files Affected

| File | Change |
|------|--------|
| scripts/auto-pipeline.py | Refactor `scan_all_backlogs()` to lazy-call `completed_slugs()` and remove verbose log |
| tests/test_completed_archive.py | Add regression test for lazy dependency resolution |

## Detailed Changes

### scripts/auto-pipeline.py - `scan_all_backlogs()`

Current code (lines 438-466):
```python
def scan_all_backlogs() -> list[BacklogItem]:
    defects = scan_directory(DEFECT_DIR, "defect")
    features = scan_directory(FEATURE_DIR, "feature")
    all_items = defects + features

    done = completed_slugs()
    verbose_log(f"Completed slugs: {done}")

    ready: list[BacklogItem] = []
    for item in all_items:
        deps = parse_dependencies(item.path)
        if not deps:
            ready.append(item)
            continue
        unsatisfied = [d for d in deps if d not in done]
        if unsatisfied:
            log(f"Skipped: {item.slug} (waiting on: {', '.join(unsatisfied)})")
        else:
            ready.append(item)
    return ready
```

Proposed code:
```python
def scan_all_backlogs() -> list[BacklogItem]:
    defects = scan_directory(DEFECT_DIR, "defect")
    features = scan_directory(FEATURE_DIR, "feature")
    all_items = defects + features

    # Lazy: only load completed slugs when needed for dependency resolution
    done: set[str] | None = None

    ready: list[BacklogItem] = []
    for item in all_items:
        deps = parse_dependencies(item.path)
        if not deps:
            ready.append(item)
            continue
        # First item with dependencies triggers the scan
        if done is None:
            done = completed_slugs()
        unsatisfied = [d for d in deps if d not in done]
        if unsatisfied:
            log(f"Skipped: {item.slug} (waiting on: {', '.join(unsatisfied)})")
        else:
            ready.append(item)
    return ready
```

Key changes:
- Remove `verbose_log(f"Completed slugs: {done}")` entirely
- Defer `completed_slugs()` call until the first item with dependencies is found
- If no items have dependencies (the common case today), no filesystem I/O occurs

## Risks

- **Low**: If a new backlog item adds a `## Dependencies` section, the lazy
  evaluation will still work correctly - it just triggers the scan on demand.
- **None**: The `completed_slugs()` function itself is unchanged, so
  `archive_item()` and any future callers are unaffected.
