# Design: Audit Design Docs for Validity

## Problem

There are 218 design documents in docs/plans/. Many reference deleted scripts
(plan-orchestrator.py), removed conventions (tilde cost prefix), or outdated
file paths. Pipeline agents read these docs during plan creation and may follow
outdated instructions.

## Approach

Systematic batch review of all design docs, classifying each as KEEP, UPDATE,
ARCHIVE, or DELETE based on accuracy and current utility. The audit checks for:

- References to deleted scripts (plan-orchestrator.py, auto-pipeline.py)
- Outdated conventions conflicting with CLAUDE.md or MEMORY.md
- References to non-existent file paths, functions, or modules
- Completed backlog items where the design doc adds no architectural value

## Batching Strategy

218 docs split into 4 batches by date range to keep each task manageable:

- Batch 1: 2026-02-13 through 2026-02-18 (~44 docs)
- Batch 2: 2026-02-19 through 2026-02-26 (~29 docs)
- Batch 3: 2026-03-23 through 2026-03-25 (~33 docs)
- Batch 4: 2026-03-26 through 2026-03-27 plus YYYY-MM-DD (~112 docs)

Each batch produces partial results appended to a working classification file.

## Output

- Classification report: docs/reports/design-doc-audit.md
- Each doc classified as KEEP / UPDATE / ARCHIVE / DELETE with reasoning
- Summary statistics and recommended next steps
- Slack notification with summary

## Key Files

- Input: docs/plans/*.md (218 design documents)
- Output: docs/reports/design-doc-audit.md
- Reference: CLAUDE.md, MEMORY.md, current codebase state

## Design Decisions

1. Use code-reviewer agent for analysis tasks since this is read-only audit work
2. Split into 4 batches rather than one massive task to avoid context limits
3. Final task consolidates results and posts to Slack
4. Each batch task checks actual codebase state (file existence, current conventions)
   rather than relying on assumptions about what changed
