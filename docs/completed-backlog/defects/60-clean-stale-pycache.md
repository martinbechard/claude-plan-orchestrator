# Clean stale __pycache__ files referencing deleted modules

## Summary

tests/__pycache__/ contains .pyc files for test_auto_pipeline which no
longer exists as a .py file. Clean up all stale .pyc files across the
project.

## Acceptance Criteria

- Are there zero .pyc files in tests/__pycache__/ that reference
  non-existent .py source files? YES = pass, NO = fail
- Is there a .gitignore entry for __pycache__/?
  YES = pass, NO = fail




## 5 Whys Analysis

Title: Clean stale Python bytecode cache from deleted test modules
Clarity: 4

5 Whys:

1. Why do we need to clean stale __pycache__ files?
   Because .pyc files cached for test_auto_pipeline.py still exist even though the source file was deleted, potentially causing import confusion or stale bytecode execution during test runs.

2. Why do these stale .pyc files remain if their source modules no longer exist?
   Because Python's __pycache__ directory persists independently on disk—Python doesn't automatically delete .pyc files when their corresponding .py files are removed; it only regenerates them on next import.

3. Why doesn't Python automatically clean up orphaned bytecode?
   Because the cache layer is designed for performance (avoiding recompilation), not for dependency tracking. Python assumes developers manage cache cleanup through manual deletion or re-running imports.

4. Why wasn't __pycache__ cleaned when test_auto_pipeline.py was deleted?
   Because __pycache__ is typically ignored by version control (.gitignore), so cleanup isn't enforced by the git workflow—deletion of a source file doesn't trigger automated cache removal, and developers must remember to clean it manually or use external tools.

5. Why is this becoming a blocking issue now rather than a minor housekeeping task?
   Because stale bytecode can cause non-deterministic test failures or mask real issues, especially in CI/CD or when developers switch branches—the cache silently references deleted code, breaking the assumption that the filesystem accurately represents what code exists.

Root Need: Maintain a bytecode cache that stays synchronized with actual source code to ensure test reliability and prevent stale artifacts from interfering with development workflows.

Summary: Orphaned Python cache files have accumulated due to lack of automated cleanup, creating risk of non-deterministic test failures and requiring both immediate cleanup and preventive infrastructure.
