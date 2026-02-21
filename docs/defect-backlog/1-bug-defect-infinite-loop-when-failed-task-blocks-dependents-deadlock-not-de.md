# :bug: *Defect: Infinite loop when failed task blocks dependents (deadlock not de

## Status: Open

## Priority: Medium

## Summary

**Title:** Detect and halt deadlocked plans where failed tasks block all remaining dependents

**Classification:** defect - The system enters an infinite resource-wasting loop due to missing state detection logic in two components that should handle this scenario.

**5 Whys:**

1. **Why does the pipeline loop infinitely?** Because `auto-pipeline.py`'s `find_in_progress_plans()` keeps finding the plan as "in progress" (it has completed + pending tasks) and resumes the orchestrator, which exits 0, which causes the pipeline to resume it again.

2. **Why does the orchestrator exit 0 when no progress can be made?** Because when `find_next_task()` returns `None`, the orchestrator assumes "All tasks completed!" and exits successfully. It doesn't distinguish between "nothing left to do because everything is done" and "nothing left to do because a failed task is blocking all remaining work."

3. **Why doesn't `find_next_task()` distinguish deadlock from completion?** Because it only searches for the next runnable task — it skips failed tasks and skips pending tasks with unmet dependencies, returning `None` in both "all done" and "deadlocked" cases without communicating which scenario occurred.

4. **Why isn't there a separate deadlock detection check after `find_next_task()` returns None?** Because the orchestrator was built with the implicit assumption that plans progress linearly — either tasks succeed and unlock dependents, or they fail and the orchestrator exits non-zero from the task execution path. The scenario where a *previously* failed task silently blocks *future* pending tasks was not anticipated.

5. **Why was the "failed task blocks dependents" scenario not anticipated?** Because the system lacks a formal plan-level state machine. There's no explicit transition logic that evaluates overall plan health (e.g., "are there unreachable pending tasks?"). Each component — `find_next_task`, `is_plan_fully_completed`, `find_in_progress_plans` — checks narrow conditions independently, and no component owns responsibility for declaring a plan deadlocked.

**Root Need:** The system needs a plan-level deadlock detector that recognizes when failed tasks make remaining pending tasks unreachable, and propagates that state (`meta.status: failed`) so both the orchestrator and pipeline can halt gracefully.

**Description:**
Add deadlock detection logic: when `find_next_task()` returns None but pending tasks still exist, the orchestrator should check whether those pending tasks are blocked by failed dependencies. If so, it must set `meta.status: failed` in the YAML and exit non-zero. Additionally, `auto-pipeline.py`'s `find_in_progress_plans()` should recognize plans with failed tasks blocking all remaining work and stop resuming them, preventing the infinite spawn loop.

## Source

Created from Slack message by U0AG70DCQ1K at 1771688419.397169.

## Verification Log

### Verification #1 - 2026-02-21 11:25

**Verdict: PASS**

**Checks performed:**
- [x] Build passes (py_compile on both scripts - no errors)
- [x] Unit tests pass (374 passed in 4.00s)
- [x] Deadlock detection function exists in plan-orchestrator.py (detect_plan_deadlock at line 2039)
- [x] Orchestrator calls detect_plan_deadlock when find_next_task returns None (line 5383)
- [x] Orchestrator sets meta.status=failed and exits non-zero on deadlock (lines 5391-5403)
- [x] Pipeline skips plans with meta.status=failed in find_in_progress_plans (line 2030)
- [x] Pipeline treats meta.status=failed as not fully completed in is_plan_fully_completed (line 1751)
- [x] 11 deadlock-specific unit tests in test_plan_orchestrator.py all pass
- [x] 3 pipeline deadlock/failed-plan unit tests in test_auto_pipeline.py all pass

**Findings:**
- detect_plan_deadlock() correctly identifies when all non-terminal tasks (pending/in_progress) are blocked by failed/suspended dependencies. It returns None when the plan is genuinely complete or has runnable tasks, and returns a list of blocked tasks when deadlocked.
- The orchestrator main loop (line 5382-5403) handles the deadlock case: when find_next_task() returns None, it calls detect_plan_deadlock(). If deadlocked, it sets meta.status to "failed", saves the plan with a commit, sends a Slack error notification, and exits with sys.exit(1).
- auto-pipeline.py find_in_progress_plans() (line 2030) skips any plan with meta.status == "failed", preventing re-spawning the orchestrator on deadlocked plans.
- auto-pipeline.py is_plan_fully_completed() (line 1751) returns False for failed plans, preventing them from being archived as if completed.
- Tests cover: empty plans, all-completed plans, pending with no deps (runnable), blocked by failed dep, blocked by suspended dep, mixed runnable+blocked (not a deadlock), multiple blocked tasks, pending-on-pending (not a deadlock), cross-section deadlock, and in_progress task blocked by failed dep.
- The reported symptom (infinite loop where pipeline keeps spawning orchestrator on a deadlocked plan) is fully addressed by both the orchestrator-side detection (exit non-zero) and the pipeline-side guard (skip failed meta.status).
