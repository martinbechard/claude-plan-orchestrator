# Fix Subagent Confusion About in_progress Task Status - Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use the implement skill to execute this plan task-by-task.

**Goal:** Eliminate subagent confusion when a task is on its first attempt by making the prompt context-aware about attempt numbers. On attempt 1, the prompt should clarify that in_progress is expected (the orchestrator set it). On attempt 2+, the prompt should explicitly state the retry context.

**Root Cause:** Two things combine: (1) the orchestrator sets task.status = "in_progress" before spawning the subagent, and (2) the prompt always says "a previous attempt may have failed", priming the subagent to treat attempt 1 as a retry.

**Architecture:** Pass the current attempt number into build_claude_prompt and use it to conditionally generate the "verify state" instruction. The attempt number is already tracked in task["attempts"] and is incremented before the prompt is built in both the sequential path (line ~2029) and parallel path (line ~1803).

**Affected Files:**
- scripts/plan-orchestrator.py - build_claude_prompt signature and prompt template

---

## Phase 1: Implementation

### Task 1.1: Update build_claude_prompt to accept and use attempt number

**Files:**
- Modify: scripts/plan-orchestrator.py (lines ~1178-1293)

**Design:**

1. Add an attempt_number parameter to build_claude_prompt:

       def build_claude_prompt(
           plan: dict,
           section: dict,
           task: dict,
           plan_path: str,
           subagent_context: Optional[dict] = None,
           attempt_number: int = 1
       ) -> str:

2. Replace the hardcoded instruction at line ~1265:

       1. First, verify the current state - a previous attempt may have failed

   With attempt-aware text:

   - When attempt_number == 1:

         1. This is a fresh start (attempt 1). The task shows as in_progress because the
            orchestrator assigned it to you. Start working immediately on the task.

   - When attempt_number >= 2:

         1. This is attempt {attempt_number}. A previous attempt failed. Check the current
            state before proceeding - some work may already be done.

3. Update the docstring to document the new parameter.

### Task 1.2: Pass attempt number from both call sites

**Files:**
- Modify: scripts/plan-orchestrator.py (lines ~1073, ~2040)

**Design:**

At the sequential execution call site (line ~2040), the attempt number is already computed as current_attempts + 1 (incremented at line ~2029 into task["attempts"]). Pass it:

    prompt = build_claude_prompt(plan, section, task, plan_path,
                                 attempt_number=task.get("attempts", 1))

At the parallel execution call site (line ~1073), the attempt number was already incremented at line ~1803. Pass it:

    prompt = build_claude_prompt(plan, section, task, plan_path, subagent_context,
                                 attempt_number=task.get("attempts", 1))

---

## Phase 2: Verification

### Task 2.1: Verify the fix

**Steps:**
1. Run: python3 -c "import py_compile; py_compile.compile('scripts/plan-orchestrator.py', doraise=True); print('syntax OK')"
2. Run: python scripts/plan-orchestrator.py --plan .claude/plans/sample-plan.yaml --dry-run
3. Verify the prompt text no longer contains "a previous attempt may have failed"
4. Verify the new prompt text is conditioned on the attempt number
