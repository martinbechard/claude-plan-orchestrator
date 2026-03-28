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

## LangSmith Trace: 58d8e2d6-5c70-447b-8a1d-806fd14be073
