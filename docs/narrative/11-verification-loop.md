# Chapter 11: The Verification Loop

**Period:** 2026-02-13
**Size:** +225 lines added to `scripts/auto-pipeline.py`, +1 line to `scripts/plan-orchestrator.py`

## The Trust Problem

Until now, the auto-pipeline had a simple success model: if the orchestrator exited
cleanly, the defect was fixed. Phase 1 creates the plan, Phase 2 executes it, Phase 3
archives the item. Done.

But "exit code 0" does not mean "bug fixed." A Claude session can compile cleanly, pass
tests, write a status file saying "completed," and still leave the original symptom intact.
The orchestrator was trusting the executor's self-assessment --- like grading your own exam.

The fix: add an independent verifier that checks the *symptoms*, not the *status file*.

## The Verify-Then-Fix Cycle

The auto-pipeline's item processing loop grew from three phases to four, with a retry
mechanism:

```
Phase 1: Create plan         (Claude generates design + YAML plan)
Phase 2: Execute plan         (Orchestrator runs all tasks)
Phase 3: Verify symptoms      (NEW - independent verifier agent)
  |
  +-- PASS --> Phase 4: Archive  (move to completed/)
  |
  +-- FAIL --> Delete stale plan, loop back to Phase 1
               (verifier's findings feed into the next plan)
```

The retry loop runs up to three cycles (MAX_VERIFICATION_CYCLES). Each cycle produces a
fresh plan that incorporates the accumulated verification findings from the defect file.

## The Verifier Agent

The verifier is a read-only Claude session. Its prompt (VERIFICATION_PROMPT_TEMPLATE)
constrains it to three actions: read, run checks, and append findings. It cannot modify
code. It cannot change the defect's status. It produces a structured verdict:

```
### Verification #1 - 2026-02-13 22:05

**Verdict: PASS**

**Checks performed:**
- [x] Build passes
- [x] Unit tests pass
- [x] No hardcoded pnpm in VERIFICATION_PROMPT_TEMPLATE

**Findings:**
(specific command outputs and observations)
```

The verdict line uses a regex-parseable format (`**Verdict: PASS**` or `**Verdict: FAIL**`)
so the pipeline can mechanically determine the outcome without interpreting prose.

## The Feedback Channel

The clever part is how failures feed forward. The verifier *appends* findings to the
defect file's `## Verification Log` section. When the pipeline retries, it deletes the
stale YAML plan and runs Phase 1 again. The plan creator reads the defect file --- including
the verification log --- and produces a plan that addresses the specific failures.

This is inter-agent communication via the filesystem: the verifier writes findings, the
planner reads them, neither knows the other exists. The defect file is the shared memory.

```
Verifier --> appends to defect file --> Plan Creator reads defect file
  ^                                           |
  |                                           v
  +---- Orchestrator executes new plan -------+
```

## PID Tracking

A related change: log messages now include the process ID. What was
`[AUTO-PIPELINE] message` is now `[AUTO-PIPELINE:12345] message`, and child process
spawns/exits are logged with their PIDs:

```
[22:05:51] [AUTO-PIPELINE:48727] Spawned child process PID 84962: Verify 01-...
[22:05:51] [AUTO-PIPELINE:48727] Child PID 84962 exited with code 0 after 96s
```

When multiple auto-pipeline instances run on different projects (sharing the same terminal
host), PID tracking makes it possible to trace which output belongs to which pipeline.
The orchestrator got the same treatment: its startup banner now reads
`=== Plan Orchestrator (PID 12345) ===`.

## The --once Mode Change

The `--once` flag changed from "process all current items" to "process the first item
then exit." The original behavior was designed for batch processing, but in practice
`--once` was used for testing a single item. Processing all items in "once" mode was
confusing because it did not loop but still ran through the entire queue. The new behavior
matches the name: once means one.

## Configurable Build Commands

The verification prompt originally hardcoded `pnpm run build`, `pnpm test`, and `pnpm dev`.
These commands are specific to JavaScript/TypeScript projects and fail on Python-only
repos like the orchestrator itself. The first defect processed by the verification loop
was, fittingly, this very issue.

The fix: three new config keys in orchestrator-config.yaml (`build_command`,
`test_command`, `dev_server_command`) with pnpm defaults for backward compatibility.
Both auto-pipeline.py and plan-orchestrator.py read these from the shared config file.

## First Live Test

The verification loop's inaugural run processed the hardcoded-pnpm defect end-to-end:

- Phase 1: Created a 4-phase, 7-task YAML plan (2 minutes)
- Phase 2: Orchestrator executed all tasks, editing both scripts and config (10 minutes)
- Phase 3: Verifier independently confirmed all three acceptance criteria (2 minutes)
- Phase 4: Archived to completed/ (instant)
- Total: 15 minutes, single cycle, no retries needed

The verifier noted two out-of-scope hardcoded pnpm references (in the plan creation
template and dev server restart logic) but correctly judged them as not relevant to
the defect's scope. This nuanced evaluation is exactly what the verification step
provides that exit-code checking cannot.

## Line Count Update

The auto-pipeline grew from ~1073 lines to ~1450 lines. The orchestrator remains at
~2095 lines. Combined: ~3545 lines of automation managing automation.

```
2026-01-19  Genesis: 454 lines
2026-02-12  Auto-pipeline: 1073 lines (separate script)
2026-02-13  Verification loop: +377 lines across both scripts
Current:    ~2095 lines (orchestrator) + ~1450 lines (auto-pipeline)
```
