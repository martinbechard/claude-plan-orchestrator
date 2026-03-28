# Design: Work Item Page Missing Requirements from Backlog File

## Problem

The `/item/<slug>` requirements section shows "No requirements document found" for items
whose backlog file has been moved to `.claude/plans/.claimed/`. The route's
`_find_requirements_file` searches only `BACKLOG_DIRS` and `COMPLETED_DIRS` — it never
checks `.claimed/`, and it never checks for a design doc in `docs/plans/`.

## Root Cause

`langgraph_pipeline/web/routes/item.py` — `_find_requirements_file(slug)`:

- Searches: `docs/defect-backlog/`, `docs/feature-backlog/`, `docs/analysis-backlog/`,
  and the three `docs/completed-backlog/` subdirs.
- Missing: `.claude/plans/.claimed/` and `docs/plans/*-<slug>-design.md`.

## Expected Priority Order (from backlog item)

1. Design doc — `docs/plans/*-<slug>-design.md` (glob, most-recent match)
2. Claimed — `.claude/plans/.claimed/<slug>.md`
3. Active backlog — `docs/defect-backlog/`, `docs/feature-backlog/`, `docs/analysis-backlog/`
4. Completed backlog — `docs/completed-backlog/**/<slug>.md`
5. "No requirements document found" if none of the above exist

When a design doc is shown (case 1), the card header must also display an
"Original request" disclosure link that expands or navigates to the raw backlog `.md`
source so the user can see the original requirements.

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/web/routes/item.py` | Rewrite `_find_requirements_file` and `_load_requirements_html` to implement the priority chain; add `_find_original_request_file`; pass `original_request_html` to template |
| `langgraph_pipeline/web/templates/item.html` | When `original_request_html` is set, render a `<details>` / `<summary>` "Original request" block inside the Requirements card header area |

## Design Decisions

- `_find_requirements_file` returns the primary content path (highest priority found).
- A new `_find_original_request_file(slug)` returns the backlog/claimed path when the
  primary source is a design doc; `None` otherwise.
- Both paths are rendered to HTML independently and passed to the template as
  `requirements_html` (primary) and `original_request_html` (secondary, may be `None`).
- The template wraps `original_request_html` in a `<details>` element so it is
  collapsed by default and does not clutter the view.
- No change to `_detect_item_type`, `_derive_status`, or any other helpers.
