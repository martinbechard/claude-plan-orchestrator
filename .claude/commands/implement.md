---
description: Execute implementation tasks from YAML plans
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task
---

# /implement Command

Execute the next pending task from the active YAML plan.

## Usage

- `/implement` - Run next pending task
- `/implement 2.1` - Run specific task by ID

## Workflow

1. Read the active plan from `.claude/plans/current-plan.yaml`
2. Find the next task with `status: pending` or `status: in_progress`
3. Read the design document referenced in `meta.plan_doc`
4. Implement the changes following project coding rules
5. Run build/tests to verify
6. Write status to `.claude/plans/task-status.json`:
   ```json
   {
     "task_id": "X.X",
     "status": "completed",
     "message": "What was done",
     "timestamp": "ISO timestamp",
     "plan_modified": false
   }
   ```
7. Commit changes
8. Update task status in YAML plan

## Important

- ALWAYS write the status file when done
- ALWAYS commit after completing a task
- If build fails, fix errors before marking complete
- Set `plan_modified: true` if you modify the YAML plan

$ARGUMENTS
