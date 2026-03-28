# Design: Noisy Log Output From Long Plan Filenames

## Date: 2026-02-17
## Defect: docs/defect-backlog/03-noisy-log-output-from-long-plan-filenames.md
## Status: Draft

## Problem

When plan YAML filenames are long (derived from slugified backlog titles), every
log line in the auto-pipeline output includes the full filename as a prefix. For
example, a plan file named:

```
2-i-want-to-be-able-to-use-separate-slack-channels-depending-on-the-project-by-de.yaml
```

produces log lines like:

```
[14:30:02] [Orchestrator: 2-i-want-to-be-able-to-use-separate-slack-channels-depending-on-the-project-by-de.yaml] ...
```

This causes terminal lines to wrap, burying useful information in noise.

## Architecture Overview

The log prefix flows through this call chain:

```
auto-pipeline.py:
  execute_plan(plan_path)
    -> description = f"Orchestrator: {os.path.basename(plan_path)}"   # line 1148
    -> run_child_process(cmd, description, ...)                        # line 1146
      -> stream_output(pipe, description, collector, show_full)        # lines 653-657
        -> print(f"[{ts}] [{prefix}] {line.rstrip()}")                # line 236
```

Additionally, the orchestrator itself (plan-orchestrator.py) uses a plan name in:
- Usage report filenames (MAX_PLAN_NAME_LENGTH = 50 chars, already truncated)
- Worktree paths (already truncated to 30 chars)
- Slack notifications (uses meta.name, not filename)

The primary fix target is auto-pipeline.py, specifically how it generates the
description passed to run_child_process/stream_output.

## Design Decision

**Option C from the defect report: Use a short abbreviated slug.**

Strategy:
1. Create a helper function that produces a compact plan identifier from a
   filename. The function extracts the numeric prefix plus a short portion of
   the slug, truncated with ellipsis if needed. Maximum length: 30 characters.
   - Example: "2-i-want-to-be-able-to-..." -> "2-i-want-to-be..."
   - Example: "03-per-task-validation-pipeline" -> "03-per-task-validation-pip..."
   - Short filenames remain unchanged: "sample-plan" -> "sample-plan"

2. Print the full plan filename once at the start of execute_plan() for
   reference, then use the compact form in the stream prefix.

3. Apply the same truncation to the description used in run_child_process for
   the create-plan and validate-plan child processes, which also pass long
   descriptions containing the item slug or plan path.

## Files Affected

| File | Change |
|------|--------|
| scripts/auto-pipeline.py | Add compact_plan_label() helper; use it in execute_plan(), create_plan(), and process_item() stream prefixes |
| tests/test_auto_pipeline.py | Add unit tests for compact_plan_label() |

## Detailed Changes

### scripts/auto-pipeline.py

Add a new helper function near the logging section:

```python
MAX_LOG_PREFIX_LENGTH = 30

def compact_plan_label(plan_path: str) -> str:
    """Produce a compact label from a plan filename for log prefixes.

    Strips the .yaml extension and truncates to MAX_LOG_PREFIX_LENGTH chars
    with ellipsis if the basename exceeds the limit.

    Examples:
        "2-i-want-to-be-able-to-use-separate-slack-channels.yaml" -> "2-i-want-to-be-able-to-use..."
        "03-per-task-validation.yaml" -> "03-per-task-validation"
    """
    stem = Path(plan_path).stem
    if len(stem) <= MAX_LOG_PREFIX_LENGTH:
        return stem
    return stem[:MAX_LOG_PREFIX_LENGTH - 3] + "..."
```

Modify execute_plan() (line 1132):
- Add a log line at the start printing the full plan path once
- Change the description to use compact_plan_label()

```python
def execute_plan(plan_path: str, dry_run: bool = False) -> bool:
    label = compact_plan_label(plan_path)
    if dry_run:
        log(f"[DRY RUN] Would execute plan: {plan_path}")
        return True
    log(f"Executing plan: {plan_path}")  # Full path printed once
    ...
    result = run_child_process(
        orch_cmd,
        description=f"Orchestrator: {label}",
        ...
    )
```

Modify create_plan() to also use a compact description for the plan-creation
child process, since it also passes long item slugs.

### tests/test_auto_pipeline.py

Add tests for compact_plan_label():
- Short filenames pass through unchanged (minus .yaml extension)
- Long filenames are truncated with ellipsis
- Edge case: exactly at the limit
- Edge case: no .yaml extension

## Risks

- **None**: This is a display-only change. No behavioral changes to pipeline
  execution, plan resolution, or usage tracking.
- **Low**: The truncated label could make two plans with similar prefixes
  harder to distinguish in logs. Mitigated by printing the full path once at
  plan start.
