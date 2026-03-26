# Planner Must Produce Validation Criteria as Checklist with Clear Outcomes - Design

## Overview

The planner agent currently writes acceptance criteria as prose statements, which are
ambiguous enough for the validator to interpret "the page renders" as success even when
data is fake or missing. This fix updates both agent prompts so that (1) the planner
produces binary YES/NO questions for each criterion, and (2) the validator answers each
question literally before rendering its verdict.

## Key Files

| File | Change |
|------|--------|
| `.claude/agents/planner.md` | Add acceptance-criteria format rules: question form, YES/NO outcomes, "independently verifiable" requirement, WARN-only flag for subjective criteria |
| `.claude/agents/validator.md` | Add Step 5d: answer each acceptance-criterion question literally; verdict cannot be PASS if any YES/NO answer is NO |
| `plugin.json` | Patch version bump |
| `RELEASE-NOTES.md` | New entry |

## Design Decisions

**Question form, not prose**: Each criterion is phrased as a question ("Does X show Y?
YES = pass, NO = fail") so the validator cannot paraphrase its way to PASS.

**WARN-only flag for unverifiable criteria**: Criteria that require manual testing or
subjective judgment (e.g. "looks correct") must be marked WARN-only rather than omitted.
This preserves the checklist completeness while not creating false FAILs.

**Validator answers before verdict**: The validator must print the answer (YES/NO) for
every criterion before it can produce a verdict. A single NO on a binary criterion means
FAIL unless the criterion is flagged WARN-only.

**No schema changes**: Both files are plain markdown prompts; no YAML schema updates are
required. The orchestrator does not inspect criterion text.
