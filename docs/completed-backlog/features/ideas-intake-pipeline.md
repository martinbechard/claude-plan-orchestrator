# Ideas Intake Pipeline

## Status: Open

## Priority: Low

## Summary

Add support for a `docs/ideas/` folder where users can drop unformatted, rough
notes about enhancements, defects, or design thoughts. The auto-pipeline would
detect new files in this folder, analyze them, and convert them into properly
formatted feature or defect backlog items in the appropriate folder.

## Current State

All backlog items must be written in the standard format (Status, Priority,
Summary, Scope, Files Affected, etc.) before the auto-pipeline will process them.
This creates friction when you just want to jot down a quick idea during a
conversation or debugging session.

## Proposed Changes

### 1. Monitor docs/ideas/ folder

Add `docs/ideas/` as a watched directory in `auto-pipeline.py`, alongside the
existing defect and feature backlog folders.

### 2. Intake processing phase

When a new file appears in `docs/ideas/`:

1. Read the raw content (free-form text, bullet points, conversation snippets, etc.)
2. Spawn a Claude session to analyze and classify the idea:
   - Is it a feature, defect, or multiple items?
   - What priority does it suggest?
   - What files/areas are likely affected?
3. Generate properly formatted backlog item(s) in the correct folder:
   - Features go to `docs/feature-backlog/`
   - Defects go to `docs/defect-backlog/`
4. Move the original idea file to `docs/ideas/processed/` so it isn't re-analyzed

### 3. Handling ambiguous ideas

If the analyzer cannot determine whether an idea is a feature or defect, or if
the idea is too vague to produce a useful backlog item, it should:

- Write a placeholder file with `## Status: Needs Clarification`
- Include what it understood and what questions remain
- Place it in the most likely backlog folder
- The auto-pipeline skips items with `Needs Clarification` status

## Files Affected

- Modified: `scripts/auto-pipeline.py` (add ideas folder watcher and intake phase)
- New: `docs/ideas/processed/` (archive for processed ideas)
