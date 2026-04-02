# UX Design Document: Step-Based Artifact Explorer Accordion

**Component:** step-explorer accordion
**Page:** Item detail (/item/{slug})
**Date:** 2026-04-02
**Agent:** ux-designer (task 0.2)

Source: tmp/plans/.claimed/74-item-page-step-explorer.md
Design overview: docs/plans/2026-04-02-74-item-page-step-explorer-design.md
Requirements: docs/plans/2026-04-02-74-item-page-step-explorer-requirements.md (mapped to task AC numbering)

---

## 1. Design Overview and Rationale

### Problem

The flat artifact layout exposes every file for every pipeline stage in one undifferentiated list. As the pipeline grows (6 stages, 10+ artifacts each), operators must scroll through dozens of entries to find the specific stage they care about. This creates cognitive overload and slows triage.

### Solution

A collapsible accordion organized by pipeline stage. Each stage is a discrete card with a header showing status at a glance. Stage bodies expand on demand. The operator sees the pipeline as a sequence of named phases, not a flat file dump.

### Why Accordion over Tabs or Tree

- **Accordion:** Supports showing multiple stages simultaneously (compare Planning vs Execution). Natural for ordered sequences. Collapse-all gives a dashboard summary view.
- **Tabs:** Force single-stage view; cannot compare across stages.
- **Tree:** Too nested; stages are flat (not recursive).

### Root Need Addressed

Operators need to jump directly to the in-progress stage, confirm what was produced, and dismiss stages they already reviewed -- all without losing context. The accordion with per-stage persistence (localStorage) satisfies this directly.

---

## 2. Visual Hierarchy Specification

The design establishes two clear tiers:

```
TIER 1 -- Stage Header (card-level, always visible)
  Font:    14px, font-weight 600, color #1a1a2e
  BG:      #f8fafc (matches existing card header pattern)
  Border:  bottom 1px solid #e2e8f0 (when expanded), transparent (when collapsed)
  Padding: 0.75rem 1rem

TIER 2 -- Artifact Item (row-level, visible when stage expanded)
  Font:    13px, font-weight 500, color #374151
  BG:      #ffffff (card body)
  Border:  bottom 1px solid #f0f4f8 (separates artifacts within stage)
  Padding: 0.5rem 1rem
```

Visual differentiation checklist:

| Property | Stage Header | Artifact Row |
|---|---|---|
| Font size | 14px | 13px |
| Font weight | 600 | 500 |
| Text color | #1a1a2e (dark) | #374151 (medium) |
| Background | #f8fafc (gray tint) | #ffffff (white) |
| Has badge | Yes | No |
| Has chevron | Yes | No |
| Clickable | Yes (full row) | No (content pre-expands) |

This ensures the eye reads stage headers as section titles and artifact rows as sub-items, satisfying **AC3**.

---

## 3. Stage Header Anatomy

### Flex Layout

```
[chevron][   stage name   (flex: 1)   ][badge][timestamp][count]
```

- **Direction:** flex-direction: row
- **Alignment:** align-items: center
- **Gap:** 0.5rem between elements
- **Padding:** 0.75rem 1rem
- **Min-height:** 44px (touch target)

### Element Specifications

**Chevron** (span.step-stage-chevron)
- Content: right-pointing triangle (Unicode 25B6)
- Size: 9px
- Color: #6b7280
- Transform: rotate(90deg) when stage is expanded (not collapsed)
- Transition: transform 0.15s ease
- Flex-shrink: 0

**Stage Name** (span.step-stage-name)
- Text: human-readable stage name (e.g., "Intake", "Planning")
- Font: 14px, weight 600, color #1a1a2e
- flex: 1 1 auto -- takes all available horizontal space
- Truncate with overflow: hidden; text-overflow: ellipsis; white-space: nowrap on mobile

**Status Badge** (span.badge.step-status-badge.step-status-{status})
- Renders as pill (existing .badge class handles border-radius)
- Font: 11px, uppercase, letter-spacing 0.04em
- Flex-shrink: 0
- See Section 7 for color mapping

**Completion Timestamp** (span.step-stage-ts)
- Shown only for done stages (**AC23, AC24**)
- Font: 11px, monospace (ui-monospace, SFMono-Regular, SF Mono, Consolas, monospace)
- Color: #6b7280
- Format: YYYY-MM-DD HH:MM
- Flex-shrink: 0
- Hidden when stage is not done (server-side: only rendered when completion_ts exists)

**Artifact Count** (span.step-stage-count)
- Content: e.g., "3 artifacts" or "0 artifacts"
- Font: 11px
- Color: #9ca3af
- Flex-shrink: 0

### Header Button

The entire header is a button element (not a div) for native keyboard access. It spans full card width with width: 100%, text-align: left, background: #f8fafc, border: none, cursor: pointer.

---

## 4. Artifact Item Anatomy

### Structure per Artifact

```
div.step-artifact
  div.step-artifact-meta
    span.step-artifact-name        -- file/artifact label
    span.step-artifact-ts          -- file timestamp (AC25, AC26)
  pre.step-artifact-content        -- lazy-loaded raw content (hidden until loaded)
```

### Element Specifications

**Artifact Meta Row** (div.step-artifact-meta)
- display: flex; align-items: baseline; gap: 0.75rem
- Padding: 0.5rem 1rem
- Border-bottom: 1px solid #f0f4f8

**Artifact Name** (span.step-artifact-name)
- Font: 13px, weight 500, color #374151
- The human-readable label for the artifact (e.g., "User Request", "Design Document")
- Note: "Raw Input" MUST be renamed to "User Request" everywhere (**AC29, AC30**)

**Artifact Timestamp** (span.step-artifact-ts)
- Font: 11px, monospace
- Color: #6b7280
- Value comes from file creation/modification time (**AC26**)
- Always shown when artifact exists (**AC25**)

**Content Area** (pre.step-artifact-content)
- Background: #1a1a2e (dark code block)
- Color: #e2e8f0 (light text on dark)
- Font: 11px monospace
- Padding: 0.75rem 1rem
- Max-height: 400px with overflow-y: auto
- White-space: pre
- data-artifact-path attribute carries the fetch URL
- Starts with hidden attribute; removed after content loads
- data-loaded attribute set to "true" after first successful fetch (prevents re-fetch)

**Loading State** (injected spinner, replaces content pre temporarily)

See Section 6 for loading state specification.

**Empty Stage** (div.step-empty)
- Shown when stage has no artifacts
- Font: 12px, italic, color #6b7280
- Padding: 1rem
- Text: "No artifacts yet."

---

## 5. Interaction Patterns

### Expand (Click Header)

1. User clicks button.step-stage-header (or presses Enter/Space)
2. JS removes .collapsed from div.step-stage
3. aria-expanded on button flips from "false" to "true"
4. .step-stage-body becomes visible (CSS: .collapsed .step-stage-body display: none)
5. Chevron rotates 90deg via CSS transition (0.15s ease)
6. Stage header border-bottom becomes 1px solid #e2e8f0
7. loadStageArtifacts() is called:
   - For each pre.step-artifact-content without data-loaded="true":
     - Insert spinner HTML into pre, remove hidden
     - Fetch /item/{slug}/artifact-content?path={path}
     - On success: replace spinner with content text, set data-loaded="true"
     - On error: replace spinner with error message
8. localStorage key step-explorer-{slug}-{stageId} is set to "expanded"

### Collapse (Click Header Again)

1. User clicks the expanded button.step-stage-header
2. JS adds .collapsed to div.step-stage
3. aria-expanded flips to "false"
4. .step-stage-body hides (display none)
5. Chevron rotates back (transform removed)
6. Border-bottom becomes transparent
7. localStorage key set to "collapsed"
8. Content already fetched is preserved in the DOM -- re-expand is instant

### Loading

- Each content area independently shows a spinner while its AJAX call is pending
- The stage header remains interactive during loading (can collapse mid-load)
- If collapsed during load, the fetch still completes (content cached for next expand)

### Cache Invalidation

- If the artifact count in the updated stage data (data-artifact-count) exceeds the cached count, data-loaded is cleared from all pre elements in that stage
- Next expand re-fetches all content

### Initial State on Page Load

- Stages with data-stage-status="in_progress" are expanded by default on first visit
- On subsequent visits, localStorage state takes precedence
- All other stages default to collapsed

### Live Polling

- window._stepExplorer.updateStages() is called on an interval
- Updates data-stage-status, badge text/class, timestamps, and data-artifact-count
- Does not collapse currently-expanded stages

---

## 6. State Specifications

### Stage States

| State | CSS class on .step-stage | Chevron | Border-bottom on header | Body visibility |
|---|---|---|---|---|
| Collapsed | .step-stage.collapsed | rotate(0deg) pointing right | transparent | display: none |
| Expanded | .step-stage (no .collapsed) | rotate(90deg) pointing down | 1px solid #e2e8f0 | block |

### Artifact Content States

| State | Visual | Implementation |
|---|---|---|
| **Not yet loaded** | Pre has hidden attribute | [hidden] on pre, no spinner yet |
| **Loading** | CSS spinner inside pre | Spinner HTML injected, hidden removed |
| **Loaded** | Raw text content in pre | data-loaded="true", text content set |
| **Error** | Red error message in pre | Error text with color #dc2626 |

### Loading Spinner Specification

Injected HTML while loading:

```
<span class="step-artifact-spinner" aria-label="Loading..."></span>
```

CSS:

```
.step-artifact-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid #374151;
  border-top-color: #3b6fcf;
  border-radius: 50%;
  animation: step-spin 0.6s linear infinite;
  margin: 0.5rem;
  vertical-align: middle;
}

@keyframes step-spin {
  to { transform: rotate(360deg); }
}
```

No external assets required (**AC28**).

### Error State

```
<span class="step-artifact-error">Failed to load. Click to retry.</span>
```

```
.step-artifact-error {
  color: #dc2626;
  font-size: 12px;
  padding: 0.5rem;
  cursor: pointer;
}
```

Clicking the error span re-triggers the fetch for that artifact.

---

## 7. Status Badge Design

All badges use the existing .badge class which provides:
- display: inline-flex; align-items: center
- padding: 2px 8px
- border-radius: 9999px (pill shape)
- font-size: 11px; font-weight: 500

### Badge States

| Status | Class | Background | Text Color | Label |
|---|---|---|---|---|
| Not started | .step-status-not_started | #f3f4f6 | #6b7280 | "not started" |
| In progress | .step-status-in_progress | #fef3c7 | #92400e | "in progress" |
| Done | .step-status-done | #d1fae5 | #065f46 | "done" |

These map directly to existing CSS classes in item.html -- no new CSS needed for the badge colors.

ARIA: each badge should have aria-label="Stage status: {label}" for screen reader clarity.

---

## 8. Responsive Behavior

### Desktop (at or above 900px)

The item page uses a two-column grid: 1fr 360px. The step explorer sits in the 1fr left column (main content area). It fills the full column width. Stage headers are wide enough to show all elements (chevron, name, badge, timestamp, count) on one row without wrapping.

### Mobile (below 900px)

Grid collapses to single column, full width. The step explorer fills the viewport width.

Header element behavior on narrow screens:

- span.step-stage-name: overflow: hidden; text-overflow: ellipsis; white-space: nowrap ensures long stage names truncate rather than wrap
- span.step-stage-ts: Can be hidden on very narrow screens via media query at max-width 480px -- timestamp still visible when expanded via artifact rows
- span.step-stage-count: Retained (short, numeric)
- pre.step-artifact-content: max-height 200px on mobile to preserve scroll context

No horizontal scroll on stage headers at any breakpoint.

### CSS Media Query

```
@media (max-width: 480px) {
  .step-stage-ts { display: none; }
  .step-artifact-content { max-height: 200px; }
}
```

---

## 9. Accessibility Specification

### Semantic Structure

- Each stage header is a button element -- native keyboard activation (Enter, Space), no JS needed for keyboard events beyond toggle logic
- aria-expanded="true|false" on each button, updated by JS on toggle
- aria-controls="step-body-{id}" links button to its controlled region
- Stage body: div with role="region" and aria-label="{Stage Name} stage artifacts"

### Keyboard Navigation

| Key | Behavior |
|---|---|
| Tab | Move focus to next stage header (or next focusable element) |
| Shift+Tab | Move focus to previous stage header |
| Enter or Space | Toggle expand/collapse on focused header |
| Tab (inside expanded body) | Move through artifact content areas |

### Focus Visible

Existing pattern reused:

```
.step-stage-header:focus-visible {
  outline: 2px solid #3b6fcf;
  outline-offset: -2px;
}
```

This matches the existing focus-visible pattern in item.html.

### ARIA Labels

- Chevron span: aria-hidden="true" (decorative)
- Status badge: aria-label="Stage status: {label}"
- Artifact count: aria-label="{n} artifacts in this stage"
- Loading spinner: aria-label="Loading..."
- Error span: role="alert" so screen readers announce the failure

### Color Contrast

All badge and text color combinations meet WCAG AA (4.5:1 minimum for text):
- #065f46 on #d1fae5: passes
- #92400e on #fef3c7: passes
- #6b7280 on #f3f4f6: passes (borderline; font-weight 500 helps)

---

## 10. CSS Class Naming Conventions

All classes use the .step- prefix, scoped to the step explorer component.

### Complete Class Inventory

| Class | Element | Purpose |
|---|---|---|
| .step-explorer | Container div | Flex column, gap 0.75rem, wraps all stages |
| .step-stage | Stage card div | White card, border, radius; has .collapsed modifier |
| .step-stage.collapsed | Stage card (collapsed) | Body hidden, header border-bottom transparent |
| .step-stage-header | Button | Full-width button, flex row, card header styles |
| .step-stage-header:hover | Button (hover) | Background #f0f4f8 |
| .step-stage-header:focus-visible | Button (focus) | Blue outline |
| .step-stage-chevron | Span in button | Triangle icon, rotates on expand |
| .step-stage-name | Span in button | Stage display name, flex: 1 |
| .step-status-badge | Span in button | Status pill, pairs with .badge |
| .step-status-not_started | Modifier on badge | Gray colors |
| .step-status-in_progress | Modifier on badge | Yellow colors |
| .step-status-done | Modifier on badge | Green colors |
| .step-stage-ts | Span in button | Completion timestamp, done stages only |
| .step-stage-count | Span in button | Artifact count, muted |
| .step-stage-body | Div (collapsible region) | Contains artifact rows |
| .step-artifact | Div per artifact | Padding, bottom border |
| .step-artifact-meta | Div inside artifact | Flex row for name + timestamp |
| .step-artifact-name | Span | Artifact display name |
| .step-artifact-ts | Span | Artifact file timestamp |
| .step-artifact-content | Pre | Dark code block, lazy loaded |
| .step-artifact-spinner | Span (injected) | CSS loading spinner |
| .step-artifact-error | Span (injected) | Error message, retry target |
| .step-empty | Div | "No artifacts yet." placeholder |

### Modifier Convention

State modifiers use BEM-style: base class + modifier on same element.
- .step-stage.collapsed (not .step-stage--collapsed)
- .step-status-done (status value as suffix, underscore preserved from data)

---

## 11. ASCII Wireframe Mockups

### Mockup A: All Stages Collapsed

```
+---------------------------------------------------------+
| > Intake             [done]    10:42    3 artifacts      |
+---------------------------------------------------------+
| > Requirements       [done]    10:51    1 artifact       |
+---------------------------------------------------------+
| > Planning           [done]    11:03    2 artifacts      |
+---------------------------------------------------------+
| > Execution          [in progress]      4 artifacts      |  yellow badge, no ts
+---------------------------------------------------------+
| > Verification       [not started]      0 artifacts      |  gray badge
+---------------------------------------------------------+
| > Archive            [not started]      0 artifacts      |
+---------------------------------------------------------+
```

### Mockup B: One Stage Expanded (Execution, in progress)

```
+---------------------------------------------------------+
| > Intake             [done]    10:42    3 artifacts      |
+---------------------------------------------------------+
| > Requirements       [done]    10:51    1 artifact       |
+---------------------------------------------------------+
| > Planning           [done]    11:03    2 artifacts      |
+---------------------------------------------------------+
| v Execution          [in progress]      4 artifacts      |  expanded, chevron down
| +-------------------------------------------------------+
| |  task-1-result.md                 11:14                |  loaded artifact
| |  +---------------------------------------------------+|
| |  | ## Task 1 Result                                  ||  dark bg, monospace
| |  | Status: completed                                 ||
| |  +---------------------------------------------------+|
| |                                                        |
| |  task-2-result.md                 11:17                |  second artifact
| |  +---------------------------------------------------+|
| |  | (spinner)  Loading...                              ||  spinner (loading state)
| |  +---------------------------------------------------+|
| |                                                        |
| |  validation-report.md             11:18                |
| |  +---------------------------------------------------+|
| |  | # Validation Report                               ||
| |  | All checks passed.                                ||
| |  +---------------------------------------------------+|
+---------------------------------------------------------+
| > Verification       [not started]      0 artifacts      |
+---------------------------------------------------------+
| > Archive            [not started]      0 artifacts      |
+---------------------------------------------------------+
```

### Mockup C: Mixed Status View (multiple stages open)

```
+---------------------------------------------------------+
| v Intake             [done]    10:42    3 artifacts      |  expanded, done (green)
| +-------------------------------------------------------+
| |  User Request                     10:31                |  "User Request" (NOT Raw Input)
| |  Clause Register                  10:38                |
| |  5 Whys Analysis                  10:42                |
+---------------------------------------------------------+
| > Requirements       [done]    10:51    1 artifact       |  collapsed
+---------------------------------------------------------+
| v Planning           [done]    11:03    2 artifacts      |  expanded, done
| +-------------------------------------------------------+
| |  Design Document                  10:58                |
| |  YAML Plan                        11:03                |
+---------------------------------------------------------+
| v Execution          [in progress]      2 artifacts      |  expanded, in progress
| +-------------------------------------------------------+
| |  Task 1 Result                    11:14                |
| |  Task 2 Result                    11:17                |
+---------------------------------------------------------+
| > Verification       [not started]      0 artifacts      |  collapsed (gray badge)
+---------------------------------------------------------+
| > Archive            [not started]      0 artifacts      |
+---------------------------------------------------------+
```

### Mockup D: Mobile Narrow View (below 480px)

```
+-----------------------------------+
| > Intake         [done]   3 art.  |  timestamp hidden on mobile
+-----------------------------------+
| > Requirements   [done]   1 art.  |
+-----------------------------------+
| v Execution      [in pr]  4 art.  |  badge truncates gracefully
| +---------------------------------+
| |  task-1-result.md    11:14      |  name + ts wrap if needed
| |  +-----------------------------+|
| |  | ## Task 1 Result            ||  content max-height 200px
| |  | Status: completed           ||
| |  +-----------------------------+|
| |                                 |
| |  task-2-result.md    11:17      |
+-----------------------------------+
| > Planning       [done]   2 art.  |
+-----------------------------------+
| > Verification   [n/s]    0 art.  |
+-----------------------------------+
| > Archive        [n/s]    0 art.  |
+-----------------------------------+
```

---

## 12. Acceptance Criteria Cross-Reference

| AC | Addressed by |
|---|---|
| AC3 | Section 2 (visual hierarchy table: 14px/600 headers vs 13px/500 rows) |
| AC4 | Section 3 (.step-stage-ts shown for done stages) |
| AC5 | Section 5 (collapse interaction) |
| AC6 | Temporal sequence: stages in fixed pipeline order (Intake through Archive); timestamps visible |
| AC11 | Section 5 (localStorage restores last open stage; in_progress auto-expands) |
| AC12 | Section 5 (click to collapse, sets localStorage) |
| AC13 | Section 5 (click to expand, loads artifacts) |
| AC14 | Section 5 (each .step-stage is independent; toggling one does not affect others) |
| AC23 | Section 3 (completion timestamp shown on done stage headers) |
| AC24 | Section 3 (.step-stage-ts hidden when stage not done) |
| AC25 | Section 4 (.step-artifact-ts shown per artifact) |
| AC26 | Section 4 (timestamp value from file modification time, passed by backend) |
| AC28 | Section 6 (CSS spinner injected during fetch) |
| AC29 | Section 4 (artifact labeled "User Request" in Intake stage) |
| AC30 | Section 4 (explicit note: "Raw Input" label must not appear anywhere) |

---

## Design Assumptions

- Assumed the existing .badge class in style.css/base styles provides pill-shaped styling (border-radius, padding, font-size) based on usage patterns seen throughout item.html
- Assumed YYYY-MM-DD HH:MM timestamp format based on the server-side formatting described in the systems design document (D3)
- Assumed 44px minimum touch target for stage headers based on WCAG 2.5.5 recommendation
- Assumed mobile breakpoint at 480px for timestamp hiding based on the pattern where 900px is the two-column breakpoint and 480px represents narrow phone screens
- Assumed the error retry pattern (click error span to re-fetch) is acceptable without a dedicated retry button, based on the lightweight vanilla JS approach

## Design Quality Self-Assessment

- Clarity: 9/10 -- All specifications include exact values, classes, and element relationships
- Mobile UX: 8/10 -- Timestamp hiding and reduced max-height adapt to narrow screens; could benefit from gesture support but vanilla JS constraint limits this
- Accessibility: 9/10 -- Button elements, ARIA attributes, keyboard navigation, focus-visible, color contrast all specified
- Consistency: 10/10 -- All values directly reference or extend existing item.html patterns
- Completeness: 9/10 -- All 15 acceptance criteria mapped; error and loading states covered; animation/transition details included
