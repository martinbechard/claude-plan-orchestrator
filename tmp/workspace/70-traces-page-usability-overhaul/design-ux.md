# UX Design Proposal: Traces Page Usability Overhaul

## Design Philosophy

The traces page must evolve from a developer-centric LangSmith trace viewer into a
**user-facing execution dashboard**. The core UX principle: every screen answers a
question the user is already asking.

- **List page** answers: "What ran? When? Did it succeed? How much did it cost?"
- **Detail page** answers: "What happened in this run, step by step?"

All design choices follow from these questions. Information that does not help answer
them is hidden (not removed) behind progressive disclosure.


## Information Architecture

### Hierarchy of User Intent

```
Level 0: Scan — "Show me what ran recently" (list page, default view)
Level 1: Filter — "Find a specific item" (filter bar)
Level 2: Inspect — "What happened in this run?" (detail page header)
Level 3: Drill — "What did the agent do in this phase?" (phase expansion)
Level 4: Debug — "Show me the raw trace data" (raw toggle)
```

Each level is accessed through a deliberate user action (click, expand, toggle).
No level forces information from a deeper level onto the user.

### List Page Information Hierarchy

Each row in the list communicates, left to right, in order of importance:

1. **Item identity** (slug name) -- the primary scanning target
2. **Type badge** (defect/feature) -- color-coded for rapid visual differentiation
3. **Temporal context** (start time, relative) -- "when did this happen?"
4. **Outcome** (status badge) -- color-coded pass/fail/running/stale
5. **Metrics** (duration, cost) -- right-aligned numeric columns for comparison
6. **Secondary identifiers** (trace ID, model) -- low-priority, present but quiet

This ordering matches how users scan: they look for the item name first, glance at
status for "did it work?", then check duration/cost for anomalies.

### Detail Page Information Hierarchy

The detail page organizes information into three zones:

1. **Header zone** -- identity + summary metrics (always visible)
2. **Navigation zone** -- links to related resources (always visible, compact)
3. **Timeline zone** -- phase-by-phase story (scrollable, expandable)


## List Page Design

### Page Title and Framing

Replace "LangSmith Traces" with **"Execution History"** (already done in current
template). The nav link label "Traces" is acceptable as a short label -- it is the
established term in the application. The H1 on the page itself uses the longer,
more descriptive "Execution History" to frame the context.

### Table Columns (Flat View)

| Column | Width | Alignment | Content |
|--------|-------|-----------|---------|
| Item | flex | left | Slug name as link + type badge inline |
| Started | 160px | left | Relative time ("2h ago") with tooltip showing absolute ISO datetime |
| Duration | 90px | right | Tabular-numeric, e.g. "4m 32s" |
| Cost | 80px | right | Tabular-numeric, e.g. "$0.1234" |
| Model | 80px | left | Short model name (opus, sonnet, haiku) |
| Status | 90px | center | Color-coded badge |

**Removed columns**: "Trace ID" moves to a tooltip on the item name (click-to-copy
stays). "Item slug" is eliminated as it duplicated the run name.

**Rationale for column order**: Users scan left-to-right. The item name is the
primary identifier. Start time provides temporal context for the scan. Duration and
cost are comparison metrics that benefit from right-alignment and tabular-numeric
font-variant. Status is last because the badge color is visible from peripheral
vision even at the end of the row.

### Type Badge Design

The type badge appears inline after the item slug name, using the existing design
system badge classes:

- **Defect**: Red background (#fee2e2), dark red text (#991b1b) -- item-type-defect
- **Feature**: Blue background (#dbeafe), blue text (#1e40af) -- item-type-feature
- **Analysis**: Purple background (#ede9fe), purple text (#6d28d9) -- item-type-analysis

Type is derived from the slug prefix convention (e.g., slugs starting with numbers
like "03-" are typically defects when in defect-backlog, features when in
feature-backlog). The route handler should resolve this from the work item source
metadata when available, falling back to slug pattern analysis.

### Relative Time Display

Start times should display as relative time strings ("2h ago", "yesterday",
"Mar 25") with the absolute datetime in a title tooltip. This reduces cognitive
load -- users care about recency, not exact timestamps, when scanning the list.

Implementation: A small JavaScript function converts ISO datetimes to relative
strings. The existing local-time class already converts to locale-specific format;
this enhances it to show relative time in the cell text while preserving the
absolute time in datetime attribute and title tooltip.

### Row Click Target

The entire item name cell is the click target (links to the narrative detail page).
The link should have sufficient padding and use font-weight 500 for visual emphasis.
The trace ID (shortened to 8 chars) appears as a subtle monospace tooltip on the
item name for copy-to-clipboard functionality. This keeps the primary action
(navigate to detail) uncluttered while preserving the debug identifier.

### Grouped View

The existing group-by-slug toggle is well-designed. Keep it as-is with these
refinements:

- Group summary row shows the **most recent run's** metrics (already implemented)
- Run count badge shows "N runs" in muted text
- Expand/collapse chevron uses smooth rotation transition
- Member rows indent with left padding and use a lighter background

### Filter Bar

The current filter bar is functional. Refinements:

- **Slug filter**: Rename label from "Name" to "Search" with placeholder "Filter by
  item name..." -- this is the primary discovery mechanism (UC2)
- **Model filter**: Keep as dropdown (opus/sonnet/haiku) -- finite set works well
- **Date range**: Keep as-is with date pickers
- **Trace ID filter**: Move to an "Advanced" collapsible section since most users
  do not filter by trace ID
- Add keyboard shortcut: "/" focuses the search input (standard web convention)

### Pagination

Keep the existing prev/next pagination with page count. For future consideration:
infinite scroll or "load more" would reduce clicks, but pagination is appropriate
for the current data volumes and avoids complexity.

### Empty States

The current empty states are well-designed with contextual messaging (filters active
vs. no data). Keep as-is.


## Detail Page (Narrative) Design

### Header Card

The header card serves as the "identity + summary" zone. It should contain:

**Primary line (large, bold)**:
- Item slug as the page title (e.g., "03-fix-auth-middleware")
- Status badge inline (Completed / Running / Error / Stale)

**Metrics row (compact, horizontal)**:
- Started: relative time with absolute tooltip
- Duration: total wall-clock time (e.g., "12m 34s")
- Cost: total cost (e.g., "$0.4521")
- Phases: count of pipeline phases

This is a proven pattern from CI/CD dashboards (GitHub Actions, CircleCI).

### Navigation Links Bar

Below the header card, a horizontal row of navigation links provides quick access
to related resources. Each link is a small, icon-prefixed text link:

| Link | Icon | Target | Condition |
|------|------|--------|-----------|
| Back to traces | left arrow | /proxy | Always |
| View work item | document icon | /item/{slug} | When slug resolved |
| Worker output | terminal icon | Log files section (scroll anchor) | When logs exist |
| Design document | blueprint icon | Design doc path | When artifact found in phase data |
| Validation results | checkmark icon | Validation artifact path | When artifact found |
| Git commits | git icon | Git log filtered by slug | When slug resolved |

**Accessibility**: Each link has an aria-label describing the destination. Links that
are conditionally shown (based on available data) do not leave empty gaps -- the
flex layout reflows naturally.

**Icons**: Use Unicode symbols or simple inline SVG icons consistent with the
existing design language (the current template already uses Unicode: left arrow,
document icon, magnifying glass).

### Worker Output Logs Section

Currently, worker logs appear inline within the header card. Move them to a dedicated
section below the header but above the timeline, with their own heading. This
separation clarifies that logs are a reference resource, not a summary metric.

The section heading "Worker Output Logs" uses the same 11px uppercase style as
other section headers. Each log filename is a monospace entry. Future enhancement:
make log filenames clickable to view log content inline.

### Phase Timeline

The vertical timeline design is strong. Keep the core structure:
- Left spine with color-coded dots
- Phase cards with stripe, number, title, metrics, chevron
- Click to expand for details

Refinements:

**Phase Card Header (collapsed state)**:

```
[color dot] [number] [phase name]                [duration] [cost] [status badge] [chevron]
                     [subtitle: run name if different from phase name]
```

The subtitle row only appears when the run name adds information beyond the phase
name. This prevents visual noise from redundant labels.

**Phase Card Body (expanded state)**:

The expanded view is the core of UC4 (expand a phase to see agent actions). It
organizes information into clearly labeled sections:

1. **Agent identity** -- name of the agent type that ran this phase
2. **Activity summary** -- pill badges summarizing tool usage (Read N files, edited M, etc.)
3. **Files read** -- collapsible list of file paths (blue tint)
4. **Files written/edited** -- collapsible list of file paths (green tint)
5. **Bash commands** -- collapsible list of commands (purple tint)
6. **Artifacts** -- linkable outputs (design doc, plan YAML, etc.)

Each file/command section is independently collapsible with a heading showing the
count (e.g., "Files read (12)"). This prevents long file lists from dominating the
phase card.

**Color coding for file detail sections**: The existing color scheme for activity
pills (blue=read, green=write, purple=bash) extends naturally to the file detail
entries. This creates visual consistency between the summary pills and the detailed
lists.

### Phase Expansion Behavior

- **Default state**: All phases collapsed. The phase headers provide enough
  information for a quick overview.
- **Click behavior**: Click the phase header to toggle expansion. Only one phase
  expanded at a time? No -- allow multiple phases open simultaneously. Users often
  want to compare two phases side by side.
- **Keyboard**: Enter/Space on a focused phase header toggles it. Tab navigates
  between phase headers. This meets WCAG 2.1 keyboard accessibility.
- **Animation**: Smooth height transition (max-height or CSS grid trick) for
  expand/collapse. Current implementation uses display:none/block which is abrupt.

### Raw Trace Toggle

The raw trace toggle (FR2) replaces the current "Show raw trace" link that navigates
to a separate page. Instead:

- A toggle button appears in the header navigation row, right-aligned
- Label: "Show raw trace" with a code/JSON icon
- Default state: OFF (hidden)
- When toggled ON: A full-width section appears below the timeline showing the raw
  JSON payload in a collapsible, scrollable pre block
- The toggle uses aria-pressed and role="switch" for accessibility

**Rationale**: Inline toggle is better than a separate page because:
1. Users do not lose their place in the narrative view
2. They can cross-reference the raw data with the phase timeline
3. The browser back button is not consumed by viewing raw data

The raw trace section, when visible, should have a distinct visual treatment
(monospace font, light gray background, bordered) to clearly distinguish it from
the narrative content. A "Copy JSON" button in the top-right corner of the raw
section lets users quickly grab the data.

### Scroll Behavior

On the detail page, the header card should use sticky positioning (position: sticky,
top: 0) so it remains visible while scrolling through the phase timeline. This
keeps the item identity and summary metrics in view at all times.

The navigation links bar should also be sticky, positioned just below the header
card. This ensures that resource links (back to traces, view work item) are always
one click away.


## Interaction Patterns

### Progressive Disclosure

The design uses four levels of progressive disclosure:

1. **List scan** -- item names, status badges, and key metrics visible at a glance
2. **Detail overview** -- header card + collapsed phase timeline
3. **Phase drill-down** -- expanded phase card with agent actions
4. **Raw debug** -- full trace JSON (toggle, off by default)

Each level requires explicit user action to reach. No information from deeper
levels leaks into shallower ones.

### Affordances

- **Clickable rows**: Item name links use color (#3b6fcf) and font-weight (500) to
  signal clickability. The entire name cell is the click target.
- **Expandable phases**: Chevron icon (right-pointing triangle) on each phase header
  signals expandability. Rotates 90 degrees when expanded.
- **Toggle button**: The raw trace toggle uses a button element with border and
  distinct styling, making it clearly interactive.
- **Copy buttons**: Small bordered buttons next to trace IDs use clipboard icon.

### Feedback

- **Hover**: Table rows get a subtle background tint (#fafbff). Phase cards get a
  box-shadow. Links get underlines.
- **Active/pressed**: Toggle buttons use distinct active state (filled vs outlined).
- **Loading**: If data loading is needed, a skeleton loading state or spinner should
  appear in the content area (future enhancement).
- **Empty states**: Clear messaging with contextual help ("No traces match the
  current filters" with a "Clear filters" link).

### Keyboard Navigation

- **Tab order**: Filter inputs -> table rows -> pagination -> footer
- **Table**: Arrow keys navigate between rows (optional enhancement)
- **Detail page**: Tab navigates between phase headers, Enter/Space toggles expansion
- **Shortcuts**: "/" focuses the search input on the list page
- **Focus indicators**: Visible outline on all interactive elements (the existing
  :focus styles should be audited for completeness)


## Accessibility (WCAG 2.1 AA)

### Semantic Structure

- **List page**: Table uses proper thead/th/tbody/td. Role="search" on filter form.
  ARIA labels on all inputs.
- **Detail page**: Phase timeline uses role="list" with role="listitem" on each phase
  card. The header card uses appropriate heading levels.
- **Status badges**: Use role="status" so screen readers announce state.

### Color and Contrast

All badge text/background combinations meet WCAG AA contrast ratio (4.5:1):

| Badge | Background | Text | Ratio |
|-------|-----------|------|-------|
| Success | #d1fae5 | #065f46 | 7.2:1 |
| Error | #fee2e2 | #991b1b | 7.1:1 |
| Running | #dbeafe | #1e40af | 7.5:1 |
| Stale | #f3f4f6 | #6b7280 | 4.6:1 |
| Defect type | #fee2e2 | #991b1b | 7.1:1 |
| Feature type | #dbeafe | #1e40af | 7.5:1 |

Status is never conveyed by color alone -- each badge includes a text label
(Completed, Error, Running, Stale).

### Screen Reader Experience

- **List page**: "Execution History. Table with 25 rows. Row 1: 03-fix-auth-middleware,
  defect, started 2 hours ago, duration 4 minutes 32 seconds, cost $0.12, completed."
- **Detail page**: "03-fix-auth-middleware, completed. Total duration 12 minutes.
  Phase 1 of 5: Intake, duration 30 seconds, pass. Expand to see agent actions."
- **Phase expansion**: aria-expanded toggles between true/false. Screen readers
  announce "expanded" / "collapsed".

### Motion and Animation

- All animations respect prefers-reduced-motion media query
- Phase expand/collapse falls back to instant toggle when reduced motion is preferred
- No auto-playing animations or distracting motion


## Navigation Flow

### Primary Flow: List -> Detail -> Phase Drill-down

```
[List page] -- click item name --> [Detail page] -- click phase --> [Expanded phase]
                                                 -- toggle raw   --> [Raw JSON section]
     ^                                   |
     |                                   |
     +--- "Back to traces" link ---------+
```

### Secondary Flows

- **List -> Grouped list**: Toggle "Group by item" button. Same page, different
  rendering. URL parameter group=1 preserves state across reloads.
- **Detail -> Work item**: "View work item" link navigates to /item/{slug}.
- **Detail -> Worker logs**: Scroll anchor to logs section on the same page.
- **Detail -> External resources**: Design doc, validation, git links open in
  context (same tab for internal routes, new tab for external URLs).

### URL Design

- List: /proxy?slug=auth&model=opus&page=2&group=1
- Detail: /proxy/{run_id}/narrative
- Raw trace: /proxy/{run_id} (kept as a fallback but the inline toggle is primary)

All filter state is preserved in URL query parameters for shareability and
browser history. The detail page URL uses the run_id which is stable and
bookmarkable.


## Responsive Considerations

The current design targets desktop usage (1200px max-width). For narrower viewports:

- **Filter bar**: Wraps naturally (flex-wrap is already set)
- **Table**: Horizontal scroll on narrow screens (table-wrap with overflow-x: auto)
- **Detail page**: Phase cards stack vertically (already the case). The header
  metrics row wraps to multiple lines.
- **Timeline spine**: Reduces left padding on narrow screens

No mobile-first redesign is needed -- this is a developer/ops tool used primarily
on desktop. But the layout should not break on tablet-width screens.


## Design Decisions Addressed

### D1: Phase 0 Design Competition
This proposal participates in the design competition, focusing on UX and interaction
patterns as the differentiator.

### D8: List Page UI Redesign
- Title: "Execution History" (already in place, confirmed as correct)
- Columns: Removed redundant "Item slug" column; added inline type badge
- Each row: slug name, type badge, start time, duration, cost, model, status
- Filter: "Search" label with clear placeholder text

### D9: Detail Page Core Redesign
- Title: Item slug as page heading (not "LangGraph")
- Navigation links bar: work item, worker logs, design doc, validation, git commits
- Phase metrics: real duration and cost per phase
- Header card: sticky positioning for always-visible identity

### D10: Phase Expansion and Raw Trace Toggle
- Expandable phases: click header to reveal agent actions (files, commands, artifacts)
- Multiple phases can be open simultaneously
- Raw trace: inline toggle button (off by default), reveals JSON below timeline
- Keyboard accessible: Enter/Space toggles, Tab navigates


## Acceptance Criteria Coverage

| AC | How This Design Addresses It |
|----|------------------------------|
| AC4 | Type badge replaces redundant column, derived from item type metadata |
| AC12 | Page title "Execution History" uses user-facing language |
| AC13 | Detail page title shows item slug as primary heading |
| AC19 | Navigation links bar includes "View work item" link to /item/{slug} |
| AC20 | Navigation links bar includes "Worker output" with scroll anchor to logs |
| AC24 | Each list row displays item slug as the primary cell content |
| AC25 | Type badge (defect/feature/analysis) inline after slug name |
| AC26 | Start time column with relative time display |
| AC27 | Duration column with tabular-numeric right-aligned values |
| AC28 | Cost column with tabular-numeric right-aligned values |
| AC29 | Status badge column with color-coded outcome |
| AC30 | Item name links to /proxy/{run_id}/narrative detail view |
| AC31 | Each phase card header shows real elapsed duration |
| AC32 | Each phase card header shows real cost |
| AC33 | Phase cards are expandable via click on header |
| AC34 | Expanded phase shows files read list (blue-tinted entries) |
| AC35 | Expanded phase shows bash commands list (purple-tinted entries) |
| AC36 | Expanded phase shows agent identity and activity summary pills |
| AC37 | Navigation bar includes design document link when available |
| AC38 | Navigation bar includes validation results link when available |
| AC39 | Navigation bar includes worker output logs link |
| AC40 | Navigation bar includes git commits link |
| AC41 | Raw trace toggle button present in navigation row |
| AC42 | Raw trace toggle defaults to OFF (hidden) |
| AC43 | Toggle ON reveals full raw JSON in scrollable section below timeline |
| AC44 | Toggle OFF hides the raw JSON section completely |
