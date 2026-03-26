# Audit Design Docs for Validity - Design

## Overview

Audit all 142 design documents in docs/plans/ for accuracy and relevance. Many
documents may reference the deleted scripts/plan-orchestrator.py, the removed
tilde cost prefix convention, or other outdated implementation details. Pipeline
agents read these docs during plan creation, so stale directives can mislead them.

## Scope

- 142 markdown files in docs/plans/
- Cross-reference against: current CLAUDE.md, MEMORY.md, actual codebase

## Classification Criteria

Each document is classified as one of:

- KEEP: accurate and useful as architecture reference
- UPDATE: useful but contains outdated references needing correction
- ARCHIVE: completed work with no ongoing reference value
- DELETE: contains harmful outdated directives that could mislead agents

## Key Issues to Detect

1. References to scripts/plan-orchestrator.py (deleted)
2. References to scripts/auto-pipeline.py (deleted)
3. Tilde (~) prefix on cost values (convention explicitly removed)
4. File paths, function names, or modules that no longer exist
5. Directives conflicting with current CLAUDE.md or MEMORY.md

## Approach

A single analysis task reads all docs/plans/ files, classifies each, and produces:
- docs/reports/design-doc-audit.md: full classification report
- Slack notification with summary

The analysis agent (code-reviewer) handles all 142 docs in one session since the
task is read-only and does not require implementation changes.

## Key Files

- Input: docs/plans/*.md (142 files)
- Output: docs/reports/design-doc-audit.md (new file)
- Reference: CLAUDE.md, .claude/memory/MEMORY.md, codebase file structure

## Design Decisions

- Single analysis task: all docs are read-only; batching into one session avoids
  excessive orchestration overhead for a pure analysis workload
- No UPDATE tasks generated automatically: the audit report itself identifies
  candidates; a human or follow-on backlog item handles remediation
- Slack notification included per work item spec
