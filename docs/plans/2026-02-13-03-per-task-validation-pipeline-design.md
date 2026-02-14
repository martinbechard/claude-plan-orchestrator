# Per-Task Validation Pipeline - Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use the implement skill to execute this plan task-by-task.

**Goal:** Extend the item-level verify-then-fix cycle to work at the individual task level within the orchestrator, spawning a validator agent after each implementation task to independently verify the result and retrying with findings if validation fails.

**Architecture:** After a coder task completes successfully, the orchestrator optionally spawns a validation pass using the validator agent. The validator runs the code-reviewer agent on the task's output, then aggregates findings into a PASS/WARN/FAIL verdict. On FAIL, the task is retried with findings prepended to the prompt. On WARN, the task is marked completed with warnings logged. On PASS, the task proceeds normally. Validation is opt-in via plan meta configuration.

**Tech Stack:** Python 3 (plan-orchestrator.py), YAML (plan meta.validation configuration), Markdown (agent definitions in .claude/agents/)

---

## Architecture Overview

### Dependency: Feature 02 (Agent Definition Framework)

This feature depends on the agent definition framework introduced by Feature 02. Specifically:
- Agent markdown files in .claude/agents/ with YAML frontmatter
- load_agent_definition() function in plan-orchestrator.py
- build_claude_prompt() with agent content injection

### Validation Flow

The validation pipeline inserts into the existing task execution flow:

    1. Task executes (coder agent) -> TaskResult.success = True
    2. Check if validation is enabled for this task type
    3. If enabled: spawn validator agent with task context
    4. Parse validator output for PASS/WARN/FAIL verdict
    5. On PASS: mark task completed (normal flow)
    6. On WARN: mark task completed, log warnings
    7. On FAIL: mark task pending, prepend findings to next attempt

### ValidationConfig Dataclass

New dataclass to hold per-plan validation settings:

    @dataclass
    class ValidationConfig:
        """Configuration for per-task validation."""
        enabled: bool = False
        run_after: list[str]           # Agent types that trigger validation
        validators: list[str]          # Validator agent names to run
        max_validation_attempts: int = 1  # How many validation retries per task

Default run_after: ["coder"]
Default validators: ["validator"]

Parsed from plan meta.validation:

    meta:
      validation:
        enabled: true
        run_after:
          - coder
        validators:
          - validator

### Validation Verdict

    @dataclass
    class ValidationVerdict:
        """Result of a validation pass."""
        verdict: str     # "PASS", "WARN", or "FAIL"
        findings: list[str]
        raw_output: str

The verdict is extracted from the validator's stdout using a regex pattern matching:

    **Verdict: PASS**  or  **Verdict: WARN**  or  **Verdict: FAIL**

    **Findings:**
    - [PASS|WARN|FAIL] Description with file:line references

### Validator Agent Definition

New agent file: .claude/agents/validator.md

The validator agent:
1. Receives the task description and the task result
2. Runs build and test commands to verify the task output
3. Checks that the task requirements from the description are met
4. Produces a structured PASS/WARN/FAIL verdict

The validator is read-only (like code-reviewer) and uses the same output format as the VERIFICATION_PROMPT_TEMPLATE in auto-pipeline.py.

### Issue Verifier Agent Definition

New agent file: .claude/agents/issue-verifier.md

Specialized for defect fix verification:
1. Reads the original defect file
2. Checks whether the reported symptoms are resolved
3. Runs targeted tests mentioned in the defect file
4. Produces a PASS/FAIL verdict with specific evidence

### Validation Prompt Template

The orchestrator builds a validation prompt that includes:
1. The validator agent content (prepended, like any agent)
2. The original task description
3. The task result message
4. The files that were expected to be modified
5. Build and test commands from orchestrator config

Template:

    You are validating the results of task {task_id}: {task_name}

    ## Original Task Description
    {task_description}

    ## Task Result
    Status: {result_status}
    Message: {result_message}

    ## Validation Checks
    1. Run: {build_command}
    2. Run: {test_command}
    3. Verify the task description requirements are met
    4. Check for regressions in related code

    ## Output Format
    Produce your verdict in this exact format:

    **Verdict: PASS** or **Verdict: WARN** or **Verdict: FAIL**

    **Findings:**
    - [PASS|WARN|FAIL] Description with file:line references

### Retry-with-Findings

When a task fails validation, the orchestrator:
1. Extracts the validation findings
2. Prepends them to the task prompt for the next attempt
3. The prepended block uses this format:

        ## PREVIOUS VALIDATION FAILED

        The previous attempt at this task was completed but failed validation.
        You must address these findings:

        {validation_findings}

        ---

This is stored in a new task field: task["validation_findings"] which build_claude_prompt() checks and includes if present.

### Orchestrator Integration Points

1. **run_orchestrator() sequential block (line ~2049):** After task_result.success is confirmed, check if validation is enabled for this task's agent type. If so, run the validation pass.

2. **run_orchestrator() parallel block (line ~1830):** After parallel results are collected, validate each successful task sequentially (validators should not run in parallel to avoid conflicting state).

3. **build_claude_prompt() (line ~1198):** Check for task["validation_findings"] and prepend them to the prompt.

---

## Key Files

### New Files

| File | Purpose |
|------|---------|
| .claude/agents/validator.md | Post-task verification coordinator agent |
| .claude/agents/issue-verifier.md | Defect fix verification specialist agent |

### Modified Files

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Add ValidationConfig, ValidationVerdict, validation logic in task loop |

---

## Design Decisions

1. **Validation is opt-in via plan meta.** Most plans do not need per-task validation. The overhead of spawning a validator agent for every task would double execution time. Plans that benefit from validation (e.g., defect fixes, critical infrastructure) opt in explicitly.

2. **Validators run sequentially after parallel tasks.** Running validators in parallel with each other could cause conflicting build/test state. Sequential validation is safer and the overhead is acceptable since validation is lighter than implementation.

3. **Retry-with-findings uses a task field, not an external file.** The validation findings are stored in task["validation_findings"] in the plan YAML. This keeps all task state in one place and survives orchestrator restarts.

4. **The validator agent reuses the VERIFICATION_PROMPT_TEMPLATE output format.** The PASS/WARN/FAIL verdict and structured findings format is already proven in the auto-pipeline verifier. Reusing it means parsing logic can be shared.

5. **WARN does not trigger a retry.** Warnings are informational (e.g., "missing docstring", "could improve naming"). Only FAIL triggers a retry. This prevents infinite validation loops over style nits.

6. **max_validation_attempts defaults to 1.** A task gets at most one validation-triggered retry by default. This prevents runaway validate-fix cycles. Combined with the existing max_attempts per task, the total attempts remain bounded.
