# Structured Requirements: 01 Instead Of Completions We Should Use Work Item As The Title In The Ui And The E

Source: tmp/plans/.claimed/01-instead-of-completions-we-should-use-work-item-as-the-title-in-the-ui-and-the-e.md
Generated: 2026-04-02T23:50:07.975187+00:00

## Requirements

### P1: Misleading "Completions" terminology does not reflect full work item lifecycle
Type: UI
Priority: medium
Source clauses: [C2, C3]
Description: The current label "Completions" only describes finished runs, but the entity it represents spans the full lifecycle — queued, in-progress, failed, and completed. The name originated when the feature was built solely to show finished pipeline runs, and it was never updated as the feature grew to encompass all work item states and details. This creates a semantic mismatch between the UI label and the actual scope of the data shown.
Acceptance Criteria:
- Does the term "Completions" appear anywhere in user-facing UI labels (nav menu, page titles, headings)? YES = fail, NO = pass
- Does the replacement term "Work Items" / "Work Item" accurately represent the full lifecycle (queued, in-progress, failed, completed)? YES = pass, NO = fail

### P2: User confusion from encountering active and failed items under "Completions"
Type: UI
Priority: medium
Source clauses: [C4, C5]
Description: Users see "Completions" in the nav menu and expect only finished items. They experience confusion when they find active and failed items listed there. This is compounded by the fact that detail pages already call things "work items," creating an inconsistent experience where the list page uses one term and the detail pages use another.
Acceptance Criteria:
- Does the nav menu entry match the terminology used on detail pages? YES = pass, NO = fail
- Is there any UI path where the user sees "Completions" for a collection that includes non-completed items? YES = fail, NO = pass

### P3: Inconsistent domain terminology across UI, database, and code
Type: refactoring
Priority: medium
Source clauses: [C6, C7]
Description: Developers organically adopted "work item" as the more accurate term in routes, comments, and documentation, but never went back to update the original UI labels and database table name. There was no deliberate domain-language alignment effort, so the mismatch accumulated as incremental features were added without revisiting the foundational naming. The system now has two competing terms for the same concept.
Acceptance Criteria:
- Is "work item" (or "work_item" / "work_items") used consistently across UI labels, database table names, route paths, route modules, comments, and documentation? YES = pass, NO = fail
- Does the term "completions" remain in any non-legacy, non-migration context? YES = fail, NO = pass

### FR1: Rename nav menu link from "Completions" to "Work Items" in base.html
Type: UI
Priority: high
Source clauses: [C1, C8, C9]
Description: The nav menu link in base.html currently reads "Completions." It must be renamed to "Work Items" to establish the ubiquitous domain term and eliminate the legacy label. This is part of the broader goal to align the UI with the "work item" terminology already used in route modules, comments, and documentation.
Acceptance Criteria:
- Does the nav menu in base.html display "Work Items" instead of "Completions"? YES = pass, NO = fail

### FR2: Rename page title and heading from "Completions" to "Work Items" in completions.html
Type: UI
Priority: high
Source clauses: [C1, C8, C9]
Description: The page title and heading in completions.html currently reference "Completions." Both must be updated to "Work Items" to create consistent domain language with the nav menu and detail pages.
Acceptance Criteria:
- Does the page title (browser tab) display "Work Items" instead of "Completions"? YES = pass, NO = fail
- Does the page heading (H1 or equivalent) display "Work Items" instead of "Completions"? YES = pass, NO = fail

### FR3: Rename the /completions route path to /work-items
Type: refactoring
Priority: high
Source clauses: [C1, C8, C9, C10]
Description: The route path /completions must be renamed to /work-items (or equivalent work-item-based path) to align the URL structure with the ubiquitous domain term. All internal links, redirects, and references to the old route must be updated accordingly. This aligns the persistence and routing layer with the "work item" terminology already used in route modules, comments, and documentation.
Acceptance Criteria:
- Does the application serve the list page at a work-item-based route (e.g., /work-items) instead of /completions? YES = pass, NO = fail
- Do all internal links and redirects point to the new route path? YES = pass, NO = fail
- Does navigating to the old /completions path either redirect to the new path or no longer resolve? YES = pass, NO = fail

### FR4: Rename the completions database table to work_items
Type: refactoring
Priority: high
Source clauses: [C1, C8, C9, C10]
Description: The database table currently named "completions" must be renamed to "work_items" to align the persistence layer with the ubiquitous domain term. All queries, ORM models, and references to the old table name must be updated. This establishes "work item" as the single consistent term across UI, database, and code.
Acceptance Criteria:
- Does a database table named "work_items" exist and contain the data previously in "completions"? YES = pass, NO = fail
- Does the old "completions" table no longer exist (or is it replaced by the renamed table)? YES = pass, NO = fail
- Do all ORM models, queries, and data access code reference "work_items" instead of "completions"? YES = pass, NO = fail

### FR5: Establish "Work Item" as the single ubiquitous domain term across the entire application
Type: refactoring
Priority: medium
Source clauses: [C8, C10]
Description: Beyond the specific UI, route, and database changes, the system must be audited to ensure "Work Item" is used consistently as the single domain term across the entire application — including any remaining references in code comments, documentation, variable names, and module names that still use the legacy "completions" term in a domain-label context. This creates consistent domain language across the entire application.
Acceptance Criteria:
- Are all user-facing references to the entity consistent in using "Work Item" / "Work Items"? YES = pass, NO = fail
- Are code-level identifiers (variables, classes, modules) aligned to use work_item / work_items naming? YES = pass, NO = fail
- Is there a single, unambiguous term used across UI, database, routes, and documentation for this entity? YES = pass, NO = fail

---

## Coverage Matrix

| Raw Input Section | Requirement(s) |
|---|---|
| Title: Rename "Completions" to "Work Items" across UI and database | FR1, FR2, FR3, FR4, FR5 |
| Why 1: "Completions" only describes finished runs, full lifecycle is misleading | P1 |
| Why 2: feature originally built for finished runs, name stuck | P1 |
| Why 3: users expect only finished items, confusion with active/failed | P2 |
| Why 4: developers adopted "work item" organically, never updated UI/DB | P3 |
| Why 5: no deliberate domain-language alignment effort | P3 |
| Root Need: establish single ubiquitous domain term | FR5 |
| Description: nav menu link in base.html | FR1 |
| Description: page title/heading in completions.html | FR2 |
| Description: /completions route path | FR3 |
| Description: completions database table | FR4 |
| Description: aligns UI and persistence layer with existing terminology | FR3, FR4, FR5 |
| Detail pages already call things "work items" | P2 |

## Clause Coverage Grid

| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [GOAL] | GOAL | FR1, FR2, FR3, FR4 | Mapped |
| C2 [PROB] | PROB | P1 | Mapped |
| C3 [CTX] | CTX | P1 | Mapped — provides causal context for why the name is misleading |
| C4 [PROB] | PROB | P2 | Mapped |
| C5 [FACT] | FACT | P2 | Mapped — detail pages using "work items" evidences the inconsistency |
| C6 [FACT] | FACT | P3 | Mapped — documents the organic terminology drift |
| C7 [CTX] | CTX | P3 | Mapped — explains why the inconsistency was never addressed |
| C8 [GOAL] | GOAL | FR5 | Mapped |
| C9 [GOAL] | GOAL | FR1, FR2, FR3, FR4 | Mapped — each specific rename target is a separate FR |
| C10 [GOAL] | GOAL | FR3, FR4, FR5 | Mapped — alignment goal addressed by route, DB, and audit requirements |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT
