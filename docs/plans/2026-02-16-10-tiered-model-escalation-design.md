# Tiered Model Selection with Cost-Aware Escalation - Design Document

**Goal:** Add dynamic model escalation to the orchestrator so agents start with cost-efficient models and automatically escalate to more capable ones when tasks fail repeatedly.

**Architecture:** Define a fixed model tier ladder (haiku -> sonnet -> opus). Add an EscalationConfig dataclass parsed from plan YAML meta.model_escalation. Add a compute_effective_model() function that takes the agent's starting model and the task's current attempt count, returning the correct model for this attempt. Pass the effective model to the Claude CLI via the --model flag in all execution paths (sequential, parallel, validation). Add a validation_model override so validators always use a cost-efficient model regardless of escalation.

**Tech Stack:** Python 3 (plan-orchestrator.py), YAML (plan meta.model_escalation configuration), agent frontmatter (escalation overrides)

---

## Architecture Overview

### Dependencies

- Feature 02 (Agent Definition Framework): Agent model field must exist in frontmatter (already implemented)
- Feature 06 (Token Usage Tracking): Per-task cost tracking for model visibility (already implemented)

### Model Tier Ladder

A fixed, ordered list of model tiers:

    MODEL_TIERS: list[str] = ["haiku", "sonnet", "opus"]

The ladder defines escalation order. To find the next tier, look up the current model's index and increment by one, capped at the max_model ceiling.

### EscalationConfig Dataclass

New dataclass to hold escalation configuration, placed after BudgetGuard in plan-orchestrator.py:

    DEFAULT_ESCALATE_AFTER_FAILURES = 2
    DEFAULT_MAX_MODEL = "opus"
    DEFAULT_VALIDATION_MODEL = "sonnet"
    DEFAULT_STARTING_MODEL = "sonnet"

    @dataclass
    class EscalationConfig:
        """Model escalation configuration for cost-aware tier promotion."""
        enabled: bool = False
        escalate_after: int = DEFAULT_ESCALATE_AFTER_FAILURES
        max_model: str = DEFAULT_MAX_MODEL
        validation_model: str = DEFAULT_VALIDATION_MODEL
        starting_model: str = DEFAULT_STARTING_MODEL

        def get_effective_model(self, agent_model: str, attempt: int) -> str:
            """Compute the effective model for a given agent and attempt number.

            If escalation is disabled, returns the agent_model unchanged.
            Otherwise, promotes up the tier ladder based on attempt count.
            """
            if not self.enabled:
                return agent_model
            base = agent_model or self.starting_model
            if base not in MODEL_TIERS:
                return base  # Unknown model, don't escalate
            base_idx = MODEL_TIERS.index(base)
            max_idx = MODEL_TIERS.index(self.max_model) if self.max_model in MODEL_TIERS else len(MODEL_TIERS) - 1
            # How many escalation steps?
            steps = max(0, (attempt - 1) // self.escalate_after)
            effective_idx = min(base_idx + steps, max_idx)
            return MODEL_TIERS[effective_idx]

Escalation math:
- attempt 1..N where N=escalate_after: use base model
- attempt N+1..2N: use next tier
- attempt 2N+1..: use next tier again, capped at max_model

### Configuration Sources

Configuration comes from three places (in priority order):

1. **Plan YAML meta.model_escalation** (plan-level defaults):

       meta:
         model_escalation:
           enabled: true
           escalate_after: 2
           max_model: opus
           validation_model: sonnet

2. **Agent frontmatter** (per-agent starting model):

       ---
       model: sonnet
       ---

   The agent's model field is used as the starting model for escalation.

3. **Defaults** (if neither plan nor agent specifies): escalation disabled, models unchanged.

Plan-level config controls the escalation behavior. Agent frontmatter controls the starting point. There is no per-agent escalation override in the first version to keep things simple.

### parse_escalation_config Helper

    def parse_escalation_config(plan: dict) -> EscalationConfig:
        """Parse model escalation config from plan YAML meta."""
        esc_meta = plan.get("meta", {}).get("model_escalation", {})
        if not esc_meta:
            return EscalationConfig()
        return EscalationConfig(
            enabled=esc_meta.get("enabled", False),
            escalate_after=esc_meta.get("escalate_after", DEFAULT_ESCALATE_AFTER_FAILURES),
            max_model=esc_meta.get("max_model", DEFAULT_MAX_MODEL),
            validation_model=esc_meta.get("validation_model", DEFAULT_VALIDATION_MODEL),
            starting_model=esc_meta.get("starting_model", DEFAULT_STARTING_MODEL),
        )

### Validation Model Override

Validation agents (code-reviewer, validator, issue-verifier) always use escalation_config.validation_model, ignoring escalation. This is because validators perform structured checks (not open-ended reasoning) where a cheaper model is sufficient.

The determination of whether an agent is a "validator" is based on the existing run_after list in ValidationConfig. If the task's agent name is NOT in run_after, the task itself is a validator.

### run_claude_task Changes

The key change: run_claude_task() accepts a new optional model parameter:

    def run_claude_task(prompt: str, dry_run: bool = False, model: str = "") -> TaskResult:

When model is non-empty, add --model {model} to the CLI command:

    cmd = [*CLAUDE_CMD, "--dangerously-skip-permissions", "--print", prompt]
    if model:
        cmd.extend(["--model", model])

This is passed in three execution paths:

1. **Sequential path** (run_orchestrator main loop, line ~2821): Compute effective model before calling run_claude_task()
2. **Parallel path** (run_parallel_task, line ~1711): Add --model to the subprocess command
3. **Validation path** (run_validation, which calls run_claude_task): Use validation_model

### Orchestrator Integration

In run_orchestrator(), before calling run_claude_task for each task:

1. Resolve the agent name and load its definition to get agent_model
2. Determine if this is a validator task (agent_name NOT in validation_config.run_after):
   - If validator: effective_model = escalation_config.validation_model
   - If regular task: effective_model = escalation_config.get_effective_model(agent_model, current_attempts + 1)
3. Log the model selection: "Task X.Y attempt N: using {model}" (or "escalating from {base} to {model}" when escalated)
4. Pass effective_model to run_claude_task()

### Usage Report Enhancement

The usage report (from Feature 06) already records per-task cost. This feature enhances it by recording the model used per task attempt. Add a model field to the task record in the usage report:

    task["model_used"] = effective_model

And record the model in the YAML plan task dict:

    task["model_used"] = effective_model

This makes the model used visible in both the usage report JSON and the plan YAML.

---

## Key Files

### Modified Files

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | MODEL_TIERS constant, EscalationConfig dataclass, parse_escalation_config, compute_effective_model in get_effective_model method, --model flag in run_claude_task and parallel runner, validation model override, escalation logging, model_used in usage report |

### New Files

| File | Purpose |
|------|---------|
| tests/test_model_escalation.py | Unit tests for EscalationConfig, parse_escalation_config, model tier computation |

---

## Design Decisions

1. **Fixed tier ladder, not configurable.** The ladder haiku -> sonnet -> opus is hardcoded. There is no need for per-plan custom ladders; the three tiers cover all current Claude models. This simplifies configuration and avoids user errors.

2. **EscalationConfig lives on the plan, not per-agent.** While agents have a starting model, the escalation policy (when to escalate, ceiling) is plan-level. This keeps the configuration in one place and avoids conflicting settings across agents in the same plan.

3. **Escalation uses attempt count, not failure type.** The backlog item mentions "consecutive failures." Since the orchestrator already increments task.attempts on each retry, we use that counter directly. All failures are treated equally (no distinction between rate limits, timeouts, or logical failures).

4. **Validation model is a separate override, not part of escalation.** Validators are not subject to escalation because they perform deterministic checks. The validation_model setting gives explicit control.

5. **Model flag passed via --model CLI argument.** The Claude CLI supports --model to override the default model. This is the cleanest integration point.

6. **No agent frontmatter changes required.** The existing model field in agent frontmatter already serves as the starting model. No new fields are needed in agent definitions.

7. **model_used recorded in plan YAML for observability.** After each task attempt, the model used is written into the task dict. This provides an audit trail visible in the plan file.

8. **Backwards compatible when disabled.** When meta.model_escalation is absent or enabled: false, the orchestrator behaves exactly as before (no --model flag is passed, Claude uses its default).
