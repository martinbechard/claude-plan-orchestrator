# Design: Fix False-Positive Agent Inference for Reviewer Keywords

## Problem

The `infer_agent_for_task()` function in `scripts/plan-orchestrator.py` uses overly
broad single-word keyword matching for `REVIEWER_KEYWORDS`:

```python
REVIEWER_KEYWORDS = [
    "verify", "review", "check", "validate", "regression", "compliance"
]
```

These words are extremely common in implementation task descriptions. For example:
- "Add content moderation **check** functionality" matches "check" -> code-reviewer (wrong)
- "Implement **review** UI for moderators" matches "review" -> code-reviewer (wrong)
- "**Validate** user input in the form" matches "validate" -> code-reviewer (wrong)

When a task is misclassified as `code-reviewer`, it gets the READ_ONLY permission
profile (only Read, Grep, Glob, Bash). The Claude model inside then repeatedly
fails trying to use Edit/Write tools, wasting tokens and never completing the task.

By contrast, other specialist keywords (PLANNER, QA_AUDITOR, SPEC_VERIFIER,
UX_REVIEWER) already use multi-word phrases and do not suffer from this problem.

## Root Cause

`REVIEWER_KEYWORDS` and `DESIGNER_KEYWORDS` are the only keyword lists that use
single words. All other specialist keyword lists use multi-word phrases that are
specific enough to avoid false positives.

## Solution

Replace single-word `REVIEWER_KEYWORDS` with multi-word phrases that specifically
indicate a review/verification task, not an implementation task that happens to
mention reviewing or checking.

### New REVIEWER_KEYWORDS

```python
REVIEWER_KEYWORDS = [
    "code review", "review code", "review implementation",
    "review changes", "verify implementation", "verify changes",
    "run verification", "check compliance", "compliance check",
    "regression test", "regression check",
]
```

### New DESIGNER_KEYWORDS

Similarly tighten `DESIGNER_KEYWORDS` to prevent false positives (e.g., "implement
design system" matching "design"):

```python
DESIGNER_KEYWORDS = [
    "system design", "design document", "architecture design",
    "wireframe", "layout design", "mockup",
    "data model design", "api design",
]
```

### Key design decisions

1. Multi-word phrases are specific enough to match actual review/design tasks
   while avoiding false positives on implementation tasks
2. The priority ordering of keyword checks remains unchanged
3. Tasks that explicitly set `agent: code-reviewer` in the YAML are unaffected
   (inference only runs when no agent is specified)
4. The FALLBACK_AGENT_NAME ("coder") remains the default when no keywords match

## Files to Modify

- `scripts/plan-orchestrator.py` - Update REVIEWER_KEYWORDS and DESIGNER_KEYWORDS
  constants, update docstring for `infer_agent_for_task()`
- `tests/test_spec_verifier_ux_reviewer.py` - Update existing tests that rely on
  single-word keyword matching; add false-positive regression tests
- `tests/test_qa_auditor_integration.py` - Verify no tests break from the change

## Test Plan

1. Existing specialist keyword tests (planner, qa-auditor, spec-verifier,
   ux-reviewer, frontend-coder) should continue to pass unchanged
2. Update tests that relied on single-word reviewer/designer matching
3. Add regression tests for the false-positive scenarios:
   - Task with "check" in implementation context -> should infer "coder"
   - Task with "review" in UI context -> should infer "coder"
   - Task with "validate" in form context -> should infer "coder"
   - Task with "code review" -> should still infer "code-reviewer"
   - Task with "system design" -> should still infer "systems-designer"

## Risk Assessment

- **Low risk**: Only affects tasks without an explicit `agent:` field in YAML
- **Backward compatibility**: Plans with explicit agent assignments are unaffected
- **False negatives**: Some legitimate review tasks that only use single words
  (e.g., task named just "Review") will now fall through to "coder". This is
  acceptable because: (a) it is far less harmful (coder has superset permissions),
  and (b) plans should use explicit `agent: code-reviewer` for review tasks
