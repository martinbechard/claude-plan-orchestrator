# Design: Fix Intake Single-Digit Prefix

## Problem

The Slack intake in `scripts/plan-orchestrator.py` creates backlog files with single-digit
prefixes (1-slug.md, 2-slug.md), but the scanner in
`langgraph_pipeline/pipeline/nodes/scan.py` uses `BACKLOG_SLUG_PATTERN = re.compile(r"^\d{2,}-[\w-]+$")`
which requires two or more digits. Intake-created files are silently ignored.

## Architecture

Two code paths create backlog files:

1. **Legacy path** - `scripts/plan-orchestrator.py:4523` - `_create_backlog_item()`
   uses `f"{next_num}-{slug}.md"` (NO zero-padding -- the bug)
2. **LangGraph path** - `langgraph_pipeline/slack/poller.py:735` - `_create_backlog_item()`
   uses `f"{next_num:02d}-{slug}.md"` (already correct)

The scanner at `langgraph_pipeline/pipeline/nodes/scan.py:40` requires `\d{2,}` prefix.

## Fix

Apply the preferred option (a) from the defect report: change the legacy intake
numbering to use `%02d` format.

### Files to Modify

- `scripts/plan-orchestrator.py` line 4523: change `f"{next_num}-{slug}.md"` to
  `f"{next_num:02d}-{slug}.md"`

### Files Already Correct (no changes needed)

- `langgraph_pipeline/slack/poller.py:735` - already uses `:02d`
- `langgraph_pipeline/pipeline/nodes/scan.py:40` - pattern is correct as-is

## Design Decisions

- **Option (a) chosen over (b)**: Zero-padding the prefix is preferred over relaxing the
  scanner regex because consistent two-digit prefixes sort correctly in file listings and
  match the existing LangGraph implementation.
- **Single file change**: Only `plan-orchestrator.py` needs the fix since `poller.py`
  already zero-pads correctly.
