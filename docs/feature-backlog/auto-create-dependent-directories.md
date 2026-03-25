# Auto-Create Dependent Directories

## Status: Open

## Priority: Medium

## Summary

Both `plan-orchestrator.py` and `auto-pipeline.py` depend on several directories
existing before they run (logs, status files, agent claims, etc.). Currently,
projects must manually create these directories or risk runtime errors. Both scripts
should auto-create any directories they depend on at startup so projects don't need
to worry about it.

## Current State

Some directories are already auto-created in specific code paths (e.g.,
`TASK_LOG_DIR.mkdir(parents=True, exist_ok=True)` before writing task logs), but
this is inconsistent. Other paths assume the directory exists and fail if it doesn't.

## Proposed Changes

### plan-orchestrator.py

Add a startup directory check that ensures all of these exist:

- `.claude/plans/` (plan files)
- `.claude/plans/logs/` (task logs and usage reports)
- `.claude/subagent-status/` (parallel worker heartbeats)
- `logs/` (general logs)
- `logs/e2e/` (E2E test result logs, per spec-aware-validator feature)

### auto-pipeline.py

Add a startup directory check that ensures all of these exist:

- `.claude/plans/` (plan files)
- `logs/` (per-item detail logs and summary log)
- `docs/defect-backlog/` (monitored input)
- `docs/feature-backlog/` (monitored input)
- `docs/completed-backlog/features/` (archive destination)
- `docs/completed-backlog/defects/` (archive destination)

### Implementation

Add an `ensure_directories()` function near the top of each script, called once
at startup before any other logic. Use `os.makedirs(path, exist_ok=True)` for
each directory. Log a message for any directory that had to be created so the
user knows it was missing.

```python
REQUIRED_DIRS = [
    ".claude/plans/",
    ".claude/plans/logs/",
    "logs/",
    # etc.
]

def ensure_directories():
    for d in REQUIRED_DIRS:
        if not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
            print(f"[INIT] Created missing directory: {d}")
```

Remove any scattered `mkdir` calls that become redundant after this centralized check.

## Files Affected

- Modified: `scripts/plan-orchestrator.py`
- Modified: `scripts/auto-pipeline.py`
