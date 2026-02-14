# Per-Task Validation Pipeline

## Status: Open

## Priority: Medium

## Summary

Extend the item-level verify-then-fix cycle (already implemented in auto-pipeline.py)
to work at the individual task level within the orchestrator. After each implementation
task completes, spawn a validator agent to independently verify the result. If validation
fails, retry the task with findings appended to the prompt.

This replaces the current "trust the status file" approach with independent verification.

## Scope

### New Agent Definitions

Create agents in .claude/agents/:

1. **validator.md** - Post-task verification coordinator
   - Dispatches relevant sub-validators based on task context
   - Aggregates findings into PASS/WARN/FAIL verdict

2. **issue-verifier.md** - Defect fix verification
   - For tasks fixing defects: independently verifies the defect is resolved
   - Reads the original defect file, checks the fix, runs targeted tests
   - Produces PASS/FAIL with specific evidence

### Orchestrator Changes

1. Add validation config to plan meta schema:
   - validation.enabled (default: false)
   - validation.run_after (which agent types trigger validation)
   - validation.validators (which validators to run)

2. Post-task validation hook: after a coder task completes successfully,
   optionally spawn a validator agent to verify the result

3. PASS/WARN/FAIL verdict aggregation:
   - PASS: task marked completed, continue
   - WARN: task marked completed, warnings logged
   - FAIL: task marked failed, findings appended to retry prompt

4. Retry-with-findings: when a task fails validation, the orchestrator
   retries it with the validation findings prepended to the prompt

### Verification Prompt Reuse

The VERIFICATION_PROMPT_TEMPLATE pattern from auto-pipeline.py can inform the
validator agent design, but the per-task validator operates within the orchestrator
context (not the auto-pipeline).

## Verification

- Create a test plan with validation enabled
- Run a task that deliberately introduces a verifiable issue
- Confirm the validator catches it and the task gets retried with findings
- Confirm PASS verdicts allow tasks to complete normally

## Dependencies

- 02-agent-definition-framework.md
