# Tiered Model Selection with Cost-Aware Escalation

## Status: Open

## Priority: High

## Summary

Add dynamic model escalation to the orchestrator so agents start with cost-efficient
models and automatically escalate to more capable ones when tasks fail repeatedly.
Today each agent has a static model field (e.g., model: sonnet). This feature makes
that a starting model, with configurable escalation rules that promote to a higher-tier
model after N consecutive failures on the same task.

## Sources

- docs/ideas/e2e-test-protocol.md: "Use sonnet instead of opus for running validations"
  and "For investigating problems, start with Claude sonnet, then after 3 attempts at
  fixing it, use Claude Opus."
- docs/ideas/specialized-agent-architecture.md: Agent model field definitions (haiku for
  quick checks, sonnet for coding, opus for design/complex reasoning).

## Problem

The current model assignment is static per agent definition. This creates two problems:

1. Agents configured for opus spend expensive tokens on tasks that sonnet could handle,
   wasting budget.
2. When a sonnet-configured agent fails repeatedly on a difficult task, there is no
   mechanism to escalate to a more capable model. The same model retries with the same
   limitations.

## Proposed Design

### Model Tier Hierarchy

Define a fixed escalation ladder:

    haiku -> sonnet -> opus

Each agent definition specifies a starting_model (defaults to the current model field).
On failure, the orchestrator promotes to the next tier.

### Escalation Configuration

Add escalation settings to plan meta and agent definitions:

    meta:
      model_escalation:
        enabled: true
        escalate_after: 2          # failures before promoting
        max_model: opus            # ceiling (never escalate beyond this)
        validation_model: sonnet   # override: validators always use this
        checklist_model: haiku     # override: checklist-style tasks use this

Agents can also set escalation in their frontmatter:

    ---
    model: sonnet
    escalation:
      after_failures: 2
      max_model: opus
    ---

Plan-level config overrides agent-level config when both are present.

### Orchestrator Changes

1. Track consecutive failure count per task (already have task.attempts).
2. Before spawning Claude for a task, compute the effective model:
   - If attempts <= escalate_after: use agent starting_model
   - If attempts > escalate_after: use next tier up, capped at max_model
3. Pass the effective model to the Claude CLI via --model flag (overrides
   the agent default).
4. Log model selection: "Task 3.1 attempt 3: escalating from sonnet to opus"

### Validation Model Override

Validation agents (code-reviewer, validator, issue-verifier) use the
validation_model setting regardless of their agent definition. This ensures
validations always run on a cost-efficient model since they perform structured
checks rather than open-ended reasoning.

### Cost Tracking Integration

Works with feature 06 (token usage tracking): the usage report shows which model
was used per task attempt, making cost-per-model visible.

## Verification

- Configure a plan with escalation enabled, escalate_after: 1
- Run a task that fails on sonnet (e.g., a deliberately hard problem)
- Verify the second attempt uses opus
- Verify validators always use the validation_model regardless of escalation
- Verify usage report shows correct model per attempt

## Files Likely Affected

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Model escalation logic in run_task, effective model computation |
| .claude/agents/*.md | Add escalation frontmatter to agent definitions |
| Plan YAML schema | meta.model_escalation configuration block |

## Dependencies

- 02-agent-definition-framework.md (completed): Agent model field must exist
- 06-token-usage-tracking.md (completed): Per-task cost tracking for model visibility
