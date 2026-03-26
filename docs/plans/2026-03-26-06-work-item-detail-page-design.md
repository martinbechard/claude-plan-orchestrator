# Work Item Detail Page — Design

Feature: 06-work-item-detail-page
Date: 2026-03-26

## Architecture Overview

Adds a `/item/<slug>` detail page to the embedded web server. The page aggregates
all information about a single work item: its markdown requirements, plan YAML
task list, completion history from the SQLite DB, and linked root traces.

Dashboard active-worker cards and recent-completions rows gain clickable slug
links that navigate to this page.

## Data Sources

| Section | Source |
|---|---|
| Requirements markdown | Scans `BACKLOG_DIRS` + `COMPLETED_DIRS` for `<slug>.md` |
| Plan task list | `.claude/plans/<slug>.yaml` (glob fallback: `<slug>*.yaml`) |
| Completion history | `completions` table — `SELECT * WHERE slug = ?` |
| Root traces | `traces` table — root runs whose `name` contains the slug |

## Key Files to Create

| File | Purpose |
|---|---|
| `langgraph_pipeline/web/routes/item.py` | GET /item/{slug} endpoint; data assembly |
| `langgraph_pipeline/web/templates/item.html` | Detail page template |

## Key Files to Modify

| File | Change |
|---|---|
| `langgraph_pipeline/web/proxy.py` | Add `list_completions_by_slug()` and `list_root_traces_by_slug()` query helpers |
| `langgraph_pipeline/web/server.py` | Register item router |
| `langgraph_pipeline/web/templates/dashboard.html` | Wrap slug text in `<a href="/item/{slug}">` in worker cards and completions JS |

## Route Design

```
GET /item/{slug}
```

Response: rendered `item.html` with template context:

```python
{
    "slug": str,
    "item_type": str | None,          # "feature" / "defect" / "analysis"
    "status": str,                    # "running" / "completed" / "queued" / "unknown"
    "total_cost_usd": float,          # sum across all completions
    "requirements_html": str,         # markdown rendered to HTML
    "plan_tasks": list[dict] | None,  # [{id, name, status}, ...] or None
    "completions": list[dict],        # from completions table
    "traces": list[dict],             # [{run_id, name, created_at}, ...]
}
```

## Layout

Two-column on wide screens (≥ 900 px):
- Left column: Requirements (full-width markdown render)
- Right column: Plan task list + Completion history + Traces

Single column on narrow screens (stacks top-to-bottom in same order).

## Design Decisions

- Markdown rendering via Python `markdown` library (already available via pip);
  sanitised output is injected as `{{ requirements_html | safe }}`.
- Plan YAML parsed with `yaml.safe_load`; task status mapped to checked/unchecked
  checkboxes. Sections are flattened to a single task list for display.
- Completion outcome rows use CSS classes `outcome-passed`, `outcome-failed`,
  `outcome-error` for colour coding, mirroring the dashboard pattern.
- Traces section shown as a simple table with links to `/proxy?trace_id=<run_id>`.
  If no traces found, a "No traces linked" placeholder is shown.
- The route never raises 404; unknown slugs render the page with empty sections
  and a "No data found" notice.
