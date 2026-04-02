# Design: Rename "Completions" to "Work Items" Across UI and Database

Source: tmp/plans/.claimed/01-instead-of-completions-we-should-use-work-item-as-the-title-in-the-ui-and-the-e.md
Requirements: docs/plans/2026-04-02-01-instead-of-completions-we-should-use-work-item-as-the-title-in-the-ui-and-the-e-requirements.md

## Architecture Overview

This is a domain-language alignment refactoring that renames the legacy "completions"
terminology to "work items" across every application layer: HTML templates, route
definitions, database schema, Python modules, data classes, and tests.

The change touches four layers:
1. **UI layer** -- template text, nav links, page headings
2. **Routing layer** -- URL path and internal link references
3. **Persistence layer** -- SQLite table name, indexes, queries
4. **Code layer** -- Python module names, class/function names, variable names, comments, documentation

SQLite supports ALTER TABLE ... RENAME TO which preserves all data and indexes.
The rename is atomic within a single DDL statement.

## Key Files to Create/Modify

### Files to rename:
- langgraph_pipeline/web/routes/completions.py -> langgraph_pipeline/web/routes/work_items.py
- langgraph_pipeline/web/completion_grouping.py -> langgraph_pipeline/web/work_item_grouping.py
- langgraph_pipeline/web/templates/completions.html -> langgraph_pipeline/web/templates/work_items.html
- tests/langgraph/web/test_completion_grouping.py -> tests/langgraph/web/test_work_item_grouping.py

### Files to modify:
- langgraph_pipeline/web/templates/base.html -- nav link text and href
- langgraph_pipeline/web/server.py -- router import and registration
- langgraph_pipeline/web/proxy.py -- table DDL, indexes, all queries, method names
- langgraph_pipeline/web/dashboard_state.py -- CompletionRecord dataclass rename
- langgraph_pipeline/supervisor.py -- record_completion calls
- langgraph_pipeline/web/templates/dashboard.html -- completion references
- langgraph_pipeline/web/templates/item.html -- any completion references
- langgraph_pipeline/web/templates/analysis.html -- any completion references

## Design Decisions

### D1: Rename UI labels from "Completions" to "Work Items"
- **Addresses:** P1, P2, FR1, FR2
- **Satisfies:** AC1, AC2, AC3, AC4, AC5, AC6, AC7
- **Approach:** In base.html, change the nav link text from "Completions" to "Work Items"
  and update the href from "/completions" to "/work-items". The active-page detection
  must also match the new path. Rename completions.html to work_items.html and update
  the page title block and visible heading to "Work Items". Update the template_name
  reference in the route handler. This resolves the nav/list vs detail page inconsistency.
- **Files:** base.html, completions.html (renamed to work_items.html)

### D2: Rename route path from /completions to /work-items with redirect
- **Addresses:** FR3
- **Satisfies:** AC8, AC9, AC10
- **Approach:** Rename completions.py to work_items.py. Change the route decorator from
  @router.get("/completions") to @router.get("/work-items"). Add a permanent redirect
  (HTTP 301) from /completions to /work-items to preserve any bookmarks. Update all
  internal links in templates and server.py imports. The redirect preserves query
  parameters by forwarding the full query string.
- **Files:** completions.py (renamed to work_items.py), server.py, all templates

### D3: Rename database table from completions to work_items
- **Addresses:** FR4
- **Satisfies:** AC11, AC12, AC13
- **Approach:** Add an ALTER TABLE completions RENAME TO work_items statement in the
  schema initialization, executed after the CREATE TABLE IF NOT EXISTS (which still
  uses the new name work_items). For fresh databases, the table is created as
  work_items directly. For existing databases, the migration renames the table.
  The migration is idempotent: if work_items already exists, skip the rename.
  Update all SQL queries in proxy.py to reference work_items. Rename the unique
  index from idx_completions_slug_unique to idx_work_items_slug_unique.
- **Files:** proxy.py

### D4: Rename Python modules, classes, functions, and variables
- **Addresses:** FR5
- **Satisfies:** AC14, AC15
- **Approach:** Rename completion_grouping.py to work_item_grouping.py and update
  the function name from group_completions_by_slug to group_work_items_by_slug.
  Rename CompletionRecord dataclass to WorkItemRecord in dashboard_state.py.
  Rename proxy methods: record_completion -> record_work_item,
  list_completions -> list_work_items, list_completions_grouped -> list_work_items_grouped,
  count_completions -> count_work_items, sum_completions_cost -> sum_work_items_cost,
  _completions_filter -> _work_items_filter. Update all call sites in supervisor.py,
  routes, and templates. Rename test file accordingly. Update all code comments,
  log messages, and variable names that reference "completion(s)" in the work-item
  entity sense. Preserve "completion" references that genuinely refer to LLM
  completions (different domain concept).
- **Files:** completion_grouping.py (renamed), dashboard_state.py, proxy.py,
  supervisor.py, test_completion_grouping.py (renamed), all importing modules

### D5: Update documentation to use "work item" terminology
- **Addresses:** FR5
- **Satisfies:** AC16
- **Approach:** Search all documentation files (docs/, README, inline docstrings) for
  references to "completions" in the work-item entity context and update them to
  "work items". This includes any references in design documents, backlog items,
  and code docstrings. Preserve references to "completions" that genuinely mean
  LLM completions.
- **Files:** Any documentation files referencing the entity

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | Remove "Completions" from all UI labels (nav, title, heading) |
| AC2 | D1 | Replace all user-facing labels with "Work Item(s)" covering all lifecycle states |
| AC3 | D1 | Nav menu link text changed to "Work Items", matching detail page terminology |
| AC4 | D1 | List page and detail pages use consistent "Work Item(s)" terminology |
| AC5 | D1 | Nav menu in base.html displays "Work Items" as link text |
| AC6 | D1 | Page heading on list page reads "Work Items" |
| AC7 | D1 | Browser tab title on list page uses "Work Items" |
| AC8 | D2 | /work-items route serves the listing page |
| AC9 | D2 | All internal links and navigation elements point to /work-items |
| AC10 | D2 | /completions permanently redirects (301) to /work-items |
| AC11 | D3 | Database contains work_items table, no completions table |
| AC12 | D3 | All queries and ORM references use work_items table name |
| AC13 | D3 | ALTER TABLE RENAME TO preserves all data; idempotent migration |
| AC14 | D4 | Variable/function names using "completion(s)" renamed to "work_item(s)" |
| AC15 | D4 | Code comments referencing "completions" updated to "work item(s)" |
| AC16 | D5 | Documentation updated to use "work item" terminology consistently |
