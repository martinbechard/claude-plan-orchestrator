# Spec Verifier and UX Reviewer Agents

## Status: Open

## Priority: Medium

## Summary

Create two missing validator agents from the specialized agent architecture: a
spec-verifier that checks code changes against functional specifications, and a
ux-reviewer that evaluates UI quality and usability. Both are read-only validators
that produce PASS/WARN/FAIL verdicts and integrate with the validation pipeline.

These agents close the gap between "code compiles and passes tests" and "the feature
actually matches what was specified and is usable."

## Sources

- docs/ideas/specialized-agent-architecture.md: Detailed spec-verifier and ux-reviewer
  agent definitions with checklists, output formats, and integration points.
- docs/ideas/e2e-test-protocol.md: CRUD validation rules that inform the spec-verifier
  checklist (e.g., create/edit use same modal, data persists after save).

## Problem

The current agent roster includes a code-reviewer (coding standards) and issue-verifier
(defect fix verification), but lacks two agents described in the architecture:

1. **No spec-verifier**: When a coder implements a UI feature, nothing checks whether
   the components ended up on the correct page, whether the layout matches the spec,
   or whether data display is honest (no fallback data from wrong sources).

2. **No ux-reviewer**: When UI code is written, nothing evaluates whether it meets
   basic usability standards (responsive layout, accessibility, loading/error/empty
   states, keyboard navigation).

These gaps mean UI defects are caught late (by humans in manual review) rather than
early (by automated agents in the validation pipeline).

## Proposed Design

### Spec Verifier Agent (agents/spec-verifier.md)

    ---
    name: spec-verifier
    description: >
      Functional specification verifier. Use after UI changes to validate that
      component placement, data display, and user workflow match the spec.
      Read-only: does not modify code.
    tools: Read, Grep, Glob
    model: sonnet
    ---

Verification checklist:
- Read the functional spec for every page affected by the changes
- For each UI component added or moved:
  - Does it appear on the correct page per the spec?
  - Is it in the correct section/position within the page?
  - Does it match the workflow described in the spec?
- For each data display:
  - Is real data shown when available?
  - When data is unavailable, does it show an appropriate empty state?
  - Is there any fallback to data from a different source? (FAIL if yes)
- For CRUD operations (from e2e-test-protocol):
  - Do create and edit use the same form/modal?
  - Is data properly saved and reloaded?
  - Can the user cancel without saving?
  - Are mandatory field validations present?
- For removed components: was removal explicitly requested?

Output format: VERDICT with FINDINGS and EVIDENCE sections (same as code-reviewer).

### UX Reviewer Agent (agents/ux-reviewer.md)

    ---
    name: ux-reviewer
    description: >
      UX/UI quality reviewer. Use after UI changes to evaluate design quality,
      accessibility, and usability. Read-only: does not modify code.
      Distinct from ux-designer which generates designs.
    tools: Read, Grep, Glob
    model: sonnet
    ---

Review checklist:
- Responsive layout: components work on mobile and desktop viewports
- Accessibility: ARIA labels on interactive elements, keyboard navigation,
  sufficient color contrast, screen reader compatibility
- State coverage: loading states, error states, empty states all handled
- Visual hierarchy: information density is appropriate, primary actions are
  visually prominent
- Interaction patterns: hover states, focus indicators, click targets are
  large enough for touch
- Consistency: uses project component library, follows existing patterns
- Feedback: uses centralized notification/toast system, not inline ad-hoc divs

Output format: VERDICT with FINDINGS and EVIDENCE sections, plus a quality score
(1-10) on clarity, consistency, accessibility, and implementation feasibility.

### Validator Dispatch Integration

The validator agent (already exists) dispatches these sub-validators based on
task context:

- code-reviewer: always (for all code changes)
- issue-verifier: when fixing a defect
- spec-verifier: when task modifies UI files (.tsx, .jsx, .vue, .svelte)
- ux-reviewer: when task modifies UI files

Plan meta configuration:

    meta:
      validation:
        enabled: true
        run_after: [coder]
        validators: [code-reviewer, spec-verifier, ux-reviewer]
        max_validation_attempts: 1

### Relationship Between Agents

    ux-designer  -- generates designs (Phase 0, creative)
    ux-reviewer  -- reviews implemented UI (Phase validation, analytical)

    spec-verifier  -- checks code matches spec (structural compliance)
    qa-auditor     -- generates test plans from spec (coverage analysis)

These are complementary, not overlapping. The spec-verifier is a focused check
("does code match spec?"), while the qa-auditor (feature 11) is a broader pipeline
("what should we test and did we cover it?").

## Verification

- Create spec-verifier.md and ux-reviewer.md agent definitions
- Run spec-verifier against a feature with a known spec deviation
- Verify it catches the deviation and produces a FAIL verdict
- Run ux-reviewer against a UI component missing accessibility attributes
- Verify it flags the accessibility gap
- Verify both integrate with the validation pipeline dispatch

## Files Likely Affected

| File | Change |
|------|--------|
| .claude/agents/spec-verifier.md | New agent definition |
| .claude/agents/ux-reviewer.md | New agent definition |
| .claude/agents/validator.md | Update dispatch logic to include new sub-validators |
| scripts/plan-orchestrator.py | Register new validators in agent inference rules |

## Dependencies

- 02-agent-definition-framework.md (completed): Agent infrastructure
- 03-per-task-validation-pipeline.md (completed): Validation dispatch hook
