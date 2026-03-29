# Requirements: 74 Item Page Step Explorer

Source: tmp/plans/.claimed/74-item-page-step-explorer.md

## Problem Statement

The work item detail page displays all artifacts in a single long page without
visual hierarchy or collapsibility. Users cannot identify which pipeline stage
produced each artifact, understand the temporal sequence, or collapse sections
irrelevant to their current task. All content loads at page render, causing
unnecessary weight for items with many artifacts.

## Priorities

- P1: Organize artifacts into pipeline stage groups with correct ordering
- P2: Show timestamps at stage and artifact level
- P3: Enable collapse/expand per stage with persistence across page reloads

## Functional Requirements

- FR1: Group all item artifacts under six ordered pipeline stages (Intake,
  Requirements, Planning, Execution, Verification, Archive)
- FR2: Compute each stage's status as not_started, in_progress, or done based
  on the item's pipeline_stage and artifact presence
- FR3: Load artifact content on demand (AJAX) when a stage is expanded, not at
  initial page load
- FR4: Rename the "Raw Input" artifact label to "User Request" in all
  user-facing UI

## Use Cases

- UC1: A user opens the item page and sees stages in pipeline order, each with
  a status badge, and can immediately tell how far the item has progressed
- UC2: A user clicks a collapsed stage header to expand it, revealing nested
  artifacts with their timestamps. Artifact content loads via AJAX on first
  expansion
- UC3: A user reviews a completed stage and sees its completion timestamp
  (derived from the latest artifact mtime in that stage)

## Acceptance Criteria

### Stage Grouping (P1, FR1)

- AC1: Artifacts are grouped into six pipeline stage sections on the item page
- AC7: Stages render in fixed pipeline order (Intake -> Requirements ->
  Planning -> Execution -> Verification -> Archive)
- AC8: build_stages() enforces this order regardless of artifact discovery order

### Visual Hierarchy (P3)

- AC2: Stage headers are visually distinct from artifact items (larger font,
  bold, status badge)
- AC9: Collapsed stages allow direct access to the expanded stage without
  scrolling through hidden content
- AC11: Each stage section shows name, status badge, completion timestamp (when
  done), and nested artifacts
- AC12: Collapsed stages reduce page scroll distance

### Timestamps (P2)

- AC3: Completed stages display a completion timestamp
- AC4: Each artifact displays its file modification timestamp
- AC13: Stage completion timestamp equals the latest artifact mtime when stage
  is done
- AC14: Artifacts are nested under stages with individual timestamps visible
- AC15: Artifact timestamps show created-or-last-modified time (file mtime)

### Collapse / Expand (P3)

- AC5: Stage sections collapse via clickable header toggle
- AC6: Collapsed stages expand on click to reveal artifacts

### Stage Status (FR2)

- AC22: Each stage has a three-state status indicator: not_started, in_progress,
  or done

### On-Demand Loading (FR3)

- AC10: Artifact content is fetched via AJAX only when its parent stage is
  expanded
- AC23: Content is fetched on demand via the existing artifact-content endpoint
- AC24: Initial page load renders only stage headers and artifact metadata (no
  artifact content bodies)

### Artifact Mapping (FR1)

- AC16: Intake stage contains: User Request, clause register, 5 whys analysis
- AC17: Requirements stage contains: structured requirements document
- AC18: Planning stage contains: design document, YAML plan
- AC19: Execution stage contains: per-task output files, validation reports
- AC20: Verification stage contains: final verification report (defects only,
  omitted for features)
- AC21: Archive stage contains: completion status/outcome records

### Rename Raw Input (FR4)

- AC25: The label "User Request" appears in build_stages() for the original
  backlog file artifact
- AC26: No user-facing occurrence of "Raw Input" label remains on item pages

## Non-Functional Requirements

- NFR1: Initial page load time must not increase (on-demand loading offsets
  removed inline content)
- NFR2: Stage status updates in real-time via the existing /dynamic polling
  mechanism
- NFR3: Collapse state persists across page reloads (localStorage)
