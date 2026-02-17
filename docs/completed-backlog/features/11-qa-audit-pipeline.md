# QA Audit Pipeline with Test Plan Generation

## Status: Open

## Priority: Medium

## Summary

Create a QA audit pipeline that generates test plans from functional specifications
and runs structured validation checklists against implemented features. This adds a
qa-auditor agent that bridges functional specs and verification, producing reusable
test plans that cover what a user can actually do on each page.

The pipeline uses cost-efficient models (haiku for checklist processing, sonnet for
test plan generation) to keep audit costs low while providing thorough coverage.

## Sources

- docs/ideas/e2e-test-protocol.md: CRUD validation checklist, functional spec to
  page guide to test plan pipeline, generic QA checklist processed by haiku.
- docs/ideas/specialized-agent-architecture.md: Validation hierarchy with specialized
  sub-agents, the concept of focused verification agents with checklists.

## Problem

The current validation pipeline (feature 03) verifies that code changes meet coding
standards and that defect fixes resolve the reported issue. What it does NOT do:

1. Verify that a feature implementation covers all user-facing behaviors described
   in the functional spec.
2. Generate a structured test plan that maps spec requirements to test scenarios.
3. Apply domain-specific validation rules (e.g., CRUD operations must use a single
   modal for create/edit, pages must load correctly on reload, data must persist).
4. Provide a QA audit trail: a document proving that each spec requirement has a
   corresponding test and that test was checked.

## Proposed Design

### QA Audit Pipeline Stages

    Functional Spec
         |
         v
    Page Guide Generator (sonnet)
    - Extracts user-facing behaviors from the spec
    - Groups by page/component
    - Produces a "what the user can do" guide
         |
         v
    Test Plan Generator (sonnet)
    - Maps each behavior to test scenarios
    - Applies domain checklists (CRUD, navigation, data persistence)
    - Produces structured test plan with coverage matrix
         |
         v
    Checklist Auditor (haiku)
    - Runs each checklist item against the codebase
    - Fast, cheap, focused on yes/no checks
    - Produces pass/fail per checklist item
         |
         v
    QA Audit Report
    - Aggregated results with coverage percentage
    - Uncovered behaviors flagged for manual review
    - Links each test to its spec requirement

### QA Auditor Agent (agents/qa-auditor.md)

A new agent that orchestrates the pipeline:

    ---
    name: qa-auditor
    description: >
      QA audit specialist. Generates test plans from functional specs and runs
      validation checklists. Use after feature implementation to verify coverage.
    tools: Read, Grep, Glob, Bash
    model: sonnet
    ---

The qa-auditor reads the functional spec, generates the test plan, then dispatches
haiku-level checklist checks for each item.

### Domain Checklists

Reusable checklist templates stored in .claude/checklists/:

**crud-operations.md:**
- Create and edit use the same modal/form
- Page loads correctly on browser refresh
- Data persists after save and reload
- Cancel discards unsaved changes
- Save button enables only when all required fields are filled
- Validation errors display inline near the relevant field
- Delete requires confirmation

**navigation.md:**
- All links resolve to valid pages
- Back button returns to the previous page
- Breadcrumbs reflect the current location
- Deep links work (direct URL access)

**data-display.md:**
- Empty state shows a helpful message (not blank)
- Loading state shows a spinner or skeleton
- Error state shows an actionable message
- Lists paginate or virtualize for large datasets
- Sort and filter controls work correctly

### Integration with Validation Pipeline

The qa-auditor plugs into the existing validation pipeline (feature 03) as an
additional validator. In plan meta:

    meta:
      validation:
        enabled: true
        run_after: [coder]
        validators: [code-reviewer, qa-auditor]

### Test Plan Output Format

The generated test plan is a markdown file with structured sections:

    # Test Plan: [Feature Name]

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
    ...

## Verification

- Create a sample functional spec for a CRUD page
- Run the qa-auditor against an implemented feature
- Verify the test plan covers all spec requirements
- Verify checklist items produce correct pass/fail results
- Verify the coverage matrix links tests to spec requirements

## Files Likely Affected

| File | Change |
|------|--------|
| .claude/agents/qa-auditor.md | New agent definition |
| .claude/checklists/crud-operations.md | CRUD domain checklist |
| .claude/checklists/navigation.md | Navigation domain checklist |
| .claude/checklists/data-display.md | Data display domain checklist |
| scripts/plan-orchestrator.py | Register qa-auditor as a validator option |

## Dependencies

- 02-agent-definition-framework.md (completed): Agent infrastructure must exist
- 03-per-task-validation-pipeline.md (completed): Validation hook to trigger audits
