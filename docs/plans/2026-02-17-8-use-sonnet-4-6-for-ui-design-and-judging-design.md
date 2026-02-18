# Feature 8: Use Sonnet 4.6 for UI Design and Judging

## Overview

Sonnet 4.6 is optimized for UI/frontend design work. This feature optimizes
model selection for UI-related tasks across three dimensions:

1. **ux-designer agent** — switch from opus to sonnet (faster, cheaper, better UI design)
2. **frontend-coder agent** — new agent specialized for UI implementation
3. **judge_model meta field** — allow UI-focused design competitions to use sonnet instead of opus for judging

## Architecture

### Existing Agent System

Agents are defined as markdown files with YAML frontmatter in `.claude/agents/`.
The orchestrator's `infer_agent_for_task()` function scans task name + description
for keywords to auto-select the appropriate agent. Priority order matters — more
specific multi-word phrases are checked before single-word keywords.

Current inference priority:
1. PLANNER_KEYWORDS -> planner
2. QA_AUDITOR_KEYWORDS -> qa-auditor
3. SPEC_VERIFIER_KEYWORDS -> spec-verifier
4. UX_REVIEWER_KEYWORDS -> ux-reviewer
5. REVIEWER_KEYWORDS -> code-reviewer
6. DESIGNER_KEYWORDS -> systems-designer
7. Default -> coder

### Changes

#### 1. ux-designer Agent Model Update

`.claude/agents/ux-designer.md` frontmatter: `model: opus` -> `model: sonnet`

Rationale: Sonnet 4.6 is optimized for UI design tasks, produces better visual
designs faster and cheaper. Opus remains appropriate for systems-designer
(architecture requires deeper reasoning).

Note: The README already shows ux-designer as sonnet (documentation drift from
a prior plan). The actual agent file still has opus and must be updated.

#### 2. frontend-coder Agent

New file: `.claude/agents/frontend-coder.md`

Frontmatter:
- name: frontend-coder
- model: sonnet
- tools: Read, Edit, Write, Bash, Grep, Glob (same as coder)
- description: Frontend implementation specialist for UI components, pages, and forms

Role prompt focuses on:
- Component structure and composition
- Accessibility (ARIA, keyboard nav, screen reader)
- Responsive design (mobile-first)
- Design system adherence
- Performance (code splitting, lazy loading)

#### 3. FRONTEND_CODER_KEYWORDS Constant

New keyword list added to `scripts/plan-orchestrator.py` before the DESIGNER_KEYWORDS
check (position 5.5 in priority order, between REVIEWER_KEYWORDS and DESIGNER_KEYWORDS):

```python
FRONTEND_CODER_KEYWORDS = [
    "frontend", "component", "ui component", "page component",
    "form", "dialog", "modal", "ui implementation"
]
```

Priority placement: After REVIEWER_KEYWORDS (single words like "verify" take
precedence), before DESIGNER_KEYWORDS (prevents "component" from matching
"architecture" design tasks).

#### 4. judge_model Meta Field

The YAML plan meta section accepts an optional `judge_model` field:

```yaml
meta:
  judge_model: sonnet   # For UI-focused competitions
  # judge_model: opus   # Default for architecture competitions
```

When present, the orchestrator uses this model for planner tasks that judge
design competitions. The implementation reads `plan.get("meta", {}).get("judge_model")`
and overrides the effective model for tasks with agent type `planner`.

The `build_claude_prompt()` function already passes all plan metadata to the
prompt. Model selection happens at task execution time in the `process_task()`
loop at line ~4582. The judge_model override is applied there: if the task
is a planner task and the plan has judge_model set, use judge_model instead
of the planner agent's default model.

### Template and Documentation Updates

- `scripts/auto-pipeline.py` PLAN_CREATION_PROMPT_TEMPLATE: add frontend-coder
  to agent list, add judge_model example to meta section
- `README.md`: add frontend-coder row to agent table, update inference description,
  add judge_model documentation

## Key Files to Create/Modify

| File | Action |
|------|--------|
| `.claude/agents/ux-designer.md` | Change model: opus -> sonnet |
| `.claude/agents/frontend-coder.md` | Create new agent |
| `scripts/plan-orchestrator.py` | Add FRONTEND_CODER_KEYWORDS, update infer_agent_for_task(), add judge_model override |
| `scripts/auto-pipeline.py` | Update PLAN_CREATION_PROMPT_TEMPLATE |
| `README.md` | Add frontend-coder agent row, update inference description, add judge_model docs |
| `tests/test_spec_verifier_ux_reviewer.py` | Update ux-designer model assertion (opus -> sonnet), add frontend-coder tests |

## Design Decisions

1. **FRONTEND_CODER_KEYWORDS placement** — checked before DESIGNER_KEYWORDS
   to ensure UI implementation tasks route to frontend-coder, not systems-designer.
   Multi-word phrases like "ui component" and "ui implementation" are more specific
   and go first within FRONTEND_CODER_KEYWORDS.

2. **judge_model applies to planner tasks only** — the planner reads competition
   results and produces implementation tasks. Constraining override to planner
   tasks avoids unexpected model changes for other task types.

3. **judge_model has no default** — omitting it means the planner agent's own
   model is used (currently sonnet). Explicit opt-in prevents silent behavior changes.

4. **frontend-coder uses same tool set as coder** — Read, Edit, Write, Bash,
   Grep, Glob. UI tasks need all the same operations as backend tasks.

5. **Test update** — the existing test `test_ux_reviewer_distinct_from_ux_designer`
   asserts `ux_designer["model"] == "opus"`. After this change it must assert sonnet.
   A new test for frontend-coder inference is also required.
