# Design: Clean stale __pycache__ files (defect 60)

## Problem

Orphaned .pyc files accumulate in __pycache__/ directories when source .py files
are deleted. These stale bytecodes can cause non-deterministic test failures and
import confusion.

## Current state

- .gitignore already contains __pycache__/ -- pass criterion #2 is already met.
- 14 stale .pyc files found across tests/, langgraph_pipeline/, and scripts/.

## Solution

Single script task:

1. Walk all __pycache__/ directories in the project.
2. For each .pyc file, derive the expected .py source path (strip cpython version
   suffix, look in parent directory).
3. If the source .py does not exist, delete the .pyc file.
4. If a __pycache__/ directory becomes empty after cleanup, remove it.
5. Verify .gitignore contains __pycache__/ (already does, but script should confirm).

## Key files

- **scripts/clean_pycache.py** -- new standalone cleanup script
- **.gitignore** -- already has __pycache__/, no change needed

## Design decisions

- Standalone script rather than integration into the pipeline -- this is a
  maintenance utility, not a pipeline concern.
- Delete only orphaned .pyc files, not all caches, to avoid forcing unnecessary
  recompilation.
- Remove empty __pycache__/ dirs after cleanup for tidiness.
