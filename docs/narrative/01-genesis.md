# Chapter 1: Genesis

**Commit:** `24076eb` --- 2026-01-19
**Size:** 454 lines, 2 files (+693 lines)
**Title:** "Add plan orchestrator for automated task execution"

## The Problem

By mid-January 2026, the CheapoVille project had accumulated significant
complexity: a program evaluation system with database schema changes, API layers, reporting
frameworks, and UI components. Implementing this as one continuous Claude session was failing.
The LLM would lose track of earlier decisions, contradict its own code, and the quality would
drop noticeably after 3-4 tasks.

The human developer (Martin) recognized the pattern: **LLMs get confused on long-running tasks.**
Context accumulates and degrades quality. The solution was to break the work into discrete tasks,
each executed in a fresh Claude session.

## The Design: Three-Layer Architecture

The orchestrator introduced a clean separation of concerns:

1. **YAML Plan** (the "what") --- A structured document listing sections and tasks with
   dependencies, statuses, and metadata
2. **Claude CLI** (the "do it") --- Each task spawns a fresh `claude --dangerously-skip-permissions
   --print` process
3. **Python Orchestrator** (the "manage it") --- A state machine that walks the plan, dispatches
   tasks, reads results, and handles retries

## The Initial YAML Schema

The first plan (`program-evaluation.yaml`, 239 lines) established the template:

```yaml
meta:
  name: Program Evaluation System
  description: Build systematic program evaluation with AI-assisted reporting
  plan_doc: docs/plans/2025-01-18-program-evaluation-implementation.md
  created: '2025-01-19'
  max_attempts_default: 3
  notification_email: martin.bechard@DevConsult.ca
sections:
- id: epic-1
  name: Foundation
  status: completed
  tasks:
  - id: '1.1'
    name: Database Schema - Programs
    status: completed
    attempts: 1
    description: Add program tracking tables to schema
```

Key decisions:
- **Section/task hierarchy** mirrors epics/stories in agile
- **Status tracking** built into the YAML itself (not a separate database)
- **Attempt counting** enables retry logic
- **plan_doc reference** points Claude at the detailed design document

## The Communication Protocol: task-status.json

The orchestrator and Claude communicate through a JSON status file. Before running a task,
the orchestrator clears the file. Claude is instructed to write it when done:

```json
{
  "task_id": "1.1",
  "status": "completed",
  "message": "Brief description of what was done",
  "timestamp": "2026-01-19T17:30:00Z",
  "plan_modified": false
}
```

The `plan_modified` flag is particularly clever: it tells the orchestrator to reload the YAML
because Claude may have split a large task, added missing tasks, or updated descriptions.
This makes the plan a *living document* that Claude can evolve during execution.

## The Claude Prompt Template

Each task gets a detailed prompt that includes:
- The task ID, section, and description from the YAML
- A reference to the design document
- Step-by-step instructions: verify state, read the plan, implement, build, commit
- Instructions for writing the status file
- Permission to modify the plan itself

```python
def build_claude_prompt(plan, section, task, plan_path):
    return f"""Run task {task['id']} from the implementation plan.

## Task Details
- **Section:** {section['name']} ({section['id']})
- **Task:** {task['name']}
- **Description:** {task.get('description', 'No description')}
- **Plan Document:** {plan_doc}

## Instructions
1. First, verify the current state - a previous attempt may have failed
2. Read the relevant section from the plan document
3. Implement the task following the plan's specifications
4. Run `pnpm run build` to verify no TypeScript errors
5. Commit your changes with a descriptive message
6. Write a status file to `.claude/plans/task-status.json`
...
"""
```

## The Execution Loop

The core loop was straightforward:

1. Find the next pending or in-progress task
2. Build a prompt
3. Spawn `claude --dangerously-skip-permissions --print <prompt>`
4. Wait for completion (600s timeout)
5. Read the status file
6. Update the YAML and commit
7. Repeat

```python
def run_orchestrator(plan_path, dry_run=False, resume_from=None, single_task=False):
    plan = load_plan(plan_path)
    while True:
        result = find_next_task(plan)
        if not result:
            print("All tasks completed!")
            break
        section, task = result
        prompt = build_claude_prompt(plan, section, task, plan_path)
        task_result = run_claude_task(prompt, dry_run=dry_run)
        # Update status, save plan, commit...
```

## What Was Not Yet Present

The initial version was deliberately simple. Missing features that would come later:
- No parallel execution
- No circuit breaker (failures just counted up to max_attempts)
- No dependency checking between tasks
- No graceful stop mechanism
- `claude` binary assumed to be on PATH
- No rate limit handling
- Output captured but not streamed

## Questions

**Q: Why Python instead of a shell script or Node.js?**
CheapoVille is a Next.js/TypeScript application, so Node.js would have been a natural choice.
Python was likely chosen for its superior subprocess management (`subprocess.Popen`), clean
YAML handling (`pyyaml`), and the fact that orchestration logic benefits from Python's
readability. Shell scripts would have been fragile for this level of state management.

**Q: Why `--dangerously-skip-permissions`?**
The orchestrator runs unattended. Each Claude session needs to read files, write code, run
builds, and commit without human approval for each action. The "dangerous" flag name is
appropriate --- this requires trust in the prompt engineering and the plan structure.

**Q: Why 600 seconds timeout?**
This was an empirical choice. Most tasks complete in 1-3 minutes, but complex tasks
(CRUD implementations, E2E tests, UI components) can take longer. The 10-minute ceiling
prevents runaway sessions while giving enough room for legitimate work. Later experience
would show that some tasks (particularly complex E2E tests) would bump against this limit.
