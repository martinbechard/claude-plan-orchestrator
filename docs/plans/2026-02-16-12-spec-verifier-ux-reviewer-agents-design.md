# Spec Verifier and UX Reviewer Agents - Design Document

**Goal:** Create two validator agents (spec-verifier and ux-reviewer) that check UI code changes against functional specifications and usability standards, producing structured PASS/WARN/FAIL verdicts.

**Architecture:** Define two read-only agents in .claude/agents/ following the established agent definition pattern. Both use tools: Read, Grep, Glob (no Bash since they only inspect code, unlike qa-auditor which runs tests). Add inference keywords (SPEC_VERIFIER_KEYWORDS and UX_REVIEWER_KEYWORDS) to plan-orchestrator.py so tasks with spec/ux keywords auto-select the correct agent. Both agents integrate as additional validators in the existing ValidationConfig.validators list.

**Tech Stack:** Python 3 (plan-orchestrator.py for keyword registration), Markdown (agent definitions), YAML (plan meta.validation.validators)

---

## Architecture Overview

### Dependencies

- Feature 02 (Agent Definition Framework): Agent infrastructure for loading agent definitions (already implemented)
- Feature 03 (Per-Task Validation Pipeline): Validation hook to trigger validators (already implemented)
- Feature 11 (QA Audit Pipeline): Established the pattern for adding new agents with keywords (already implemented)

### Agent Definitions

#### Spec Verifier Agent (.claude/agents/spec-verifier.md)

    ---
    name: spec-verifier
    description: >
      Functional specification verifier. Use after UI changes to validate that
      component placement, data display, and user workflow match the spec.
      Read-only: does not modify code.
    tools:
      - Read
      - Grep
      - Glob
    model: sonnet
    ---

The spec-verifier reads functional specs and compares implemented code against them. It checks:
- Component placement on the correct page and section
- Data display honesty (no fallback data from wrong sources)
- CRUD operations (create/edit use same form, cancel discards changes, etc.)
- No removed components unless explicitly requested

#### UX Reviewer Agent (.claude/agents/ux-reviewer.md)

    ---
    name: ux-reviewer
    description: >
      UX/UI quality reviewer. Use after UI changes to evaluate design quality,
      accessibility, and usability. Read-only: does not modify code.
      Distinct from ux-designer which generates designs.
    tools:
      - Read
      - Grep
      - Glob
    model: sonnet
    ---

The ux-reviewer evaluates implemented UI code for usability. It checks:
- Responsive layout (mobile and desktop)
- Accessibility (ARIA labels, keyboard navigation, color contrast)
- State coverage (loading, error, empty states)
- Visual hierarchy and interaction patterns
- Consistency with project component library
- Centralized feedback system usage (toasts, not inline divs)

### Relationship Between Existing Agents

    ux-designer   -> generates designs (Phase 0, creative, opus model)
    ux-reviewer   -> reviews implemented UI (validation, analytical, sonnet model)

    spec-verifier -> checks code matches spec (structural compliance)
    qa-auditor    -> generates test plans from spec (coverage analysis)

    code-reviewer -> checks coding standards (naming, types, file size)
    validator     -> post-task build/test coordinator

### Agent Inference Keywords

New keyword constants added to plan-orchestrator.py:

    SPEC_VERIFIER_KEYWORDS = [
        "spec verifier", "spec verification", "functional spec",
        "spec-verifier", "spec compliance"
    ]

    UX_REVIEWER_KEYWORDS = [
        "ux review", "ux-reviewer", "usability review",
        "accessibility review", "ui quality"
    ]

These are multi-word phrases checked before single-word DESIGNER_KEYWORDS in infer_agent_for_task() to avoid false positives.

### Integration with Validation Pipeline

Both agents register as validators in the plan meta. No code changes to the validation mechanics (already generic). To enable for a plan:

    meta:
      validation:
        enabled: true
        run_after: [coder]
        validators: [code-reviewer, spec-verifier, ux-reviewer]
        max_validation_attempts: 1

The validator dispatch section in the backlog describes context-based selection: spec-verifier and ux-reviewer run when tasks modify UI files (.tsx, .jsx, .vue, .svelte). In this initial implementation, selection is manual via the validators list. Context-based auto-dispatch is a future enhancement.

### Output Format

Both agents produce the standard verdict format parsed by existing VERDICT_PATTERN and FINDING_PATTERN:

    **Verdict: PASS** or **Verdict: WARN** or **Verdict: FAIL**

    **Findings:**
    - [PASS|WARN|FAIL] Description with file:line references

    **Evidence:**
    - Finding N: Specific code reference or spec reference

The ux-reviewer additionally produces a quality score section:

    **Quality Score:**
    - Clarity: X/10
    - Consistency: X/10
    - Accessibility: X/10
    - Implementation Feasibility: X/10

---

## Key Files

### New Files

| File | Purpose |
|------|---------|
| .claude/agents/spec-verifier.md | Spec verification agent definition with checklist |
| .claude/agents/ux-reviewer.md | UX review agent definition with checklist and quality scoring |
| tests/test_spec_verifier_ux_reviewer.py | Unit tests for agent loading, keyword inference, and integration |

### Modified Files

| File | Change |
|------|---------|
| scripts/plan-orchestrator.py | Add SPEC_VERIFIER_KEYWORDS and UX_REVIEWER_KEYWORDS to infer_agent_for_task() |

---

## Design Decisions

1. **Read-only agents with no Bash tool.** Unlike qa-auditor and validator which use Bash for running build/test commands, spec-verifier and ux-reviewer only inspect code. They do not run builds or tests. This constrains them to pure code analysis, reducing risk and execution time.

2. **sonnet model, not haiku.** Both agents need to reason about code structure and compare against specifications. haiku is too lightweight for this kind of analysis. sonnet provides the right balance of quality and cost.

3. **Standard VERDICT format for compatibility.** Both agents output **Verdict: PASS/WARN/FAIL** with structured findings, matching the existing VERDICT_PATTERN and FINDING_PATTERN regex. No parser changes needed.

4. **UX reviewer is distinct from UX designer.** The ux-designer generates designs (creative, opus model, Phase 0). The ux-reviewer evaluates implemented code (analytical, sonnet model, validation phase). The names are intentionally different to avoid confusion.

5. **CRUD checklist reference in spec-verifier.** The spec-verifier references .claude/checklists/crud-operations.md (created in feature 11) for CRUD-specific verification rules. This reuses existing domain knowledge without duplication.

6. **Multi-word keywords checked before single-word DESIGNER_KEYWORDS.** Keywords like "spec verification" and "ux review" are multi-word phrases. They are checked before single-word keywords (like "design") to prevent false matches where a "ux review" task would match the "design" keyword in DESIGNER_KEYWORDS.
