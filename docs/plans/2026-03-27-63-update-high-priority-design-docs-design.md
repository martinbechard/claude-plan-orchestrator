# Design: Update 7 High-Priority Design Docs

## Overview

The design-doc audit (docs/reports/design-doc-audit.md) identified 7 documents
that actively mislead agents by referencing the deleted scripts/plan-orchestrator.py.
This plan corrects each per the audit's "High Priority" recommendations.

## Documents to Update

### Group A: Spec-Aware Validator Docs (4 files)

1. docs/plans/2026-02-18-spec-aware-validator-with-e2e-logging-design.md
   - Remove plan-orchestrator.py refs; port SPEC_DIR, E2E_COMMAND to langgraph config
2. docs/plans/2026-03-24-11-spec-aware-validator-with-e2e-logging-design.md
   - Remove "Already implemented" section citing plan-orchestrator.py
3. docs/plans/2026-03-24-spec-aware-validator-with-e2e-logging-design.md
   - Remove plan-orchestrator.py line refs (62-63, 377-378, 412, 1765)
4. docs/plans/2026-03-25-spec-aware-validator-with-e2e-logging-design.md
   - Remove plan-orchestrator.py line refs; remove CompletionTracker/auto_pipeline.py test refs

### Group B: Cost/Tool-Call Docs (3 files)

5. docs/plans/2026-03-24--cost-analysis-design.md
   - Replace import path to langgraph_pipeline.slack.notifier
6. docs/plans/2026-03-25-16-tool-call-timing-and-cost-analysis-ui-design.md
   - Update schema section to reference langgraph_pipeline/shared/cost_log.py
7. docs/plans/2026-03-26-27-tool-call-cost-attribution-dummy-data-design.md
   - Replace plan-orchestrator.py executor node refs with langgraph_pipeline/ paths

## Approach

Each task updates a group of related docs. The coder agent reads each file,
applies the specific corrections from the audit, and ensures no plan-orchestrator.py
references remain while keeping the architectural intent of each document intact.

## Key Principle

Updates should reflect current steady-state architecture. No "was X, now Y"
comparative language. Write as if the langgraph_pipeline always existed.


## Acceptance Criteria

- Are all 7 high-priority UPDATE docs corrected per the audit?
  YES = pass, NO = fail
- Do the updated docs reference langgraph_pipeline/ paths instead of
  plan-orchestrator.py? YES = pass, NO = fail
