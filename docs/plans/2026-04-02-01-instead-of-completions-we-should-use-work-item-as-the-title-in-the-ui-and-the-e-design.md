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


## Acceptance Criteria

**AC1**: Does the term "Completions" appear anywhere in user-facing UI labels (nav menu, page headings, browser tab titles) after the rename is complete? YES = fail, NO = pass
  Origin: Derived from C2 [PROB] (inverse — "name is misleading" → "misleading name no longer present")
  Belongs to: P1
  Source clauses: [C2, C3]

**AC2**: Does the replacement term "Work Items" / "Work Item" accurately describe entities across all lifecycle states (queued, in-progress, failed, completed)? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse — "only describes finished runs" → "describes all states")
  Belongs to: P1
  Source clauses: [C2]

**AC3**: Does the nav menu label match the terminology used on detail pages (both using "Work Item(s)")? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse — "users see Completions but detail says Work Item" → "terminology is consistent")
  Belongs to: P2
  Source clauses: [C4, C5]

**AC4**: Can a user navigate from the list page to a detail page without encountering a terminology change for this entity? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse — "confusion from inconsistent terms" → "no terminology change in journey")
  Belongs to: P2
  Source clauses: [C4, C5]

**AC5**: Does the nav menu in base.html display "Work Items" instead of "Completions"? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized — "rename the nav menu link" → verifiable check)
  Belongs to: FR1
  Source clauses: [C1, C8, C9]

**AC6**: Does the page heading on the list page display "Work Items" instead of "Completions"? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized — "rename page title/heading in completions.html")
  Belongs to: FR2
  Source clauses: [C1, C8, C9]

**AC7**: Does the browser tab title on the list page use "Work Items" instead of "Completions"? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized — "rename page title" includes the document title element)
  Belongs to: FR2
  Source clauses: [C1, C9]

**AC8**: Does the application serve the work items list page at a route using "work-items" (or equivalent work-item terminology) instead of "/completions"? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized — "rename the /completions route path")
  Belongs to: FR3
  Source clauses: [C1, C9, C10]

**AC9**: Do all internal links and navigation elements point to the new work-items route path instead of /completions? YES = pass, NO = fail
  Origin: Derived from C8 [GOAL] (operationalized — "single ubiquitous domain term" requires all references updated)
  Belongs to: FR3
  Source clauses: [C8, C9]

**AC10**: Does the old /completions path either redirect to the new path or return a 404 (i.e., it no longer serves the page at the old URL without indication of the change)? YES = pass, NO = fail
  Origin: Derived from C8 [GOAL] (operationalized — eliminating legacy path ensures no stale bookmarks silently work under the old name)
  Belongs to: FR3
  Source clauses: [C8, C9]

**AC11**: Is the database table named "work_items" (or equivalent work-item terminology) instead of "completions"? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized — "rename the completions database table")
  Belongs to: FR4
  Source clauses: [C1, C9, C10]

**AC12**: Do all queries, ORM models, and data access code reference the new table name instead of "completions"? YES = pass, NO = fail
  Origin: Derived from C8 [GOAL] (operationalized — "single ubiquitous domain term across UI, database, and code")
  Belongs to: FR4
  Source clauses: [C8, C10]

**AC13**: Does the application start and function correctly (pages load, data persists, queries execute) after the table rename? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized — rename must not break functionality)
  Belongs to: FR4
  Source clauses: [C9]

**AC14**: Are variable names and function names that used "completion(s)" (in the context of this entity) renamed to use "work_item(s)"? YES = pass, NO = fail
  Origin: Derived from C8 [GOAL] (operationalized — "single ubiquitous domain term across code")
  Belongs to: FR5
  Source clauses: [C6, C8, C10]

**AC15**: Are code comments that previously referenced "completions" (in the context of this entity) updated to say "work item(s)"? YES = pass, NO = fail
  Origin: Derived from C10 [GOAL] (operationalized — "aligns with work item terminology already used in comments")
  Belongs to: FR5
  Source clauses: [C6, C7, C10]

**AC16**: Is documentation updated to use "work item" terminology consistently, with no remaining references to "completions" for this entity? YES = pass, NO = fail
  Origin: Derived from C10 [GOAL] (operationalized — "terminology already used in documentation" must be made universal)
  Belongs to: FR5
  Source clauses: [C6, C8, C10]

---
