# Claude Plan Orchestrator

Automate multi-step implementation plans with Claude Code. Break complex projects into discrete tasks executed in fresh Claude sessions, avoiding the context degradation that plagues long-running LLM interactions.

## Overview

The Plan Orchestrator executes structured YAML plans through Claude Code, providing:

- **Fresh Context Per Task**: Each task runs in its own Claude session with clean context
- **Parallel Execution**: Run independent tasks concurrently via git worktrees
- **Dependency Management**: Tasks declare dependencies; orchestrator respects execution order
- **Circuit Breaker**: Stops after consecutive failures to avoid wasting resources
- **Rate Limit Handling**: Detects Claude API rate limits and waits automatically
- **Graceful Stop**: Touch a semaphore file to stop between tasks
- **Post-Plan Smoke Tests**: Optionally run Playwright tests after plan completion
- **Auto-Pipeline**: Daemon that watches backlog folders and drives the orchestrator automatically
- **Defect Verification Loop**: Independent symptom verification with verify-then-fix retry cycles
- **Configurable Commands**: Build, test, and dev-server commands configurable per project

```
                     ┌──────────────────────────┐
                     │      YAML Plan           │
                     │  (sections + tasks +     │
                     │   dependencies)          │
                     └────────────┬─────────────┘
                                  │
                     ┌────────────▼─────────────┐
                     │     Orchestrator          │
                     │  (Python state machine)   │
                     │                           │
                     │  ┌─────┐ ┌─────┐ ┌─────┐ │
                     │  │Task │ │Task │ │Task │ │  ← parallel via
                     │  │ 2.1 │ │ 2.2 │ │ 2.3 │ │    git worktrees
                     │  └──┬──┘ └──┬──┘ └──┬──┘ │
                     │     │       │       │     │
                     └─────┼───────┼───────┼─────┘
                           │       │       │
                     ┌─────▼───────▼───────▼─────┐
                     │    Claude Code CLI         │
                     │  (fresh session per task)  │
                     └────────────┬──────────────┘
                                  │
                     ┌────────────▼─────────────┐
                     │    task-status.json       │
                     │  (completion protocol)    │
                     └──────────────────────────┘
```

## Why Fresh Sessions Matter

LLMs degrade on long-running tasks. Context accumulates, quality drops, and implementation details get contradicted after 3-4 tasks. The orchestrator solves this by giving each task a fresh Claude session with:
- Clean context focused on ONE task
- The full plan available for reference
- Automatic status tracking and commits

See [docs/narrative/](docs/narrative/) for the full development history and design rationale.

## Requirements

- Python 3.8+
- PyYAML (`pip install pyyaml`)
- Claude Code CLI installed and authenticated
- Git (for version control and parallel worktrees)
- Optional: `watchdog` (`pip install watchdog`) for auto-pipeline

## Installation

### Plugin Install (Recommended)

```bash
claude plugin install martinbechard/claude-plan-orchestrator
```

Or for local development:

```bash
claude --plugin-dir /path/to/claude-plan-orchestrator
```

After plugin install, the orchestrator scripts are available in the plugin directory:

```bash
python "$(claude plugin path plan-orchestrator)/scripts/plan-orchestrator.py" --plan .claude/plans/my-feature.yaml
```

See [Migration Guide](docs/migration-from-manual-copy.md) for migrating from manual-copy to plugin installation.

### Manual Install (Alternative)

Copy the orchestrator components to your project:

```bash
# Clone this repo
git clone https://github.com/martinbechard/claude-plan-orchestrator.git

# Copy to your project
cp -r claude-plan-orchestrator/.claude/ /path/to/your/project/
cp -r claude-plan-orchestrator/scripts/ /path/to/your/project/
cp -r claude-plan-orchestrator/docs/ /path/to/your/project/
```

Or copy individual files:

```bash
# Required
cp scripts/plan-orchestrator.py /your/project/scripts/

# Recommended
cp CODING-RULES.md /your/project/                  # Coding standards template
cp .claude/skills/implement/SKILL.md /your/project/.claude/skills/implement/

# Optional
cp scripts/auto-pipeline.py /your/project/scripts/
cp .claude/commands/implement.md /your/project/.claude/commands/
cp .claude/plans/sample-plan.yaml /your/project/.claude/plans/
```

## Quick Start

### 1. Create your plan

```bash
cp .claude/plans/sample-plan.yaml .claude/plans/my-feature.yaml
```

Edit the plan with your tasks:

```yaml
meta:
  name: My Feature
  description: What this plan accomplishes
  plan_doc: docs/plans/2026-01-20-my-feature-design.md
  created: '2026-01-20'
  max_attempts_default: 3

sections:
- id: phase-1
  name: Phase 1 - Setup
  status: pending
  tasks:
  - id: '1.1'
    name: Create initial structure
    status: pending
    description: Set up the basic project structure
  - id: '1.2'
    name: Add configuration
    status: pending
    description: Add configuration files
    depends_on:
    - '1.1'

- id: phase-2
  name: Phase 2 - Implementation (Parallel)
  status: pending
  tasks:
  - id: '2.1'
    name: Build component A
    status: pending
    description: Implement component A
    parallel_group: phase-2-impl
    depends_on:
    - '1.2'
  - id: '2.2'
    name: Build component B
    status: pending
    description: Implement component B
    parallel_group: phase-2-impl
    depends_on:
    - '1.2'
```

### 2. Create your design document

Write detailed implementation steps at `docs/plans/YYYY-MM-DD-my-feature-design.md`. The more detailed, the better Claude will execute each task.

### 3. Run the orchestrator

```bash
# Dry run first (shows what would execute)
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml --dry-run

# Run all pending tasks
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml

# Run with parallel execution
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml --parallel

# Run single task then stop
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml --single-task

# Resume from specific task
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml --resume-from 2.1

# Verbose output with real-time streaming
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml --verbose

# Skip post-plan smoke tests
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml --skip-smoke
```

## Features

### Parallel Execution

Tasks with the same `parallel_group` run concurrently in isolated git worktrees:

```yaml
- id: '2.1'
  parallel_group: phase-2-impl    # Same group = run in parallel
  depends_on: ['1.2']
- id: '2.2'
  parallel_group: phase-2-impl    # Same group = run in parallel
  depends_on: ['1.2']
- id: '2.3'
  exclusive_resources: [database]  # Can't share = run sequentially
  depends_on: ['1.2']
```

Each parallel task:
- Runs in its own git worktree (isolated working directory)
- Follows a subagent coordination protocol (file claims, heartbeats)
- Has artifacts merged back via file-copy (not git merge, to avoid YAML conflicts)

### Dependency Management

Tasks declare dependencies with `depends_on`. The orchestrator only starts a task when all its dependencies are completed:

```yaml
- id: '3.1'
  depends_on:
  - '2.1'
  - '2.2'
  - '2.3'
```

### Circuit Breaker

After 3 consecutive task failures (configurable), the orchestrator pauses for 300 seconds before retrying. This prevents burning through rate limits or repeatedly hitting the same error.

### Rate Limit Detection

When Claude CLI output contains rate limit messages ("You've hit your limit"), the orchestrator:
1. Parses the reset time from the message
2. Calculates wait duration with timezone awareness
3. Sleeps until reset + 30s buffer
4. Resumes execution automatically

### Graceful Stop

To stop the orchestrator between tasks without killing it:

```bash
touch .claude/plans/.stop
```

The orchestrator checks for this semaphore before each new task and exits cleanly. Remove it to allow future runs.

### Post-Plan Smoke Tests

After all tasks complete, the orchestrator can run Playwright smoke tests to verify the application still works:

```bash
# Enabled by default (looks for tests/SMOKE01-critical-paths.spec.ts)
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml

# Disable smoke tests
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml --skip-smoke
```

### Plan Modification by Claude

Claude can modify the YAML plan during execution:
- **Split tasks**: Large task 2.1 becomes 2.1a, 2.1b, 2.1c
- **Add tasks**: Insert discovered work
- **Skip tasks**: Mark unnecessary tasks as skipped
- **Self-extending plans**: A task can append new tasks and set `plan_modified: true`

Set `plan_modified: true` in the status file to trigger a plan reload.

### Verbose / Streaming Output

Use `--verbose` for real-time streaming of Claude's output via `--output-format stream-json`:

```bash
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml --verbose
```

## Auto-Pipeline

The auto-pipeline daemon (`scripts/auto-pipeline.py`) watches backlog folders and drives the orchestrator automatically:

```bash
# Watch backlogs and process items
python scripts/auto-pipeline.py

# Single pass (process one item, then exit)
python scripts/auto-pipeline.py --once

# Dry run
python scripts/auto-pipeline.py --dry-run

# Verbose output
python scripts/auto-pipeline.py --verbose
```

The auto-pipeline:
1. Monitors `docs/defect-backlog/` and `docs/feature-backlog/` for new `.md` files
2. Prioritizes defects over features; respects `## Dependencies` between items
3. For each item: Claude creates a design + YAML plan, then the orchestrator executes it
4. For defects: runs an independent verification step to confirm symptoms are resolved
5. If verification fails: deletes stale plan, retries with findings (up to 3 cycles)
6. Archives completed items to `completed/` subdirectories
7. Shares the `.stop` semaphore with the orchestrator for coordinated shutdown

Requires: `pip install watchdog pyyaml`

### Defect Verification Loop

For defects, the auto-pipeline runs a verify-then-fix cycle after the orchestrator completes:

```
Phase 1: Create plan      --> Phase 2: Execute plan
                                        |
                              Phase 3: Verify symptoms
                                    |           |
                                  PASS        FAIL
                                    |           |
                              Phase 4:    Delete stale plan,
                              Archive     loop to Phase 1
                                          (findings in defect file
                                           inform the next plan)
```

The verifier is a read-only Claude session that checks whether the reported symptoms are actually resolved. It appends structured findings to the defect file, which the next plan-creation step reads to produce a targeted fix.

### Project Configuration

Customize build and test commands in `.claude/orchestrator-config.yaml`:

```yaml
# Build/test commands used during verification (defaults shown)
# build_command: "pnpm run build"
# test_command: "pnpm test"
# dev_server_command: "pnpm dev"
# dev_server_port: 3000
```

### Backlog Item Format

Write backlog items as markdown files in `docs/defect-backlog/` or `docs/feature-backlog/`:

```markdown
# Brief Title

## Status: Open

## Priority: High

## Summary
What this defect/feature is about.

## Expected Behavior
What should happen.

## Actual Behavior
What actually happens (for defects).

## Fix Required
Specific steps or criteria for the fix.

## Verification
How to verify the fix is correct.

## Dependencies
- 02-other-feature.md
```

Key conventions:
- Filenames use `NN-slug-name.md` format (e.g., `01-fix-login-bug.md`)
- `## Status: Fixed` or `## Status: Completed` marks items as done (auto-pipeline skips them)
- `## Dependencies` lists other backlog slugs that must be completed first
- Items in `completed/` subdirectories are ignored
- Items in `on-hold/` subdirectories are ignored

## Manual Execution

You can also run tasks manually using the `/implement` command in Claude Code:

```
/implement        # Run next pending task
/implement 2.1    # Run specific task by ID
```

## How It Works

1. **Find Next Task**: Orchestrator finds first `pending` or `in_progress` task (respecting dependencies)
2. **Build Prompt**: Creates prompt with task details, plan document reference, and coordination instructions
3. **Execute Claude**: Runs `claude --dangerously-skip-permissions --print <prompt>` in a fresh session
4. **Check Status**: Reads `.claude/plans/task-status.json` for result
5. **Update Plan**: Marks task complete/failed in YAML
6. **Commit**: Auto-commits changes to git
7. **Repeat**: Continues until all tasks done, circuit breaker trips, or stop semaphore detected

### Status File Protocol

Claude writes its status to `.claude/plans/task-status.json`:

```json
{
  "task_id": "1.1",
  "status": "completed",
  "message": "What was accomplished",
  "timestamp": "2026-01-20T12:00:00Z",
  "plan_modified": false
}
```

### Task Statuses

- `pending` - Not yet started
- `in_progress` - Currently being executed
- `completed` - Successfully finished
- `failed` - Failed after max attempts
- `skipped` - Manually skipped with reason

## Subagent Coordination Protocol

When running parallel tasks, each Claude session follows a coordination protocol:

1. **File Claims**: Before editing a file, check/claim it in `.claude/agent-claims.json`
2. **Heartbeats**: Update `.claude/subagent-status/{agent-id}.json` periodically
3. **Conflict Detection**: The orchestrator checks for file conflicts before spawning parallel tasks
4. **Stale Claim Cleanup**: Heartbeat-based detection of abandoned claims

See `.claude/skills/implement/SKILL.md` for the full protocol details.

## Directory Structure

```
your-project/
├── CODING-RULES.md                   # Coding standards (adapt for your project)
├── .claude/
│   ├── plans/
│   │   ├── sample-plan.yaml        # Template plan
│   │   ├── my-feature.yaml         # Your active plan
│   │   ├── task-status.json        # Auto-generated status
│   │   └── .stop                   # Graceful stop semaphore
│   ├── skills/
│   │   └── implement/
│   │       └── SKILL.md            # Implementation skill
│   ├── commands/
│   │   └── implement.md            # /implement command
│   ├── subagent-status/            # Parallel task heartbeats
│   └── agent-claims.json           # File claim coordination
├── scripts/
│   ├── plan-orchestrator.py        # Main orchestrator (~2095 lines)
│   └── auto-pipeline.py            # Auto-pipeline daemon (~1450 lines)
└── docs/
    ├── plans/
    │   └── YYYY-MM-DD-*.md         # Design documents
    └── narrative/
        └── *.md                    # Development history
```

## Tips

1. **Start Small**: Test with 2-3 tasks before running large plans
2. **Detailed Designs**: The design doc is crucial - be specific about file paths and steps
3. **Use Dependencies**: Declare `depends_on` to ensure correct execution order
4. **Parallel Where Possible**: Group independent tasks with `parallel_group` for faster execution
5. **Graceful Stop**: Use `touch .claude/plans/.stop` instead of killing the process
6. **Self-Extending Plans**: Let Claude add tasks during execution with `plan_modified: true`
7. **Monitor Progress**: Check the YAML file for status updates during execution

## Troubleshooting

**Task keeps failing:**
- Check the error message in `last_error` field
- Increase `max_attempts` for complex tasks (default: 3, max recommended: 5)
- Simplify the task description
- The circuit breaker trips after 3 consecutive failures (300s cooldown)

**Parallel tasks conflict:**
- Use `exclusive_resources` to prevent shared-resource tasks from running together
- The conflict detector checks file paths in task descriptions before spawning

**Rate limit hit:**
- The orchestrator auto-detects and waits for rate limit reset
- Check the output for "Rate limit detected" messages

**Claude doesn't write status file:**
- Ensure the implement skill is in `.claude/skills/implement/SKILL.md`
- Check Claude has write access to `.claude/plans/`

**Graceful stop not working:**
- Ensure the `.stop` file is in `.claude/plans/.stop` (not the project root)
- The check happens before each new task, not during execution

**Stale worktrees after crash:**
- Run `git worktree list` and `git worktree remove <path>` for orphans
- The orchestrator attempts cleanup, but crashes may leave worktrees behind

## Development History

The orchestrator evolved from a 454-line sequential executor to a ~3500-line parallel execution engine (across two scripts) over the course of building a production application. See [docs/narrative/](docs/narrative/) for the complete development history, including:

- Genesis and initial design decisions
- Parallel execution via git worktrees
- Subagent coordination protocol
- Hardening (graceful stop, binary resolution, stale branch cleanup)
- Rate limit detection and resilience
- Smoke tests and streaming output
- Auto-pipeline daemon
- Lessons learned and open questions
- Fixing the parallel merge strategy
- Design competitions: parallel design generation with AI judge
- Verification loop: independent symptom verification for defects

## License

MIT License - see [LICENSE](LICENSE)
