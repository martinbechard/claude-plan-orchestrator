# QA Audit Pipeline with Test Plan Generation - Design Document

**Goal:** Create a QA audit pipeline that generates test plans from functional specifications and runs structured validation checklists against implemented features. Adds a qa-auditor agent, domain-specific checklists, and integration with the existing validation pipeline.

**Architecture:** Define a qa-auditor agent that orchestrates a multi-stage pipeline: (1) extract user-facing behaviors from functional specs, (2) map behaviors to test scenarios using domain checklists, (3) run individual checklist items as fast/cheap audits, (4) produce a structured QA audit report with coverage matrix. Domain checklists are reusable markdown templates stored in .claude/checklists/. The qa-auditor integrates as an additional validator in the existing ValidationConfig.validators list.

**Tech Stack:** Python 3 (plan-orchestrator.py for validator registration), Markdown (agent definition, checklist templates), YAML (plan meta.validation.validators list)

---

## Architecture Overview

### Dependencies

- Feature 02 (Agent Definition Framework): Agent infrastructure for defining qa-auditor (already implemented)
- Feature 03 (Per-Task Validation Pipeline): Validation hook to trigger qa-auditor as a validator (already implemented)

### Pipeline Stages

The QA audit pipeline processes a functional spec through four stages:

    Stage 1: Page Guide Generator (sonnet)
      Input: Functional spec document
      Output: Grouped list of user-facing behaviors by page/component
      Purpose: Extract what the user can do on each page

    Stage 2: Test Plan Generator (sonnet)
      Input: Page guide + domain checklists
      Output: Structured test plan with coverage matrix
      Purpose: Map each behavior to test scenarios, apply checklist rules

    Stage 3: Checklist Auditor (haiku)
      Input: Individual checklist items + codebase
      Output: Pass/fail per checklist item with evidence
      Purpose: Fast, cheap verification of each item

    Stage 4: Report Aggregator
      Input: All checklist results + coverage matrix
      Output: QA Audit Report with coverage percentage
      Purpose: Aggregate results, flag uncovered behaviors

In the initial implementation, the qa-auditor agent handles all four stages in a single session. The agent prompt instructs it to follow this pipeline sequence. The haiku-level checklist processing is a future optimization (the agent prompt describes the approach, but the initial version runs everything in one sonnet session for simplicity).

### QA Auditor Agent

New agent definition at .claude/agents/qa-auditor.md:

    ---
    name: qa-auditor
    description: >
      QA audit specialist. Generates test plans from functional specs and runs
      validation checklists against implemented features. Use after feature
      implementation to verify coverage of user-facing behaviors.
    tools:
      - Read
      - Grep
      - Glob
      - Bash
    model: sonnet
    ---

The qa-auditor is a read-only verification agent (like code-reviewer and validator). It uses Bash only for running build/test commands, not for modifying files. It reads functional specs, domain checklists, and source code to produce a structured QA report.

### Domain Checklists

Reusable checklist templates stored in .claude/checklists/:

**crud-operations.md** - Rules for CRUD features:
- Create and edit use the same modal/form
- Page loads correctly on browser refresh
- Data persists after save and reload
- Cancel discards unsaved changes
- Save button enables only when required fields are filled
- Validation errors display inline near the relevant field
- Delete requires confirmation

**navigation.md** - Rules for navigation features:
- All links resolve to valid pages
- Back button returns to the previous page
- Breadcrumbs reflect the current location
- Deep links work (direct URL access)

**data-display.md** - Rules for data display features:
- Empty state shows a helpful message (not blank)
- Loading state shows a spinner or skeleton
- Error state shows an actionable message
- Lists paginate or virtualize for large datasets
- Sort and filter controls work correctly

Each checklist file is a simple markdown document with one rule per line (prefixed with -). The qa-auditor reads the relevant checklists based on the feature type and applies each rule against the codebase.

### Integration with Validation Pipeline

The qa-auditor registers as a validator in the plan meta.validation.validators list. No code changes are needed to plan-orchestrator.py because the validator mechanism is already generic: it loads any agent name from the validators list, builds a validation prompt using that agent's body, and runs it.

To enable qa-auditor for a plan:

    meta:
      validation:
        enabled: true
        run_after: [coder]
        validators: [validator, qa-auditor]

When a coder task completes, the orchestrator runs both the generic validator AND the qa-auditor in sequence (short-circuiting on first FAIL).

### Test Plan Output Format

The qa-auditor produces a structured report matching this template:

    # QA Audit Report: [Feature Name]

    ## Source: [Functional Spec Reference]

    ## Coverage Matrix

    | Spec Requirement | Test Scenario | Checklist | Status |
    |-----------------|---------------|-----------|--------|
    | User can create | Create via modal | crud | PASS |
    | User can edit   | Edit via same modal | crud | PASS |
    | ...             | ...           | ...       | ...    |

    ## Checklist Results

    ### CRUD Operations
    - [PASS] Create and edit use the same modal
    - [PASS] Page loads on refresh
    - [FAIL] Cancel does not discard changes (no cancel handler found)

    ## Coverage: X/Y requirements covered (Z%)

The report is included in the validator output and parsed by the existing VERDICT_PATTERN and FINDING_PATTERN regex in plan-orchestrator.py.

---

## Key Files

### New Files

| File | Purpose |
|------|---------|
| .claude/agents/qa-auditor.md | QA audit agent definition with pipeline instructions |
| .claude/checklists/crud-operations.md | CRUD operations domain checklist |
| .claude/checklists/navigation.md | Navigation domain checklist |
| .claude/checklists/data-display.md | Data display domain checklist |
| tests/test_qa_auditor_integration.py | Unit tests verifying agent loads and checklist files parse correctly |

### Modified Files

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Add QA_AUDITOR_KEYWORDS to infer_agent_for_task() so qa-auditor is auto-selected for tasks with audit/qa/checklist keywords |

---

## Design Decisions

1. **qa-auditor runs as a single sonnet session, not a multi-model pipeline.** The backlog item describes haiku for checklists and sonnet for test plan generation. In the initial version, the qa-auditor runs everything in one sonnet session with instructions to process checklists concisely. This avoids the complexity of agent-to-agent dispatch while delivering the core value. Multi-model dispatch can be added later by having the orchestrator run individual checklist items as separate haiku tasks.

2. **No changes to plan-orchestrator.py validation mechanics.** The existing validation pipeline already supports arbitrary validator names. Adding qa-auditor to the validators list is a pure configuration change. The only code change is adding audit-related keywords to infer_agent_for_task() for auto-selection.

3. **Checklists are static markdown files, not dynamic.** Checklists live in .claude/checklists/ as plain markdown. They are not generated or parameterized. The qa-auditor reads them and applies each item as a verification check. This keeps checklists simple, version-controlled, and human-editable.

4. **qa-auditor produces standard VERDICT format.** The agent outputs **Verdict: PASS/WARN/FAIL** with - [PASS/WARN/FAIL] findings, matching the existing VERDICT_PATTERN and FINDING_PATTERN in plan-orchestrator.py. This means no parser changes are needed.

5. **Checklists are organized by domain, not by page.** A CRUD page applies the crud-operations checklist plus the data-display checklist. The qa-auditor selects which checklists apply based on the functional spec content, not a hardcoded mapping.

6. **Keywords for agent inference include "audit", "qa", "checklist", "test plan".** These are added to a new QA_AUDITOR_KEYWORDS list in plan-orchestrator.py, following the same pattern as REVIEWER_KEYWORDS and DESIGNER_KEYWORDS.
