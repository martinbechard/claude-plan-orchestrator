---
name: implement
description: Execute implementation tasks from YAML plans or TODO.md. Reads the plan file, picks the next uncompleted task, implements changes, runs tests, writes status file, and marks task complete. (project)
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task
---

# Implementation Agent Skill

## Purpose

This skill executes implementation tasks from YAML plan files (preferred) or TODO.md. It:
1. Reads the plan to find the next uncompleted task
2. Reads relevant architecture and design documents
3. Implements the changes following project coding rules
4. Runs tests and build to verify
5. Writes a status file for the orchestrator
6. Commits changes after completion
7. Marks the task as complete in the plan

## Usage

Invoke with: `/implement` or `/implement [task id]`

## Plan Formats

### YAML Plans (Preferred)

YAML plans live in `.claude/plans/` and are executed by `scripts/plan-orchestrator.py`.

**To run automated execution:**
```bash
# Run all pending tasks
python scripts/plan-orchestrator.py --plan .claude/plans/<plan-name>.yaml

# Run with parallel execution (independent tasks run concurrently)
python scripts/plan-orchestrator.py --plan .claude/plans/<plan-name>.yaml --parallel

# Run single task then stop
python scripts/plan-orchestrator.py --plan .claude/plans/<plan-name>.yaml --single-task

# Resume from specific task
python scripts/plan-orchestrator.py --plan .claude/plans/<plan-name>.yaml --resume-from 4.7

# Verbose with real-time streaming
python scripts/plan-orchestrator.py --plan .claude/plans/<plan-name>.yaml --verbose
```

**YAML Plan Structure:**
```yaml
meta:
  name: Feature Name
  description: What this plan accomplishes
  plan_doc: docs/plans/YYYY-MM-DD-feature-design.md
  created: 'YYYY-MM-DD'
  max_attempts_default: 3
  notification_email: user@example.com
sections:
- id: phase-1
  name: Phase Name
  status: pending  # pending | in_progress | completed | failed
  tasks:
  - id: '1.1'
    name: Task Name
    status: pending
    description: What this task does
    max_attempts: 3          # optional, overrides default
    depends_on: ['1.0']      # optional, wait for these tasks
    parallel_group: group-1  # optional, same group = run in parallel
    exclusive_resources:      # optional, prevents parallel with same resource
    - database
```

### TODO.md (Legacy)

Simple markdown checklist format:
```markdown
## Phase 1
- [ ] Task 1.1: Description
- [x] Task 1.2: Completed task
- [DONE] Task 1.3: Also completed
```

## Workflow for YAML Plans

### Step 1: Check for YAML Plan

Look for active YAML plans in `.claude/plans/`:
```bash
ls -la .claude/plans/*.yaml
```

### Step 2: Find Next Task

Read the plan and find the first task with `status: pending` or `status: in_progress`.

### Step 3: Read Context

Before implementing, ALWAYS read:
1. `procedure-coding-rules.md` - coding standards
2. The `plan_doc` referenced in meta - detailed design
3. Relevant files in `design/architecture/` and `design/modules/`

### Step 4: Implement Changes

- Follow procedure-coding-rules.md guidelines
- Use existing patterns from the codebase
- Prefer editing existing files over creating new ones

### Step 5: Verify Changes

```bash
pnpm run build
pnpm test
```

### Step 6: Write Status File

**CRITICAL**: Write status to `.claude/plans/task-status.json`:

```json
{
  "task_id": "4.7",
  "status": "completed",
  "message": "Brief description of what was done",
  "timestamp": "2025-01-19T12:00:00Z",
  "plan_modified": false
}
```

For failures:
```json
{
  "task_id": "4.7",
  "status": "failed",
  "message": "What went wrong and why",
  "timestamp": "2025-01-19T12:00:00Z",
  "plan_modified": false
}
```

### Step 7: Commit Changes

```bash
git add -A
git commit -m "feat: Task description

- What changed
- Why it changed

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

### Step 8: Update Plan (if not using orchestrator)

If running manually (not via orchestrator), update the task status in the YAML:
```yaml
- id: '4.7'
  status: completed
  completed_at: '2025-01-19T12:00:00'
  result_message: Brief description
```

## Plan Modification

You MAY modify the YAML plan if needed:
- **Split a task** that's too large (e.g., 5.2 -> 5.2a, 5.2b)
- **Add a task** if something is missing
- **Skip a task** by setting `status: skipped` with a reason
- **Add notes** with important context

If you modify the plan, set `plan_modified: true` in the status file.

## Important Rules

1. ALWAYS read procedure-coding-rules.md before generating code
2. NEVER use `any` types - create proper TypeScript types
3. Use RSC and APIs instead of server actions for mutations
4. Fix ALL test failures before marking complete
5. If build fails, fix the errors before proceeding
6. Keep changes minimal and focused on the task
7. ALWAYS write the status file when done
8. COMMIT after completing each task

## Error Handling

If the task fails:
1. Write status file with `status: failed` and clear message
2. Document what went wrong
3. The orchestrator will retry (up to max_attempts)
4. After max attempts, manual intervention required

## Creating New YAML Plans

To create a new plan:
1. Write detailed design to `docs/plans/YYYY-MM-DD-feature-design.md`
2. Create YAML plan in `.claude/plans/<feature>.yaml`
3. Reference the design doc in `meta.plan_doc`
4. Break work into sections and tasks
5. Run orchestrator to execute

Example command to start:
```bash
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml --dry-run
```
