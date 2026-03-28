# Design: Replace fragile build command with project-wide syntax check

## Problem

The build_command in .claude/orchestrator-config.yaml hardcodes specific file
paths in a py_compile list comprehension. When files are deleted or renamed,
the build command fails because it references non-existent paths. This is
fragile and requires manual maintenance.

Current command:
```
python3 -c "import os, py_compile; [py_compile.compile(f, doraise=True) for f in ['scripts/auto-pipeline.py'] if os.path.isfile(f)]"
```

## Solution

Replace with Python compileall module which recursively compiles all .py files
in specified directories. This auto-discovers files and never breaks when files
are added or removed.

New command:
```
python3 -m compileall -q langgraph_pipeline/ scripts/ tests/
```

The compileall module:
- Recursively finds all .py files in the given directories
- Compiles each one to check for syntax errors
- Returns non-zero exit code if any file has a syntax error
- The -q flag suppresses per-file output (only errors shown)

## Files to modify

- .claude/orchestrator-config.yaml (line 12): Replace build_command value

## Design decisions

1. Use compileall over manual py_compile: compileall handles recursive directory
   walking automatically, no custom code needed.

2. Include langgraph_pipeline/, scripts/, and tests/: These are the three
   directories containing project Python files. Covering all three ensures
   complete syntax validation.

3. Single-line command: Keeps the YAML config simple and readable.
