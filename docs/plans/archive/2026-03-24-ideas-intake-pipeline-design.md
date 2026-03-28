# Ideas Intake Pipeline - Design

## Status: Active

## Overview

Add support for a `docs/ideas/` folder where users can drop unformatted, rough
notes. The pipeline detects new files, spawns a Claude session to classify and
convert them into properly formatted backlog items, then moves the original to
`docs/ideas/processed/`.

This feature targets the LangGraph pipeline architecture (v1.8.x+). The ideas
processing step runs in the CLI scan loop, before the regular backlog pre-scan,
so no changes to the LangGraph graph topology are required.

## Architecture

### Integration point

The CLI's continuous scan loop in `langgraph_pipeline/cli.py` already handles
pre-scan scheduling and suspension management. Ideas processing slots in as a
new step at the top of each scan iteration:

```
while not shutdown_event.is_set():
    _reinstate_answered_suspensions()
    _post_pending_suspension_questions(slack)
    process_ideas(dry_run)     # <-- new
    pre_scanned = _pre_scan(budget_cap_usd)
    ...
```

This keeps the LangGraph graph topology (`scan_backlog → intake_analyze → ...`)
completely unchanged.

### New module

`langgraph_pipeline/pipeline/nodes/idea_classifier.py` contains all ideas
intake logic:

- `scan_ideas() -> list[str]` — finds unprocessed `.md` files in `IDEAS_DIR`
  (non-empty, not in `IDEAS_PROCESSED_DIR`, not dotfiles)
- `classify_idea(idea_path: str, dry_run: bool) -> bool` — spawns Claude with
  the intake prompt; verifies the original was moved to `processed/`; returns
  True on success
- `process_ideas(dry_run: bool) -> int` — calls `scan_ideas()` and
  `classify_idea()` in sequence; returns count of processed ideas

### Claude prompt

The prompt instructs Claude to:
1. Read the raw idea file
2. Determine type (feature / defect / multiple items) and priority
3. Write properly formatted backlog `.md` files with standard headers
   (`## Status: Open`, `## Priority:`, `## Summary:`, `## Scope:`,
   `## Files Affected:`)
4. Use `## Status: Needs Clarification` when the idea is too vague
5. Move the original idea file to `IDEAS_PROCESSED_DIR`
6. `git commit` with message `"intake: classify idea <filename>"`

The pipeline skips items with `Needs Clarification` status (handled by the
existing `scan_backlog` node which filters on status headers).

## Key files

| Change | File |
|--------|------|
| Add `IDEAS_DIR`, `IDEAS_PROCESSED_DIR` constants | `langgraph_pipeline/shared/paths.py` |
| New module with `scan_ideas`, `classify_idea`, `process_ideas` | `langgraph_pipeline/pipeline/nodes/idea_classifier.py` |
| Import and call `process_ideas()` in scan loop | `langgraph_pipeline/cli.py` |
| Unit tests | `tests/test_idea_classifier.py` |
| Version bump | `plugin.json`, `RELEASE-NOTES.md` |

## Design decisions

- **No graph changes**: Ideas processing happens in the CLI loop, not as a
  LangGraph node. This avoids changing the compiled graph and its checkpointer.
- **Lazy directory creation**: `ideas/processed/` is created on first use, like
  other directories in the codebase (no global `REQUIRED_DIRS` list needed).
- **Dry-run passthrough**: `classify_idea(dry_run=True)` logs what would happen
  and returns True without invoking Claude or moving files.
- **Rate-limit resilience**: On subprocess failure, `classify_idea` returns
  False; `process_ideas` counts it as not-processed so the file remains for
  the next cycle.
- **Prompt template**: Stored as a module-level constant `IDEA_INTAKE_PROMPT`
  with `{idea_path}`, `{feature_dir}`, `{defect_dir}`, `{processed_dir}` placeholders.
- **Claude invocation**: Uses `subprocess.run(["claude", "--dangerously-skip-permissions",
  "--print", prompt], ...)` matching the pattern in `intake.py`.
