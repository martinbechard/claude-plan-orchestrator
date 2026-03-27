# Design: Work Item Page Missing Requirements from Backlog File (Validation)

## Status

Previously implemented. This plan validates the existing implementation against
acceptance criteria and fixes any gaps found.

## Architecture Overview

The /item/<slug> page is served by FastAPI route handler in
langgraph_pipeline/web/routes/item.py. Requirements display uses a priority chain:

1. Design doc -- docs/plans/*-<slug>-design.md (glob, most-recent match)
2. Claimed -- tmp/plans/.claimed/<slug>.md
3. Active backlog -- docs/defect-backlog/, docs/feature-backlog/, docs/analysis-backlog/
4. Completed backlog -- docs/completed-backlog/**/<slug>.md
5. "No requirements document found" if none exist

When a design doc is primary, an "Original request" details/summary block shows
the raw backlog file content.

## Key Files

| File | Role |
|------|------|
| langgraph_pipeline/web/routes/item.py | Route handler, _find_requirements_file(), _find_original_request_file(), _load_requirements_html() |
| langgraph_pipeline/web/templates/item.html | Template with requirements card and original-request disclosure |
| langgraph_pipeline/shared/paths.py | BACKLOG_DIRS, COMPLETED_DIRS, CLAIMED_DIR constants |

## Design Decisions

- Existing implementation covers all four fallback tiers plus the "Original request"
  disclosure when a design doc is the primary source.
- The validator agent will check the three acceptance criteria from the backlog item
  by inspecting code paths and verifying rendered output logic.
- If any criterion fails, the coder agent will fix the specific gap rather than
  rewriting the entire feature.
