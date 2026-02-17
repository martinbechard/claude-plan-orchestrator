# Noisy Log Output From Long Plan Filenames

## Status: Open

## Priority: Low

## Summary

The orchestrator log output is excessively noisy when plan YAML filenames are long.
Every log line includes the full plan filename as a prefix, e.g.:

```
[Orchestrator: 2-i-want-to-be-able-to-use-separate-slack-channels-depending-on-the-project-by-de.yaml]
```

This makes the terminal output hard to read, especially when filenames are derived
from long backlog item titles (which become slugified filenames).

## Root Cause

The orchestrator uses the full plan YAML filename as the log line prefix. Plan
filenames are generated from backlog item titles, which can be arbitrarily long.
There is no truncation or abbreviation strategy.

## Symptoms

- Terminal output wraps multiple times per log line
- Useful information (task status, Claude output) is buried in noise
- Hard to visually scan the log for important events

## Proposed Fix

Use a compact representation for the plan identifier in log output:

- Option A: Truncate the filename to a max length (e.g., 30 chars) with ellipsis
- Option B: Use just the numeric prefix (e.g., "Plan 2") during execution, print
  the full name once at plan start
- Option C: Use a short hash or abbreviated slug (e.g., "2-separate-slack-chan...")

The full filename should be printed once at plan start for reference, then use the
compact form for all subsequent log lines.

## Files

- scripts/plan-orchestrator.py (log formatting in run_orchestrator and task execution)
- scripts/auto-pipeline.py (if it also uses the filename as prefix)

## Verification Log

### Verification #1 - 2026-02-17 15:30

**Verdict: PASS**

**Checks performed:**
- [x] Build passes (py_compile on both scripts succeeds)
- [x] Unit tests pass (152 passed in 2.03s)
- [x] No long plan filename used as repeated log prefix in plan-orchestrator.py
- [x] auto-pipeline.py uses compact_plan_label() for all log prefixes
- [x] compact_plan_label() correctly truncates to 30 chars with ellipsis

**Findings:**

1. **py_compile**: Both scripts/auto-pipeline.py and scripts/plan-orchestrator.py compile without errors.

2. **Unit tests**: All 152 tests pass (test_budget_guard, test_completed_archive, test_model_escalation, test_qa_auditor_integration, test_slack_notifier, test_spec_verifier_ux_reviewer, test_token_usage).

3. **Symptom check - auto-pipeline.py**: The compact_plan_label() function (line 183) truncates plan filenames to MAX_LOG_PREFIX_LENGTH=30 chars with ellipsis. All log-prefix usages go through this function:
   - Line 1023: description=f"Plan: {compact_plan_label(item.slug)}"
   - Line 1045: description=f"Validate: {compact_plan_label(item.slug)}"
   - Line 1153/1170: label = compact_plan_label(plan_path), then description=f"Orch: {label}"
   - The full path is printed once on line 1158 (log(f"Executing plan: {plan_path}")) as a one-time informational message, consistent with the proposed fix.

4. **Symptom check - plan-orchestrator.py**: The old [Orchestrator: long-filename.yaml] pattern does NOT exist anywhere in the file. The orchestrator uses Task {task_id} and Section {section_id} style prefixes for its log lines, not the plan filename. The plan filename is only printed once at startup in the header block (line 3888: Plan: {meta.get('name', 'Unknown')}).

5. **Functional test of compact_plan_label**: With input "2-i-want-to-be-able-to-use-separate-slack-channels-depending-on-the-project-by-de.yaml", output is "2-i-want-to-be-able-to-use-..." (30 chars). Short filenames pass through unchanged.

The reported symptoms (terminal wrapping, noisy log output from long filenames) are resolved. The fix implements Option A from the proposed fix (truncate to 30 chars with ellipsis) combined with printing the full name once at plan start.
