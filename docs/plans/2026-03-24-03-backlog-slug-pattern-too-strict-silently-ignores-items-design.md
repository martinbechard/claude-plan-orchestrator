# Design: Backlog Slug Pattern Too Strict — Silently Ignores Items

## Work Item

docs/defect-backlog/03-backlog-slug-pattern-too-strict-silently-ignores-items.md

## Problem

`_scan_directory` in `langgraph_pipeline/pipeline/nodes/scan.py` uses
`BACKLOG_SLUG_PATTERN = re.compile(r"^\d{2,}-[\w-]+$")`, which requires two or more
leading digits. Any item file with a single-digit prefix (`9-foo.md`) or no digit
prefix at all (`cost-analysis.md`) is silently skipped — never logged, never processed.

## Architecture Overview

The fix is confined to a single file: `langgraph_pipeline/pipeline/nodes/scan.py`.

The `_scan_directory` helper filters candidate `.md` files using `BACKLOG_SLUG_PATTERN`
before checking status headers. The change relaxes this constant and replaces the silent
`continue` for non-matching files with a `logging.warning` so operators have a visible
signal when a file is present but cannot be processed.

## Design Decisions

### Regex relaxation

The new pattern is `r"^[\w][\w-]*$"` — any slug that starts with a word character
(letter, digit, or underscore) and contains only word characters and hyphens. This:

- Accepts `9-foo` (single-digit prefix)
- Accepts `cost-analysis` (prose slug, no number)
- Accepts `01-my-bug` (existing two-digit prefix, unchanged)
- Rejects `.hidden`, `has spaces`, or empty stems

Item type is already determined by which directory the file lives in, so the slug does
not need a numeric prefix to be unambiguous.

### Warning log for truly invalid files

`.md` files in a backlog directory that still fail the relaxed pattern (e.g. files with
spaces in their names) emit a `logging.warning` instead of being silently skipped. This
replaces the silent ignore with a visible signal.

### No changes to other callers

`BACKLOG_SLUG_PATTERN` is only referenced in `scan.py:82` — the `_scan_directory`
helper. No other module imports or uses this constant.

## Key Files

| File | Change |
|---|---|
| `langgraph_pipeline/pipeline/nodes/scan.py` | Relax `BACKLOG_SLUG_PATTERN`; add warning log in `_scan_directory` |
| `tests/langgraph/pipeline/nodes/test_scan.py` | Update slug-pattern tests to match new behavior |
