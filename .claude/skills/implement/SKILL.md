---
name: implement
description: Execute implementation tasks from YAML plans. Reads the plan file, picks the next uncompleted task, implements changes, runs tests, writes status file, and marks task complete.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task
---

# Implementation Agent Skill

## Purpose

This skill executes implementation tasks from YAML plan files. It:
1. Reads the plan to find the next uncompleted task
2. Reads relevant architecture and design documents
3. Implements the changes following project coding rules
4. Runs tests and build to verify
5. Writes a status file for the orchestrator
6. Commits changes after completion
7. Marks the task as complete in the plan

## Usage

Invoke with: `/implement` or `/implement [task id]`

## YAML Plans

YAML plans live in `.claude/plans/` and are executed by `scripts/plan-orchestrator.py`.

**To run automated execution:**

IMPORTANT: Always launch the orchestrator as a background Bash task using `run_in_background: true`
so it appears in the Claude Code task list. Then monitor it periodically by checking the YAML plan
for task status updates. Never launch with shell `&` --- it won't be tracked.

```bash
# Run all pending tasks sequentially (use run_in_background: true)
python scripts/plan-orchestrator.py --plan .claude/plans/<plan-name>.yaml

# Run with parallel task execution (uses git worktrees)
python scripts/plan-orchestrator.py --plan .claude/plans/<plan-name>.yaml --parallel

# Run single task then stop
python scripts/plan-orchestrator.py --plan .claude/plans/<plan-name>.yaml --single-task

# Resume from specific task
python scripts/plan-orchestrator.py --plan .claude/plans/<plan-name>.yaml --resume-from 4.7

# Dry run to preview execution order
python scripts/plan-orchestrator.py --plan .claude/plans/<plan-name>.yaml --dry-run

# Verbose with real-time streaming
python scripts/plan-orchestrator.py --plan .claude/plans/<plan-name>.yaml --verbose
```

**Monitoring the Orchestrator:**

After launching the orchestrator in the background, check on progress periodically:

```bash
# Quick status: show non-completed tasks
grep -E '(status:|id:)' .claude/plans/<plan>.yaml | paste - - | grep -v completed

# Check if orchestrator process is alive
pgrep -f "plan-orchestrator"

# Check child Claude processes
pgrep -P <orchestrator-pid>

# Check current task status file
cat .claude/plans/task-status.json
```

Check every 2-3 minutes during active execution. Report progress to the user when tasks
complete or if the orchestrator encounters errors (circuit breaker, rate limits, failures).

**Graceful Stop:**
To stop the orchestrator without killing the current task, create a semaphore file:
```bash
touch .claude/plans/.stop
```
The orchestrator checks for this file before starting each new task. The current task
will finish normally, then the orchestrator will exit cleanly. The semaphore file is
automatically cleaned up on the next orchestrator start, so a stale file from a
previous run will not block a new run.

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
    depends_on: ['0.4']           # optional, task IDs that must complete first
    parallel_group: 'group-name'  # optional, tasks with same group run in parallel
    exclusive_resources:           # optional, prevents parallel with same resource
    - database
    max_attempts: 3               # optional, overrides default
    execution_mode: agent_team    # optional, use agent team for this task
    team_roles:                   # optional, roles for agent team
    - name: role-name
      focus: "What this role does"
```

**Task Fields:**
- `id` - Unique identifier (e.g., '1.1', '2.3a')
- `name` - Short task name
- `status` - pending | in_progress | completed | failed | skipped
- `description` - Detailed description (include "Files:" for conflict detection)
- `depends_on` - List of task IDs that must complete before this task can start
- `parallel_group` - Tasks with the same group execute concurrently (requires `--parallel`)
- `exclusive_resources` - Resources that can't be shared (e.g., ['database', 'config'])
- `max_attempts` - Override default retry count
- `execution_mode` - Set to `agent_team` for collaborative tasks
- `team_roles` - Define roles when using agent team execution

## Choosing Task Execution Strategy

The orchestrator drives execution. When designing a YAML plan, decide the execution
strategy for each task based on whether agents need to communicate:

| Strategy | YAML Config | When to Use |
|----------|-------------|-------------|
| Single agent (default) | No special fields | Most tasks: one agent, one focused job |
| Independent parallel | `parallel_group` | Tasks touch different files, no coordination needed |
| Design competition | `parallel_group` + judge task | Multiple approaches to evaluate (see below) |
| Agent team | `execution_mode: agent_team` | Tasks require inter-agent discussion and collaboration |

**Decision guide for each task in the plan:**
1. Can this task be done by one agent in isolation? -> Single agent (default)
2. Can multiple tasks run at the same time without talking to each other? -> `parallel_group`
3. Are there multiple valid approaches that should be explored? -> Design competition
4. Do agents need to discuss interfaces, challenge assumptions, or coordinate? -> Agent team

## Parallel Execution

When `--parallel` is enabled, tasks with the same `parallel_group` field execute concurrently:
- Each parallel task runs in its own git worktree (`.worktrees/` directory)
- Results are merged back to main branch after all parallel tasks complete
- The orchestrator automatically detects file conflicts from task descriptions
- Tasks with conflicts fall back to sequential execution

**Parallel Coordination (Automatic):**
The orchestrator extracts file paths from task descriptions and validates that parallel
tasks don't conflict:
- Files mentioned after "Files:" or "New:" are tracked
- Paths matching patterns like `src/.../*.tsx` are detected
- If two tasks in the same `parallel_group` modify the same file, they run sequentially

**Exclusive Resources:**
For non-file resources that can't be shared (e.g., database schemas, global state):
```yaml
- id: '2.1'
  name: Run database migration
  parallel_group: 'phase-2'
  exclusive_resources: ['database', 'prisma-schema']
```
Tasks declaring the same exclusive resource cannot run in parallel.

**Writing Good Task Descriptions for Parallel Execution:**
Include file paths in descriptions to enable automatic conflict detection:
```yaml
description: |
  Add user search to the assignment panel.
  Files: src/components/community/UserAssignments.tsx
  New: src/components/community/UserSearchInput.tsx
```

## Design Competitions (Phase 0 Pattern)

For features with multiple valid approaches (especially UI), use the design competition
pattern. Five parallel agents each explore a different approach, then a judge picks the best:

```yaml
- id: phase-0
  name: 'Phase 0: Design Generation & Evaluation'
  tasks:
  - id: '0.1'
    name: Generate Design 1 - Approach A
    parallel_group: phase-0-designs
    description: |
      Create a detailed design using approach A.
      CONTEXT: [key source files, design overview with eval criteria]
      DESIGN CONCEPT: [unique visual/architectural approach]
      OUTPUT: Write ONLY to docs/plans/feature-design-1-approach-a.md
  - id: '0.2'
    name: Generate Design 2 - Approach B
    parallel_group: phase-0-designs
    # ... same context, different concept, different output file
  # ... designs 3, 4, 5
  - id: '0.6'
    name: Judge and select best design
    depends_on: ['0.1', '0.2', '0.3', '0.4', '0.5']
    description: |
      Read all 5 designs. Score each on 5 criteria (10 pts each, 50 total).
      Declare winner. List 2-3 improvements from runner-ups to incorporate.
      Update the design overview doc with scoring table and final design.
  - id: '0.7'
    name: Extend plan with implementation tasks
    depends_on: ['0.6']
    description: |
      Read winning design. Append implementation phases to THIS YAML.
      Set plan_modified: true in status file so orchestrator reloads.
```

The AI judge validates the design; no human review is needed. The human only intervenes
if the circuit breaker trips or smoke tests fail during implementation.

## Agent Teams (Collaborative Tasks)

Agent teams let multiple Claude Code instances communicate with each other via messages
while sharing a task list. The orchestrator spawns the team; agents collaborate in real-time.

**Agent teams are the right choice when:**
- Tasks touch related or overlapping code and agents need to coordinate interfaces
- Debugging requires competing hypotheses that agents should discuss and challenge
- Cross-layer changes span frontend, backend, and tests with interface contracts to agree on
- Design reviews benefit from agents critiquing each other's approaches
- Code review needs multiple focused perspectives (security, performance, test coverage)

**Agent teams are NOT the right choice when:**
- Tasks are fully independent (use `parallel_group` instead)
- Only the result matters, not the process (use subagents instead)
- Tasks are sequential with dependencies (use orchestrator sequential)
- The work is simple enough for a single agent session

**How agent teams work:**
1. The orchestrator (or lead session) creates the team with `TeamCreate`
2. Teammates are spawned via `Task` tool with `team_name` and `name` parameters
3. Teammates communicate via `SendMessage` (direct messages or broadcast)
4. All agents share a task list (`TaskCreate`, `TaskList`, `TaskUpdate`)
5. Teammates self-claim unblocked tasks or the lead assigns them
6. When done, the lead sends `shutdown_request` to each teammate, then `TeamDelete`

**Configuring agent team tasks in YAML plans:**

Use `execution_mode: agent_team` and `team_roles` to define how the orchestrator should
set up the team for a task:
```yaml
- id: '3.1'
  name: Implement auth middleware + API endpoint + integration test
  status: pending
  execution_mode: agent_team
  team_roles:
    - name: backend-dev
      focus: "Implement auth middleware and service layer"
    - name: api-dev
      focus: "Implement API endpoint consuming the middleware"
    - name: test-dev
      focus: "Write integration tests as the API stabilizes"
  description: |
    These tasks are tightly coupled - the API depends on middleware interfaces,
    and tests depend on both. Use an agent team so agents can discuss interface
    contracts and unblock each other in real-time.
```

**Best practices for agent teams:**
- Give each teammate enough context in their spawn prompt (they don't inherit conversation history)
- Size tasks appropriately: 5-6 tasks per teammate keeps everyone productive
- Avoid two teammates editing the same file simultaneously (coordinate via messages)
- Use `delegate` mode on the lead (Shift+Tab) to prevent it from implementing instead of coordinating
- Monitor progress and redirect approaches that aren't working
- Start with research/review teams before attempting parallel implementation teams

**Token cost consideration:**
Agent teams are the most expensive execution strategy. Each teammate is a full Claude instance.
Use them when the collaboration value justifies the cost (debugging, cross-layer coordination,
design critiques) and prefer cheaper strategies (parallel_group, single agent) for independent work.

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
1. The project's coding rules: `CODING-RULES.md` (in the project root)
2. The `plan_doc` referenced in meta - detailed design
3. Relevant architecture and design documents

### Step 4: Implement Changes

- Follow the project's coding standards
- Use existing patterns from the codebase
- Prefer editing existing files over creating new ones

### Step 5: Verify Changes

Run the project's build and test commands to verify no errors:
```bash
# Example (adapt to your project):
npm run build
npm test
```

### Step 6: Write Status File

**CRITICAL**: Write status to `.claude/plans/task-status.json`:

```json
{
  "task_id": "4.7",
  "status": "completed",
  "message": "Brief description of what was done",
  "timestamp": "2026-01-19T12:00:00Z",
  "plan_modified": false
}
```

For failures:
```json
{
  "task_id": "4.7",
  "status": "failed",
  "message": "What went wrong and why",
  "timestamp": "2026-01-19T12:00:00Z",
  "plan_modified": false
}
```

### Step 7: Commit Changes

```bash
git add -A
git commit -m "feat: Task description

- What changed
- Why it changed

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Step 8: Update Plan (if not using orchestrator)

If running manually (not via orchestrator), update the task status in the YAML:
```yaml
- id: '4.7'
  status: completed
  completed_at: '2026-01-19T12:00:00'
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

1. ALWAYS read `CODING-RULES.md` before generating code
2. Fix ALL test failures before marking complete
3. If build fails, fix the errors before proceeding
4. Keep changes minimal and focused on the task
5. ALWAYS write the status file when done
6. COMMIT after completing each task

## Error Handling

If the task fails:
1. Write status file with `status: failed` and clear message
2. Document what went wrong
3. The orchestrator will retry (up to max_attempts)
4. After max attempts, the circuit breaker will trip and the human can investigate

## Creating New YAML Plans

To create a new plan:
1. Write detailed design to `docs/plans/YYYY-MM-DD-feature-design.md`
2. Create YAML plan in `.claude/plans/<feature>.yaml`
3. Reference the design doc in `meta.plan_doc`
4. Break work into sections and tasks
5. For UI features or other complex architecture questions where multiple valid approaches
   exist, consider using the Phase 0 design competition pattern. This is especially valuable
   when the team needs to explore different UX layouts, API designs, data model strategies,
   or component architectures before committing to an implementation. Five parallel agents
   each develop a distinct approach, then an AI judge scores them on predefined criteria
   and selects the winner --- removing the bottleneck of human design review while still
   ensuring quality through structured evaluation. The winning design feeds directly into
   the implementation phases via the self-extending plan pattern.
6. Run orchestrator to execute

Example command to start:
```bash
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml --dry-run
```
