# Requirements: 74 Item Page Step Explorer

Source: tmp/plans/.claimed/74-item-page-step-explorer.md
Design: docs/plans/2026-04-02-74-item-page-step-explorer-design.md

## Problem Statement

The work item detail page displays all artifacts in a single long page with no
visual hierarchy, no timestamps, and no way to collapse sections. Users cannot
identify which pipeline stage produced each artifact or understand the temporal
sequence of work.

## Priorities

- P1: Organize artifacts under their pipeline stages in chronological order
- P2: Show stage status, timestamps, and temporal sequence
- P3: On-demand artifact loading with collapsible sections for fast page load

## Use Cases

- UC1: User views an item page and sees artifacts grouped under six ordered
  pipeline stages (Intake, Requirements, Planning, Execution, Verification, Archive)
- UC2: User expands a collapsed stage to view its artifacts; content loads on
  demand with a loading indicator

## Functional Requirements

- FR1: Display six pipeline stages in order with artifacts nested under each stage
- FR2: Each stage displays a three-state status: not_started, in_progress, done
- FR3: Completed stages display a completion timestamp from latest artifact mtime
- FR4: Each artifact displays its file modification timestamp
- FR5: Artifact content loads on demand when a stage is expanded (not at page load)
- FR6: The "Raw Input" label is replaced with "User Request" in the Intake stage

## Acceptance Criteria

| ID | Criterion | Priority | Category |
|---|---|---|---|
| AC1 | Artifacts are grouped under their parent pipeline stage heading | P1 | Structure |
| AC2 | The flat layout is replaced by a structured, navigable layout | P1 | Structure |
| AC3 | Each artifact visually indicates its pipeline stage via nesting | P1 | Structure |
| AC4 | Each pipeline stage displays a timestamp | P2 | Timestamps |
| AC5 | Users can collapse sections they are not interested in | P2 | Navigation |
| AC6 | Temporal sequence of work is visually apparent | P2 | Timestamps |
| AC7 | Artifacts are loaded on demand, not all at page load | P3 | Performance |
| AC8 | Initial page load is faster because artifact content is deferred | P3 | Performance |
| AC9 | Step explorer shows stages in chronological pipeline order | P1 | Structure |
| AC10 | Stages display in order: Intake, Requirements, Planning, Execution, Verification, Archive | P1 | Structure |
| AC11 | User can navigate to a specific stage quickly without scrolling all content | P2 | Navigation |
| AC12 | User can collapse a pipeline stage to hide its artifacts | P2 | Navigation |
| AC13 | User can expand a collapsed pipeline stage to reveal its artifacts | P2 | Navigation |
| AC14 | Each stage can independently collapse/expand without affecting others | P2 | Navigation |
| AC15 | Intake stage contains: User Request, clause register, 5 whys analysis | P1 | Mapping |
| AC16 | Requirements stage contains: structured requirements document | P1 | Mapping |
| AC17 | Planning stage contains: design document, YAML plan | P1 | Mapping |
| AC18 | Execution stage contains: per-task results, validation reports | P1 | Mapping |
| AC19 | Verification stage appears only for defects, contains final verification report | P1 | Mapping |
| AC20 | Archive stage contains: completion status, outcome | P1 | Mapping |
| AC21 | Each stage displays status: not started, in progress, or done | P2 | Status |
| AC22 | Status accurately reflects actual pipeline stage state | P2 | Status |
| AC23 | Completed stage displays completion timestamp from latest artifact mtime | P2 | Timestamps |
| AC24 | Timestamp is absent/hidden for stages that have not completed | P2 | Timestamps |
| AC25 | Each artifact displays its own timestamp | P2 | Timestamps |
| AC26 | Artifact timestamp reflects file creation or last modification time | P2 | Timestamps |
| AC27 | Artifact contents load only when user expands/requests (not at page load) | P3 | Performance |
| AC28 | Loading indicator shown while artifact content is being fetched | P3 | Performance |
| AC29 | Label "Raw Input" replaced with "User Request" in Intake stage | P1 | Labelling |
| AC30 | "Raw Input" no longer appears as a label anywhere on the item page | P1 | Labelling |

## Non-Functional Requirements

- NFR1: No new JavaScript frameworks; use existing vanilla JS stack
- NFR2: No new Python dependencies; use existing FastAPI/Jinja2 stack
- NFR3: Collapse/expand state persists across page reloads via localStorage
- NFR4: Stage headers use accessible button elements with aria-expanded and aria-controls
- NFR5: Keyboard navigation (Enter/Space) works on stage headers
