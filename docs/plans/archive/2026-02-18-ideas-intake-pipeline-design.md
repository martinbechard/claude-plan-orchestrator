# Ideas Intake Pipeline - Design Document

## Overview

Add support for a `docs/ideas/` folder where users can drop unformatted, rough
notes about enhancements, defects, or design thoughts. The auto-pipeline detects
new files in this folder, analyzes them via a Claude session, and converts them
into properly formatted feature or defect backlog items in the appropriate folder.

## Architecture

### Processing Flow

```
docs/ideas/*.md
    |
    v
auto-pipeline.py (intake scan)
    |
    v
Claude session (analyze + classify)
    |
    +---> docs/feature-backlog/<slug>.md   (feature items)
    +---> docs/defect-backlog/<slug>.md    (defect items)
    +---> docs/<type>-backlog/<slug>.md    (Status: Needs Clarification, if ambiguous)
    |
    v
docs/ideas/processed/<original-file>.md   (archived original)
```

### Key Design Decisions

1. **Intake runs before backlog scan**: In each pipeline cycle, ideas are processed
   first so newly generated backlog items are immediately available for the regular
   pipeline scan in the same cycle.

2. **One idea file may produce multiple backlog items**: The Claude session can
   split a single idea into separate feature and defect items if appropriate.

3. **Ambiguous ideas get "Needs Clarification" status**: The auto-pipeline already
   skips items without "Open" status, so these are naturally excluded from processing
   until a human reviews them.

4. **Processed originals are archived, not deleted**: Moved to `docs/ideas/processed/`
   for traceability. The processed folder is added to REQUIRED_DIRS.

5. **Intake uses the same Claude session pattern as plan creation**: Reuses
   `run_child_process()` and the CLAUDE_CMD infrastructure. A prompt template
   instructs the AI to read the idea file, classify it, and write formatted output.

6. **Filesystem watcher extended**: The BacklogWatcher is also set up for the
   `docs/ideas/` directory so new idea files trigger an immediate scan.

## Files Affected

### Modified

- `scripts/auto-pipeline.py`:
  - Add IDEAS_DIR, IDEAS_PROCESSED_DIR constants
  - Add both to REQUIRED_DIRS
  - Add IDEA_INTAKE_PROMPT_TEMPLATE
  - Add `scan_ideas()` function to find unprocessed .md files in docs/ideas/
  - Add `process_idea()` function to spawn Claude for classification
  - Add `intake_ideas()` orchestration function called from main_loop
  - Extend BacklogWatcher to also watch docs/ideas/
  - Call `intake_ideas()` at the top of each main_loop iteration

### New

- `docs/ideas/` - Directory for raw idea files (created by ensure_directories)
- `docs/ideas/processed/` - Archive for processed idea files

### Tests

- `tests/test_auto_pipeline.py` - Add tests for scan_ideas(), process_idea(),
  and the intake flow

## Prompt Template Design

The intake prompt instructs Claude to:

1. Read the raw idea file
2. Determine if it describes a feature, defect, or multiple items
3. Assess priority based on content signals
4. Generate properly formatted backlog item(s) with standard sections:
   - Status (Open or Needs Clarification)
   - Priority
   - Summary
   - Scope / Files Affected
5. Write each item to the correct backlog directory
6. If the idea is too vague, write a single item with Status: Needs Clarification
7. Git commit the new backlog items and the move of the original to processed/

## Edge Cases

- **Empty idea files**: Skipped silently (no Claude session spawned)
- **Binary or non-text files**: Only .md files are processed
- **Rate limiting during intake**: Returns False, idea stays in queue for next cycle
- **Idea already in processed/**: Skip (idempotent)
- **Multiple ideas in rapid succession**: Processed one at a time, sequentially
