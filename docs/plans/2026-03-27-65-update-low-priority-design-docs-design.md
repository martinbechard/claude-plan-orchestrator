# Design: Update 3 Low-Priority Design Docs per Audit

## Overview

The design-doc audit (docs/reports/design-doc-audit.md) classified 3 documents as
"Low Priority (meta-doc clarification)". Each contains references to
plan-orchestrator.py that read as current instructions but are actually historical
context describing the subject of the audit itself.

## Files to Modify

1. docs/plans/2026-03-26-01-audit-design-docs-for-validity-design.md
   - Clarify that plan-orchestrator.py references describe the historical context
     being audited, not instructions to call the script

2. docs/plans/2026-03-26-03-cost-analysis-db-backend-design.md
   - Remove write_execution_cost_log() in scripts/plan-orchestrator.py reference;
     the 2026-03-27 version already corrects this

3. docs/plans/2026-03-27-01-audit-design-docs-for-validity-design.md
   - Same as file 1: clarify plan-orchestrator.py references are historical context

## Design Decisions

- All 3 files are meta-docs (audit-related or cost-analysis design docs), so the
  corrections are clarification-only: add historical context markers, remove stale
  script references
- No code changes required
- Per CLAUDE.md: explanations must reflect current steady-state, not reference prior
  versions comparatively
