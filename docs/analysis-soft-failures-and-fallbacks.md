# Analysis: Soft Failures, Silent Fallbacks, and Warning-Only Validation

Date: 2026-04-02
Status: ALL CRITICAL, HIGH, and MEDIUM issues FIXED (2026-04-02)

## Executive Summary

A thorough code review of the langgraph_pipeline codebase reveals **50+ instances** where
errors, missing data, or validation failures are handled with silent fallbacks rather than
hard stops. Many of these are benign (e.g., non-critical logging failures), but several are
**critical data-quality bugs** that allow items to be archived as "completed" when no real
work was done, or to proceed through the pipeline with missing prerequisites.

The worst offenders share a common anti-pattern: a function logs a warning and returns an
empty/default value, and the caller treats that as "success" rather than checking for failure.

### Severity Legend

- **CRITICAL** - Item completes pipeline with wrong outcome or no real work done. Must fix.
- **HIGH** - Pipeline proceeds with degraded quality; output is unreliable. Should fix.
- **MEDIUM** - Cost tracking or audit trail is broken; operational concern. Fix when convenient.
- **LOW** - Non-critical operational logging; acceptable for now.
- **OK** - Correct behavior for the situation.

---

## CRITICAL Issues

### C1. Feature archived as "completed" with zero tasks executed
**File:** execute_plan.py:98-100
**Code:** Missing plan_path returns empty dict; pipeline continues to archive.
**What happens:** For features, the archive node sees no failures and archives as "completed."
For defects, verify_fix runs with no changes, returns FAIL, and the item cycles until exhausted.
**Verdict:** BUG. A missing plan_path after plan_creation means something went wrong upstream.
This should set an error field in state so archive classifies it correctly.
**Fix:** Return an error/failure state instead of empty dict. Or: route to END so the item
gets unclaimed and retried.

### C2. Unreadable plan YAML treated as "all tasks complete"
**File:** archival.py:81-83
**Code:** YAML parse error in _find_non_terminal_tasks returns empty list.
**What happens:** Archive node sees no non-terminal tasks, concludes all tasks are done,
archives as "completed."
**Verdict:** BUG. An unreadable plan is not the same as a completed plan. The fallback
should return a sentinel that triggers an error outcome, not an empty list that mimics success.
**Fix:** Return None on error; caller treats None as "unknown state" and archives as exhausted
or returns to backlog.

### C3. Defect archived as success when verification never ran
**File:** edges.py:145-152
**Code:** No verification_history routes directly to archive.
**What happens:** _determine_outcome (archival.py:130-131) returns ARCHIVE_OUTCOME_SUCCESS
when there is no verification history: "No verification history for a defect: treat as success."
**Verdict:** BUG. This is exactly backwards. No verification = unknown, not success. A defect
that was never verified should be archived as "exhausted" or returned to backlog.
**Fix:** Change _determine_outcome to return ARCHIVE_OUTCOME_EXHAUSTED when verification
history is empty for a defect type.

### C4. Missing acceptance criteria silently skipped, item proceeds through planning
**File:** plan_creation.py:259-261
**Code:** No "## Acceptance Criteria" in backlog item, logs info, returns without error.
**What happens:** Plan is created and validated without AC. Downstream execution has no
acceptance criteria to validate tasks against.
**Verdict:** BUG (the one that prompted this analysis). Items without AC should not proceed.
**Fix:** Either hard-fail (return error state) or check the requirements doc as fallback
(Step 4 generates AC). If neither has AC, hard-fail.

### C5. Design validation FAIL does not stop the pipeline
**File:** plan_creation.py:493-537
**Code:** Both Step 5 (design) and Step 6 (plan) validation results are logged but not checked.
**What happens:** An item with a design that fails its own validation proceeds to execution.
Tasks are run against a flawed design.
**Verdict:** BUG. Design validation exists to catch problems before expensive execution.
Ignoring FAIL verdicts defeats the purpose.
**Fix:** On FAIL, either return error state or set a flag that routes the item back for
redesign (with a retry limit to avoid loops).

### C6. Skill-based validation results discarded in requirements node
**File:** requirements.py:497-505, 543-553
**Code:** _run_skill_validation() is called but its return value (valid, cost) is not checked.
**What happens:** Requirements structuring and AC generation validation always "pass" regardless
of the actual verdict.
**Verdict:** BUG. The validation call costs real API money. Discarding the result is both
a waste and a quality gap.
**Fix:** Check the return value. On FAIL, loop back for revision (with retry limit).

### C7. Task not found in plan_data: silently not executed
**File:** parallel.py:412-415 (fan_out)
**Code:** Returns empty list when current_task_id not found. LangGraph routes to fan_in with
no branches.
**What happens:** The task is silently never executed. No failure is recorded in the plan YAML
or task_results. The executor thinks the task completed (fan_in returns).
**Verdict:** BUG. A missing task_id is a state corruption issue. Should raise or mark the task
as failed.
**Fix:** Raise RuntimeError or return a failure state that marks the task as failed in the
plan YAML.

### C8. Defect item returned to wrong backlog (feature) on sidecar read failure
**File:** supervisor.py:176-177
**Code:** On (OSError, json.JSONDecodeError), item_type defaults to "feature".
**What happens:** A defect or investigation item is returned to the feature backlog. On next
scan it is processed with feature routing (no verification cycle, no symptom checking).
**Verdict:** BUG. Defaulting to "feature" is wrong. There is already a slug-based heuristic
at lines 179-184 that could be tried first.
**Fix:** Fall through to the slug-heuristic (lines 179-184) instead of hardcoding "feature".
The slug-heuristic is already the fallback for missing sidecars, so unify the paths.

---

## HIGH Issues

### H1. Max validation attempts -> task promoted to "verified" with WARN
**File:** validator.py:504-511
**Code:** After exceeding max_validation_attempts, task status is set to "verified" with WARN.
**What happens:** A task that never passed validation appears as verified in the plan. The
executor moves on.
**Verdict:** QUESTIONABLE. The intent is to prevent infinite validation loops. But "verified
with WARN" is misleading -- it should be "failed_validation" or at least clearly surfaced in
the item outcome.
**Fix:** Use a distinct status like "validation_exhausted" that is tracked in the final item
report. Or: mark the task as "failed" after N attempts so it shows up in error reporting.

### H2. Missing agent definition -> Claude runs with empty system prompt
**File:** task_runner.py:96-109
**Code:** _load_agent_definition() returns None; caller uses empty string as agent prompt.
**What happens:** Claude runs the task with no agent-specific instructions. Output quality is
unpredictable.
**Verdict:** SHOULD FIX. A missing agent file is a configuration error, not a runtime
condition. Should be caught at startup or at plan validation time.
**Fix:** Fail the task with a clear error message: "Agent file not found: {path}".

### H3. Reviewer failure accepts unvalidated requirements output
**File:** requirements.py:421-427
**Code:** When reviewer LLM call fails, current output is accepted with a note.
**What happens:** Requirements are saved without any review pass. Quality may be poor.
**Verdict:** QUESTIONABLE. Reviewer failure could be transient (quota, timeout). Retrying once
would be better than accepting blindly.
**Fix:** Retry once on transient failure. On persistent failure, accept but tag the item state
so downstream steps know requirements were unreviewed.

### H4. Clause extraction failure -> pipeline continues without clause register
**File:** intake.py:641-650
**Code:** Warning logged, clause_register_path stays empty.
**What happens:** The traceability chain (Clause -> UseCase -> AC -> Design) is broken from
Step 1. All downstream traceability validation is meaningless.
**Verdict:** SHOULD FIX. If the clause register cannot be produced, the structured requirements
will lack traceability. Better to retry or fail the intake.
**Fix:** Retry once. On persistent failure, route to archive with "intake_failed" outcome.

### H5. 5-Whys failure -> pipeline continues without root cause analysis
**File:** intake.py:690-693
**Code:** _report_intake_error() called but pipeline continues.
**What happens:** Requirements structuring runs without root cause context for defects.
**Verdict:** MEDIUM-HIGH. For defects specifically, 5-Whys is important for fix quality.
For features/investigations, this step may be optional.
**Fix:** For defect items, treat 5-Whys failure as a hard stop. For other types, acceptable
to continue.

### H6. Validation step FAIL results are warning-only throughout intake
**File:** intake.py:663-668, 714-718, 724-726
**Code:** _validate_with_skill() FAIL verdicts logged as warnings, pipeline continues.
**What happens:** Bad clause registers and 5-Whys outputs are accepted and used for downstream
structuring.
**Verdict:** SHOULD FIX. These validation steps cost API money. If they fail, the output should
be revised.
**Fix:** On FAIL, retry the generation step once with the validation feedback. On second FAIL,
accept with a quality flag.

### H7. AC generation failure -> requirements saved without AC Register
**File:** requirements.py:521-524
**Code:** ac_section = "" on failure, requirements saved without AC.
**What happens:** Plan creation cannot reference AC IDs. Validator cannot check acceptance
criteria. Same root issue as C4 but from the generation side.
**Verdict:** SHOULD FIX. AC generation is critical to the pipeline's value proposition.
**Fix:** Retry once. On persistent failure, fail the requirements step.

### H8. Claude verification failure indistinguishable from real FAIL
**File:** verification.py:59-73
**Code:** Timeout/OSError/subprocess failure all return empty string, parsed as FAIL.
**What happens:** A correct fix is marked as FAIL because verification could not run. After
MAX_VERIFICATION_CYCLES such failures, the item is archived as "exhausted."
**Verdict:** SHOULD FIX. Transient failures (timeout, quota) should be retried, not counted
as FAIL. Infrastructure failures should be distinguishable from real verification failures.
**Fix:** Return a distinct outcome like "ERROR" for infrastructure failures. Do not count
ERROR outcomes toward MAX_VERIFICATION_CYCLES.

### H9. Investigation proposals.yaml missing -> infinite suspension loop
**File:** investigation.py:327-332
**Code:** load_proposals() returns None, node returns should_stop=True. Item stays claimed.
**What happens:** On next scan the item is re-processed, hits same branch, suspends again.
Infinite loop unless manually unclaimed.
**Verdict:** BUG. Should either retry with backoff or fail after N attempts.
**Fix:** Track retry count in state. After N failures, archive as "investigation_failed".

### H10. Slack posting failure -> infinite suspension loop
**File:** investigation.py:339-344
**Code:** post_proposals() returns None, node returns should_stop=True.
**What happens:** Same infinite loop as H9.
**Verdict:** BUG. Same fix needed: retry count + eventual failure.
**Fix:** Same as H9.

---

## MEDIUM Issues

### M1. Cost tracking lost on Claude timeout/spawn failure
**Files:** task_runner.py:382-387, parallel.py:325-330
**Code:** Returns cost_usd=0.0, input_tokens=0, output_tokens=0 on failure.
**What happens:** Actual API spend is not tracked. Total cost reporting is understated.
**Verdict:** ACCEPTABLE but annoying. The API was called and charged; the cost is lost.
**Fix:** If the result_capture partial data is available, extract what cost data exists.

### M2. Agent model fallback to "sonnet" on file read failure
**File:** task_selector.py:194-205
**Code:** Unreadable agent file silently defaults model to "sonnet".
**What happens:** An agent that specifies opus or haiku runs on sonnet instead.
**Verdict:** SHOULD LOG WARNING. A permissions issue on an agent file is a config error.
**Fix:** Log a warning (currently silent). Consider failing the task.

### M3. Worktree status file unreadable -> bare except Exception
**File:** parallel.py:349-352
**Code:** All exceptions swallowed, returns None.
**What happens:** Task marked as failed even if it succeeded but the status file had a
transient read error.
**Verdict:** SHOULD NARROW EXCEPTION. Catch OSError only, not Exception.
**Fix:** except OSError instead of except Exception.

### M4. Plan cost JSON parse failure -> cost data lost
**File:** plan_creation.py:415-421
**Code:** except (json.JSONDecodeError, TypeError): pass
**What happens:** Planner cost/token stats not reported to dashboard.
**Verdict:** ACCEPTABLE. Non-critical operational data.
**Fix:** Log at warning level so it is visible.

### M5. Workspace artifact copy failures throughout pipeline
**Files:** plan_creation.py:551-557, requirements.py:493-494, scan.py:218-222
**Code:** except OSError: pass in all cases.
**What happens:** Workspace is missing copies of artifacts. Non-fatal but degrades debugging.
**Verdict:** ACCEPTABLE. Workspace copies are convenience; originals are authoritative.
**Fix:** Log at warning level.

### M6. record_artifact failure silently swallowed
**File:** plan_creation.py:558-564
**Code:** except Exception: pass
**What happens:** Freshness tracking broken; future restarts cannot detect staleness.
**Verdict:** SHOULD LOG WARNING. Staleness tracking is operationally important.
**Fix:** Log warning, narrow to OSError.

### M7. _plan_has_pending_tasks returns False on any error
**File:** worker.py:250-253
**Code:** except (OSError, Exception): pass returns False.
**What happens:** During crash recovery, graph is not re-invoked even if plan has pending tasks.
**Verdict:** SHOULD FIX for crash recovery reliability.
**Fix:** On parse error, return True (assume pending) as the safe default. Better to re-invoke
unnecessarily than to abandon pending tasks.

### M8. Defect symptom check failure -> continues with threshold defaults
**File:** intake.py:789-794
**Code:** On failure, clarity is set to INTAKE_CLARITY_THRESHOLD (passing), reproducible="unclear".
**What happens:** A defect with unclear symptoms passes intake as if symptoms were verified.
**Verdict:** QUESTIONABLE. Defaulting to "passing" on failure defeats the clarity check.
**Fix:** Default clarity to 0 (failing), not INTAKE_CLARITY_THRESHOLD. Let the item be
re-evaluated rather than silently passing.

---

## LOW Issues (Acceptable)

### L1. Streaming output bare except Exception: pass
**Files:** claude_cli.py:272, 371
**Verdict:** OK. Streaming is best-effort; the process exit code is the authoritative signal.

### L2. _report_quota_exhausted / _report_worker_stats failure
**Files:** claude_cli.py:62-63, 91-93
**Verdict:** OK. Dashboard reporting is non-critical. Could log at debug level.

### L3. _save_subprocess_output / _report_intake_error failure
**Files:** intake.py:443-444, 423-425
**Verdict:** OK. Logging failures during error reporting. Not much can be done.

### L4. _write_task_log broad except Exception
**File:** task_runner.py:272-279
**Verdict:** OK. Prints to stdout, task continues. Log write is non-critical.

### L5. _stop_dev_server swallows OSError
**File:** task_runner.py:495-515
**Verdict:** OK. Server cleanup is best-effort. Process will die with parent.

### L6. Git archival commit failure
**File:** archival.py:323-324
**Verdict:** OK. File move already happened; commit is convenience. Next commit picks it up.

### L7. _strip_trace_id_line OSError at debug level
**File:** archival.py:284-292
**Verdict:** OK. Cosmetic cleanup, non-critical.

### L8. _write_throttle IOError swallowed
**File:** intake.py:228-230
**Verdict:** LOW RISK. Throttle counter is a safety valve, not a correctness requirement.
If it fails to persist, the worst case is extra intakes within the hour.

### L9. RAG dedup except Exception: pass
**File:** intake.py:327-329
**Verdict:** OK. Comment explicitly notes this is intentional. Dedup is optimization only.

### L10. _cleanup_worker_db OSError warning
**File:** worker.py:229-230
**Verdict:** OK. Stale DB files accumulate but do not affect correctness.

### L11. _write_result OSError
**File:** worker.py:203-207
**Verdict:** OK. Supervisor handles missing result files via crash recovery path.

### L12. _save_worker_pid_to_sidecar / _save_worker_pid_to_plan OSError
**File:** supervisor.py:111, 129
**Verdict:** ACCEPTABLE. Crash recovery is degraded but not broken; supervisor detects
orphans via other signals.

### L13. _cleanup_orphaned_plan_yamls copy failure
**File:** supervisor.py:250-253
**Verdict:** LOW RISK. Plan is deleted without backup. Plans are reproducible via re-planning.

### L14. _missing source item in archival
**File:** archival.py:142-143
**Verdict:** OK. Item was already moved/deleted; nothing to do.

### L15. route_after_requirements: missing requirements_path routes to END
**File:** edges.py:79-82
**Verdict:** OK. This is the correct protective behavior. Item is unclaimed on restart.

### L16. Validator agent file missing -> empty body
**File:** validator.py:89-102
**Verdict:** Same class as H2. Should fail the validation step, not run with empty instructions.

### L17. _save_validation_result bare except Exception
**File:** validator.py:358-359
**Verdict:** LOW. Validation result is in state; the file copy is for debugging.

### L18. No current_task_id in validator -> returns PASS
**File:** validator.py:458-460
**Verdict:** QUESTIONABLE but probably OK. This is called when there is no task to validate
(e.g., executor finished). Returning PASS prevents spurious failures.

### L19. route_after_intake: missing clause_register_path warning-only
**File:** edges.py:52-54
**Verdict:** Same root cause as H4. If clause extraction failed, this warning fires.
The fix belongs in intake.py, not in the edge routing.

---

## Recommendations: Priority Fix Order

### Immediate (data integrity)
1. **C3** - Defect archived as success without verification (one-line fix in _determine_outcome)
2. **C2** - Unreadable YAML = "all complete" (change return [] to return None + caller check)
3. **C1** - Missing plan_path = silent skip (return error state)
4. **C4** - Missing AC = silent skip (hard fail or check requirements doc)
5. **C8** - Defect -> feature backlog on sidecar error (fall through to slug heuristic)
6. **C7** - Task not found = silently not executed (raise or fail)

### Short-term (quality gates)
7. **C5** - Design validation FAIL ignored (check return value, block on FAIL)
8. **C6** - Skill validation results discarded (check return value)
9. **H1** - Validation exhaustion disguised as WARN/verified
10. **H2** - Missing agent file = empty prompt
11. **H8** - Verification infra failure = real FAIL
12. **H9/H10** - Investigation infinite suspension loops

### Medium-term (pipeline robustness)
13. **H4/H6** - Intake validation failures warning-only
14. **H7** - AC generation failure
15. **H3** - Reviewer failure accepts blindly
16. **H5** - 5-Whys failure for defects
17. **M7** - Crash recovery returns False on error
18. **M8** - Symptom check defaults to passing
