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
- **Agent Framework**: 10 specialized agents (coder, code-reviewer, systems-designer, ux-designer, ux-reviewer, spec-verifier, qa-auditor, planner, issue-verifier, validator) with YAML frontmatter definitions
- **Slack Integration**: Real-time notifications, inbound message processing, LLM-powered question answering, and 5 Whys intake analysis via Slack
- **Budget Management**: Token usage tracking, API-equivalent cost estimates, and quota-aware execution with configurable limits
- **Model Escalation**: Tiered model selection (haiku -> sonnet -> opus) with automatic escalation after consecutive failures
- **Per-Task Validation**: Independent validator agent that runs after each task with PASS/WARN/FAIL verdicts and retry logic
- **Design Competitions**: Phase 0 parallel design generation with AI judge for architecture decisions
- **Hot-Reload**: Auto-pipeline monitors its own source files and self-restarts when code changes are detected

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
- Optional: `slack_sdk` (`pip install slack_sdk`) for Slack integration
- Optional: `requests` (`pip install requests`) for API calls

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

### Agent Framework

The orchestrator uses specialized agents defined in `.claude/agents/`. Each agent has a YAML frontmatter header specifying its name, tools, model, and capabilities.

Available agents:

| Agent | Role | Model |
|-------|------|-------|
| coder | Implementation specialist - writes code, runs tests | sonnet (default) |
| code-reviewer | Read-only reviewer - checks compliance, no code changes | sonnet |
| systems-designer | Architecture and data model designer | sonnet |
| ux-designer | Visual and interaction design specialist | sonnet |
| ux-reviewer | UX/UI quality reviewer | sonnet |
| spec-verifier | Functional specification compliance checker | sonnet |
| qa-auditor | QA audit specialist with coverage matrices | sonnet |
| planner | Design-to-implementation bridge - creates YAML phases | sonnet |
| issue-verifier | Defect fix verification with symptom checking | sonnet |
| validator | Per-task validation with PASS/WARN/FAIL verdicts | sonnet |

Tasks can specify their agent in the YAML plan:

```yaml
- id: '2.1'
  name: Implement the feature
  agent: coder
  status: pending
  description: ...

- id: '3.1'
  name: Review code quality
  agent: code-reviewer
  status: pending
  description: ...
```

If no agent is specified, the orchestrator infers it from the task name and description (review/verification -> code-reviewer, design -> systems-designer, everything else -> coder).

### Per-Task Validation

Enable automatic validation after each coder task by adding a `validation` block to the plan meta:

```yaml
meta:
  validation:
    enabled: true
    run_after:
    - coder
    validators:
    - validator
    max_validation_attempts: 1
```

The validator agent runs independently after each task and produces:
- **PASS**: Task proceeds normally
- **WARN**: Task completes but warnings are logged
- **FAIL**: Task is retried with validation findings prepended to the prompt

For defect verification, use the `issue-verifier` validator which reads the original defect file and checks whether reported symptoms are resolved.

### Design Competitions

For significant architectural decisions, the orchestrator supports a Phase 0 design competition pattern where multiple design agents generate competing proposals and an AI judge selects the winner:

```yaml
- id: '0.1'
  name: Generate Design 1
  agent: systems-designer
  parallel_group: phase-0-designs
  status: pending
  description: ...

- id: '0.2'
  name: Generate Design 2
  agent: ux-designer
  parallel_group: phase-0-designs
  status: pending
  description: ...

- id: '0.7'
  name: Extend plan with implementation tasks
  agent: planner
  depends_on: ['0.1', '0.2']
  status: pending
  description: ...
```

The planner agent reads the winning design and creates implementation phases, setting `plan_modified: true` to trigger a plan reload.

### Model Escalation

The orchestrator supports tiered model selection that automatically escalates to more capable (and expensive) models after consecutive task failures:

```bash
# Use default escalation (haiku -> sonnet -> opus after 2 failures each)
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml

# Start with sonnet, escalate after 1 failure
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml \
  --starting-model sonnet --escalate-after-failures 1

# Cap at sonnet (never use opus)
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml \
  --max-model sonnet
```

Model tiers: haiku (fastest/cheapest) -> sonnet (balanced) -> opus (most capable).

### Budget and Quota Management

Track token usage and enforce budget limits during plan execution:

```bash
# Set maximum quota percentage (stop if usage exceeds this % of daily quota)
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml \
  --max-quota-percent 80

# Set quota ceiling in USD (API-equivalent estimate)
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml \
  --quota-ceiling-usd 50.00

# Set reserved budget (stop when remaining budget drops below this)
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml \
  --reserved-budget-usd 10.00
```

Cost displays use `~$` prefix to indicate API-equivalent estimates. Note: Claude Max subscription users are not billed per-token; these are estimates for planning purposes.

### Slack Integration

The auto-pipeline integrates with Slack for real-time notifications and inbound work items:

**Outbound notifications** are sent to dedicated channels:
- `orchestrator-notifications` - Status updates, progress reports
- `orchestrator-defects` - Defect intake and status
- `orchestrator-features` - Feature intake and status
- `orchestrator-questions` - Questions from the orchestrator to the team

**Inbound message processing** supports:
- Submitting new features and defects via Slack messages
- Asking questions about the pipeline state (answered by LLM with full context)
- Control commands (stop, status, etc.)
- 5 Whys analysis for intake - the system automatically structures incoming feature/defect requests using the 5 Whys methodology

Configure Slack in `.claude/slack.local.yaml`:

```yaml
bot_token: xoxb-your-bot-token
channel_prefix: orchestrator
```

The background polling thread checks for new messages every 15 seconds, independent of task execution.

### Hot-Reload

The auto-pipeline monitors its own source files for changes. When a modification is detected between work items, it performs a graceful self-restart using `os.execv()` to pick up the new code without disrupting the Slack polling thread:

```
Work item completes -> Check source file hashes -> Changed? -> Graceful restart
                                                       -> No change? -> Continue
```

Monitored files are defined in `HOT_RELOAD_WATCHED_FILES` in auto-pipeline.py.

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
# agents_dir: ".claude/agents"
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
│   ├── agents/
│   │   ├── coder.md               # Implementation specialist
│   │   ├── code-reviewer.md        # Read-only reviewer
│   │   ├── systems-designer.md    # Architecture designer
│   │   ├── ux-designer.md          # UI/UX designer
│   │   ├── ux-reviewer.md           # UX quality reviewer
│   │   ├── spec-verifier.md        # Spec compliance checker
│   │   ├── qa-auditor.md           # QA audit specialist
│   │   ├── planner.md              # Design-to-plan bridge
│   │   ├── issue-verifier.md       # Defect fix verifier
│   │   └── validator.md            # Per-task validator
│   ├── skills/
│   │   ├── implement/
│   │   │   └── SKILL.md            # Implementation skill
│   │   └── coding-rules/
│   │       └── SKILL.md            # Coding standards skill
│   ├── commands/
│   │   └── implement.md            # /implement command
│   ├── slack.local.yaml             # Slack channel configuration (user-created)
│   ├── orchestrator-config.yaml     # Project-specific config
│   ├── subagent-status/            # Parallel task heartbeats
│   └── agent-claims.json           # File claim coordination
├── scripts/
│   ├── plan-orchestrator.py        # Main orchestrator (~4773 lines)
│   └── auto-pipeline.py            # Auto-pipeline daemon (~1949 lines)
└── docs/
    ├── plans/
    │   └── YYYY-MM-DD-*.md         # Design documents
    ├── defect-backlog/             # Active defects
    ├── feature-backlog/            # Active features
    ├── completed-backlog/          # Archived completed items
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

The orchestrator evolved from a 454-line sequential executor to a ~6700-line parallel execution engine (across two scripts) over the course of building a production application. See [docs/narrative/](docs/narrative/) for the complete development history, including:

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
- Agent definition framework with YAML frontmatter
- Per-task validation pipeline
- Design agents (systems-designer, ux-designer)
- Tiered model escalation
- Token usage and budget tracking
- Slack integration with inbound message polling
- Hot-reload self-restart for auto-pipeline

## License

MIT License - see [LICENSE](LICENSE)
