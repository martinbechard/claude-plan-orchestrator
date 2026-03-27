# Claude Plan Orchestrator

Automate multi-step implementation plans with Claude Code. Break complex projects into discrete tasks executed in fresh Claude sessions, avoiding the context degradation that plagues long-running LLM interactions.

## Overview

The Plan Orchestrator executes structured YAML plans through Claude Code, providing:

- **Fresh Context Per Task**: Each task runs in its own Claude session with clean context
- **Parallel Execution**: Run independent tasks concurrently via git worktrees
- **Dependency Management**: Tasks declare dependencies; orchestrator respects execution order
- **Circuit Breaker**: Stops after consecutive failures to avoid wasting resources
- **Rate Limit Handling**: Detects Claude API rate limits and waits automatically
- **Graceful Stop**: Touch a semaphore file or send SIGINT/SIGTERM to stop between tasks
- **Defect Verification Loop**: Independent symptom verification with verify-then-fix retry cycles
- **Configurable Commands**: Build, test, and dev-server commands configurable per project
- **Agent Framework**: 11 specialized agents (coder, frontend-coder, code-reviewer, systems-designer, ux-designer, ux-reviewer, spec-verifier, qa-auditor, planner, issue-verifier, validator) with YAML frontmatter definitions
- **Slack Integration**: Real-time notifications, inbound message processing, LLM-powered question answering, 5 Whys intake analysis, and cross-instance collaboration via Slack. Multi-layer loop prevention (chain detection, self-reply gating, notification pattern filter, global rate limiter) prevents recursive feedback spirals
- **RAG Deduplication**: ChromaDB-based semantic search over the backlog detects duplicate defect/feature requests and consolidates them into existing items instead of creating duplicates
- **Budget Management**: Session-level budget cap via CLI, plus per-plan budget limits in YAML
- **Model Escalation**: Tiered model selection (haiku -> sonnet -> opus) with automatic escalation after consecutive failures
- **Per-Task Validation**: Independent validator agent that runs after each task with PASS/WARN/FAIL verdicts and retry logic
- **Design Competitions**: Phase 0 parallel design generation with AI judge for architecture decisions
- **Crash Recovery**: SQLite-backed checkpointing allows the pipeline to resume from the last completed step after a crash
- **LangSmith Tracing**: Optional LangSmith integration for debugging and observability

## Architecture

The pipeline is built on LangGraph, with two interconnected graphs:

```
                     ┌───────────────────────────────────────────────┐
                     │            Pipeline Graph                     │
                     │                                               │
                     │  scan_backlog ──► intake_analyze ──► create_plan
                     │       │                                  │    │
                     │       ▼                                  ▼    │
                     │     (END if                        execute_plan
                     │      no items)                     ┌─────┤    │
                     │                                    │     ▼    │
                     │                              (defect?) verify │
                     │                                    │   │   │  │
                     │                                    │ PASS FAIL│
                     │                                    │   │   │  │
                     │                                    ▼   ▼   ▼  │
                     │                                  archive  ◄───┘
                     │                                    │          │
                     │                                    ▼          │
                     │                                  (END)        │
                     └───────────────────────────────────────────────┘

                     ┌───────────────────────────────────────────────┐
                     │          Executor Subgraph                    │
                     │  (invoked by execute_plan node)               │
                     │                                               │
                     │  task_selector ──► task_runner ──► validator   │
                     │       ▲                               │       │
                     │       │          FAIL + escalate      │       │
                     │       └───────────────────────────────┘       │
                     │                                               │
                     │  Features: parallel worktrees, circuit        │
                     │  breaker, model escalation, fresh Claude      │
                     │  session per task                             │
                     └───────────────────────────────────────────────┘
```

Each task runs in a fresh Claude Code CLI session. The executor subgraph handles task selection, Claude CLI invocation, validation, parallel worktree execution, circuit breaking, and model escalation entirely within LangGraph.

## Why Fresh Sessions Matter

LLMs degrade on long-running tasks. Context accumulates, quality drops, and implementation details get contradicted after 3-4 tasks. The orchestrator solves this by giving each task a fresh Claude session with:
- Clean context focused on ONE task
- The full plan available for reference
- Automatic status tracking and commits

See [docs/narrative/](docs/narrative/) for the full development history and design rationale.

**New here?** Read the [Setup Guide](docs/setup-guide.md) before proceeding. It contains the complete step-by-step setup procedure: dependency installation, Slack app creation (via automated script), required .gitignore entries for orchestrator transient files, backlog directory setup, and upgrade/migration instructions from earlier versions.

## Requirements

- Python 3.8+
- PyYAML (`pip install pyyaml`)
- LangGraph (`pip install langgraph`)
- Claude Code CLI installed and authenticated
- Git (for version control and parallel worktrees)
- Optional: `chromadb` (`pip install chromadb`) for RAG-based intake deduplication
- Optional: `slack-bolt` (`pip install slack-bolt`) for Slack Socket Mode (interactive buttons)

## Installation

### Plugin Install (Recommended)

```bash
claude plugin install martinbechard/claude-plan-orchestrator
```

Or for local development:

```bash
claude --plugin-dir /path/to/claude-plan-orchestrator
```

After plugin install, run the pipeline from your project directory:

```bash
python scripts/auto-pipeline.py
```

See the [Setup Guide](docs/setup-guide.md) for the complete setup procedure including Slack integration, .gitignore configuration, and upgrading from earlier versions.

### Manual Install (Alternative)

Copy the orchestrator components to your project:

```bash
# Clone this repo
git clone https://github.com/martinbechard/claude-plan-orchestrator.git

# Copy to your project
cp -r claude-plan-orchestrator/.claude/ /path/to/your/project/
cp -r claude-plan-orchestrator/scripts/ /path/to/your/project/
cp -r claude-plan-orchestrator/langgraph_pipeline/ /path/to/your/project/
cp -r claude-plan-orchestrator/docs/ /path/to/your/project/
```

Or copy individual components:

```bash
# Required: the pipeline package and entry point
cp -r langgraph_pipeline/ /your/project/
cp scripts/auto-pipeline.py /your/project/scripts/

# Recommended
cp CODING-RULES.md /your/project/                  # Coding standards template
cp .claude/skills/implement/SKILL.md /your/project/.claude/skills/implement/

# Optional
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

### 3. Run the pipeline

```bash
# Start the pipeline (scans backlogs, creates plans, executes tasks)
python scripts/auto-pipeline.py

# Or equivalently via module
python -m langgraph_pipeline

# Process one item then exit
python scripts/auto-pipeline.py --once

# Dry run (shows what would execute without running)
python scripts/auto-pipeline.py --dry-run

# Verbose output (debug logging)
python scripts/auto-pipeline.py --verbose
```

## CLI Reference

The pipeline accepts the following flags. Both `python scripts/auto-pipeline.py` and `python -m langgraph_pipeline` accept the same arguments:

| Flag | Description |
|------|-------------|
| `--once` | Scan backlog, process one item, then exit |
| `--single-item PATH` | Process a specific backlog item at PATH and exit |
| `--dry-run` | Log what would be done without executing |
| `--verbose` | Shorthand for `--log-level DEBUG` |
| `--log-level LEVEL` | Set logging verbosity: DEBUG, INFO, WARNING, ERROR (default: INFO) |
| `--budget-cap USD` | Stop after cumulative session cost exceeds this value. Exits with code 2 |
| `--backlog-dir DIR` | Override the default backlog directory to scan |
| `--no-slack` | Disable all Slack notifications and inbound polling |
| `--no-tracing` | Skip LangSmith tracing configuration |

Exit codes:
- `0` -- clean shutdown (SIGINT/SIGTERM, `--once` complete, or no items)
- `1` -- unhandled error
- `2` -- budget cap exhausted

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

To stop the pipeline cleanly, use any of these methods:

```bash
# Semaphore file (checked between tasks)
touch .claude/plans/.stop

# Signal (completes current graph invocation, then exits)
kill $(cat .claude/plans/.pipeline.pid)

# Or just Ctrl+C (SIGINT)
```

### Plan Modification by Claude

Claude can modify the YAML plan during execution:
- **Split tasks**: Large task 2.1 becomes 2.1a, 2.1b, 2.1c
- **Add tasks**: Insert discovered work
- **Skip tasks**: Mark unnecessary tasks as skipped
- **Self-extending plans**: A task can append new tasks and set `plan_modified: true`

Set `plan_modified: true` in the status file to trigger a plan reload.

### Agent Framework

The orchestrator uses specialized agents defined in `.claude/agents/`. Each agent has a YAML frontmatter header specifying its name, tools, model, and capabilities.

Available agents:

| Agent | Role | Model |
|-------|------|-------|
| coder | Implementation specialist - writes code, runs tests | sonnet (default) |
| frontend-coder | Frontend implementation specialist - UI components, pages, forms | sonnet |
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

If no agent is specified, the orchestrator infers it from the task name and description (review/verification -> code-reviewer, design/architecture -> systems-designer, plan extension -> planner, frontend/component/UI -> frontend-coder, everything else -> coder).

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

Design competition judging can use a different model by adding `judge_model` to the plan meta:

```yaml
meta:
  judge_model: sonnet   # For UI-focused competitions
  # judge_model: opus   # For architecture competitions
```

### Model Escalation

The executor subgraph uses tiered model selection that automatically escalates to more capable models after consecutive task failures:

- **Default progression**: haiku -> sonnet -> opus
- **Reset on success**: After a task succeeds, the model resets to the starting tier
- Escalation is enabled by default with `haiku` as the starting model

Model tiers: haiku (fastest/cheapest) -> sonnet (balanced) -> opus (most capable).

### Budget Management

Budget limits can be set at two levels:

**Session-level** via CLI flag:

```bash
# Stop after cumulative cost exceeds ~$5 (exits with code 2)
python scripts/auto-pipeline.py --budget-cap 5.00
```

**Per-plan** via YAML metadata:

```yaml
meta:
  budget_limit_usd: 10.00
```

Cost displays use `~$` prefix to indicate API-equivalent estimates. Note: Claude Max subscription users are not billed per-token; these are estimates for planning purposes.

### Crash Recovery

The pipeline uses SQLite-backed checkpointing (via LangGraph's `SqliteSaver`). If the process crashes or is killed, it resumes from the last completed graph node on restart. The checkpoint database is stored at `.claude/pipeline-state.db`.

### Defect Verification Loop

For defects, the pipeline runs a verify-then-fix cycle after plan execution:

```
scan_backlog --> intake_analyze --> create_plan --> execute_plan
                                                       |
                                             (defect?) verify_fix
                                                    |           |
                                                  PASS        FAIL
                                                    |           |
                                                archive    back to create_plan
                                                           (findings inform
                                                            the next plan)
```

The verifier checks whether the reported symptoms are actually resolved. It appends structured findings to the defect file, which the next plan-creation step reads to produce a targeted fix. Up to 3 verification cycles are attempted.

### Slack Integration

The pipeline integrates with Slack for real-time notifications and inbound work items. Slack is enabled by default; disable with `--no-slack`.

**Outbound notifications** are sent to dedicated channels:
- `{prefix}-notifications` - Status updates, progress reports
- `{prefix}-defects` - Defect intake and status
- `{prefix}-features` - Feature intake and status
- `{prefix}-questions` - Questions from the pipeline to the team

**Inbound message processing** runs on a background polling thread (every 15 seconds) and supports:
- Submitting new features and defects via Slack messages
- Asking questions about the pipeline state (answered by LLM with full context)
- Control commands: `stop_pipeline`, `skip_item`, `get_status`
- 5 Whys analysis for intake - the system automatically structures incoming feature/defect requests using the 5 Whys methodology

**Setup:** Run `python scripts/setup-slack.py --prefix myproject` to create a Slack app, channels, and config automatically. For a second project reusing an existing app, pass `--bot-token` and `--app-token` with a different `--prefix`. See the [Setup Guide](docs/setup-guide.md) for the full walkthrough including required bot scopes, manual setup alternative, and migration from webhook-based Slack to app-based Slack.

**Adding a Second Project to an Existing Workspace:** If you already have a Slack app running for another project, you can add the orchestrator to a second project with a single command:

```bash
python scripts/setup-slack.py --prefix newproject --bot-token xoxb-your-existing-token --app-token xapp-your-existing-token --non-interactive
```

Find your existing tokens in the other project's `.claude/slack.local.yaml`. The command creates new `newproject-*` channels and writes `.claude/slack.local.yaml` in the current directory.

**Loop prevention** uses four redundant layers to prevent the bot from re-processing its own notifications in a feedback spiral:
1. **Chain detection:** On-disk history of recently created items; messages referencing known item numbers are skipped
2. **Self-reply gating:** Max 1 self-origin message accepted per 5-minute window per channel
3. **Notification pattern filter:** Regex skips messages matching bot notification formats before LLM routing
4. **Global intake rate limiter:** Hard cap of 10 intakes per 5 minutes across all channels

**RAG deduplication** (requires `chromadb`): Incoming defect/feature requests are compared against a ChromaDB vector index of existing backlog items. When a high-similarity match is found, an LLM confirms whether it is a true duplicate. Confirmed duplicates are consolidated into the existing item (new information appended) instead of creating a new file.

### Cross-Instance Collaboration via Slack

Multiple orchestrator instances running in different projects can collaborate through shared Slack channels. By inviting other instances to listen to your channels, they gain the ability to:

- **Discover new versions**: Instances see release notifications and can flag when they are running outdated code
- **Submit defects**: An instance that encounters a bug in the orchestrator itself can post a structured defect report to the defects channel
- **Submit features**: Instances can request new capabilities by posting to the features channel
- **Ask questions**: Cross-instance questions are answered by the LLM with full pipeline context

This turns the Slack channels into a lightweight coordination bus where orchestrator instances running across different codebases can report issues, request improvements, and stay informed about upstream changes -- without any direct coupling between the projects.

**Setup:** Each instance uses its own channel prefix (e.g., `myproject-notifications`), but can be invited to monitor another instance's channels as a read/write participant. The inbound message processing handles messages from any source identically -- whether from a human or another orchestrator instance.

#### Setting Up Cross-Project Reporting (Consumer Side)

If your project wants to report defects or request features to an upstream orchestrator, three things must be in place:

1. **Know the upstream channel prefix** -- The upstream project's channels follow the naming pattern `{prefix}-defects`, `{prefix}-features`, `{prefix}-notifications`, and `{prefix}-questions`. Get this prefix from the upstream team.

2. **Invite your bot to the upstream channels** -- In each upstream Slack channel you want to post to, open the channel and run `/invite @YourBotName`. Your bot needs `chat:write` access on those channels to post and `channels:history` (or `groups:history` for private channels) to poll them.

3. **Configure agent identity** -- Add an `identity` section to your `orchestrator-config.yaml` (see [Agent Identity Protocol](#agent-identity-protocol) below) so the upstream orchestrator can identify your messages and skip self-echoes.

Once invited and configured, set `channel_prefix` in your `.claude/slack.local.yaml` to the upstream's prefix. Your orchestrator will then discover the upstream channels, poll them for release notifications, and route outbound defect and feature reports there.

For the full step-by-step procedure, see [Cross-Project Reporting](docs/setup-guide.md#cross-project-reporting) in the Setup Guide.

### Agent Identity Protocol

When multiple projects share Slack channels, the agent identity protocol distinguishes who sent each message and who it is intended for.

**Configuration** in `orchestrator-config.yaml`:

```yaml
identity:
  project: claude-plan-orchestrator
  agents:
    pipeline: CPO-Pipeline
    orchestrator: CPO-Orchestrator
    intake: CPO-Intake
    qa: CPO-QA
```

If not configured, display names are derived from the current directory name (e.g., directory `cheapoville` produces `Cheapoville-Pipeline`, `Cheapoville-Orchestrator`, etc.).

**Outbound signing**: Every Slack message is appended with ` -- *AgentName*` (em-dash, bold), where the agent name reflects the active role (orchestrator, pipeline, intake, or QA). The signature is appended after truncation so it is never cut off.

**Inbound filtering** applies four rules in order:
1. Messages signed by one of our own agents are skipped (self-loop prevention)
2. Messages addressed to another agent (`@OtherAgent`) but not to us are skipped
3. Messages addressed to one of our agents (`@OurAgent`) are processed
4. Messages without any `@` addressing (broadcasts) are processed

**Directed messages**: Use `@AgentName` in the message body to address a specific agent. Slack native `<@U...>` user mentions are not confused with agent addresses.

### LangSmith Tracing

The pipeline supports [LangSmith](https://smith.langchain.com) tracing for debugging and observability. Tracing is **opt-in** -- it must be explicitly enabled in the config, and both an API key and workspace ID are validated before any calls are made.

**Step 1: Get credentials**
1. Create a free account at [smith.langchain.com](https://smith.langchain.com)
2. Go to Settings > API Keys and create a new key
3. Copy your Workspace ID from the URL (`https://smith.langchain.com/o/<WORKSPACE-ID>/...`)

**Step 2: Enable in config** (`.claude/orchestrator-config.yaml`):

```yaml
langsmith:
  enabled: true
  project: "my-project"       # optional, defaults to "claude-plan-orchestrator"
```

**Step 3: Set credentials** in `.env.local` (gitignored):

```
LANGSMITH_API_KEY=lsv2_sk_...
LANGSMITH_WORKSPACE_ID=a3b32608-...
```

The pipeline loads `.env.local` then `.env` on startup. Existing env vars are never overwritten.

If `langsmith.enabled` is false (the default), tracing is off and no LangSmith calls are made. If enabled but credentials are missing, a single warning is logged and tracing is disabled. Use `--no-tracing` to skip all LangSmith configuration entirely.

## Configuration

### Project Configuration

Customize build and test commands in `.claude/orchestrator-config.yaml`:

```yaml
# Project name (used in Slack identity and logging)
project_name: my-project

# Build/test commands used during verification (defaults shown)
build_command: "pnpm run build"
test_command: "pnpm test"
dev_server_command: "pnpm dev"
dev_server_port: 3000
agents_dir: ".claude/agents"

# Agent identity for Slack (optional)
identity:
  project: my-project
  agents:
    pipeline: MyProject-Pipeline
    orchestrator: MyProject-Orchestrator
    intake: MyProject-Intake
    qa: MyProject-QA
```

**Next.js projects:** Set `build_command` to clear the `.next` cache before building. Next.js caches compiled chunks aggressively, and stale cache from a previous build can cause phantom build failures after code changes, wasting tokens on unnecessary debugging retries:

```yaml
build_command: "rm -rf .next && pnpm run build"
```

### Slack Configuration

Slack credentials and preferences are stored in `.claude/slack.local.yaml` (created by `scripts/setup-slack.py`):

```yaml
slack:
  enabled: true
  bot_token: xoxb-...
  app_token: xapp-...        # Required for Socket Mode (interactive buttons)
  channel_id: C...            # Primary notifications channel
  channel_prefix: myproject   # Channel naming prefix
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
- `## Status: Fixed` or `## Status: Completed` marks items as done (pipeline skips them)
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

### Pipeline Graph

1. **scan_backlog**: Scans `docs/defect-backlog/` and `docs/feature-backlog/` for items. Prioritizes defects over features. Checks for in-progress plans to resume
2. **intake_analyze**: Runs 5 Whys analysis on the item, checks for duplicates via RAG
3. **create_plan**: Creates a design document and YAML plan via Claude
4. **execute_plan**: Invokes the executor subgraph (see below)
5. **verify_fix** (defects only): Runs a read-only Claude session to verify the fix
6. **archive**: Moves completed items to `docs/completed-backlog/`

### Executor Subgraph

1. **task_selector**: Finds the next pending task (respecting dependencies and parallel groups)
2. **task_runner**: Runs `claude --dangerously-skip-permissions --print <prompt>` in a fresh session
3. **validator**: Checks `.claude/plans/task-status.json` for results, runs optional validation agents
4. **Loop**: Repeats until all tasks complete, circuit breaker trips, or budget is exhausted

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
+-- CODING-RULES.md                   # Coding standards (adapt for your project)
+-- langgraph_pipeline/               # Unified LangGraph pipeline (primary entry point)
|   +-- __main__.py                   # Module entry: python -m langgraph_pipeline
|   +-- cli.py                        # CLI argument parsing and main loop
|   +-- pipeline/                     # Pipeline graph nodes and edges
|   |   +-- graph.py                  # Graph assembly with SqliteSaver checkpointing
|   |   +-- state.py                  # PipelineState TypedDict
|   |   +-- edges.py                  # Conditional edge functions
|   |   +-- nodes/                    # Node implementations
|   |       +-- scan.py               # scan_backlog: find next work item
|   |       +-- intake.py             # intake_analyze: 5 Whys, RAG dedup
|   |       +-- plan_creation.py      # create_plan: design doc + YAML plan
|   |       +-- execute_plan.py       # execute_plan: invoke executor subgraph
|   |       +-- verification.py       # verify_fix: defect verification
|   |       +-- archival.py           # archive: move to completed
|   +-- executor/                     # Task execution subgraph
|   |   +-- graph.py                  # Executor graph assembly
|   |   +-- state.py                  # TaskState TypedDict
|   |   +-- edges.py                  # Conditional edges (done, should_retry, etc.)
|   |   +-- escalation.py            # Model tier escalation logic
|   |   +-- circuit_breaker.py        # Consecutive failure detection
|   |   +-- nodes/                    # Node implementations
|   |       +-- task_selector.py      # Pick next task respecting deps
|   |       +-- task_runner.py        # Run Claude CLI session
|   |       +-- validator.py          # Check task-status.json, run validators
|   |       +-- parallel.py           # Parallel worktree execution
|   +-- slack/                        # Slack integration
|   |   +-- __init__.py               # SlackNotifier facade
|   |   +-- notifier.py              # Outbound messaging, Block Kit formatting
|   |   +-- poller.py                # Background polling, LLM-powered routing
|   |   +-- suspension.py            # Q&A flows, 5 Whys intake analysis
|   |   +-- identity.py              # Agent identity, message signing
|   +-- shared/                       # Shared utilities
|       +-- paths.py                  # Standard path constants
|       +-- config.py                # orchestrator-config.yaml loader
|       +-- rate_limit.py            # Rate limit detection and parsing
|       +-- budget.py                # Budget tracking types
|       +-- claude_cli.py            # Claude CLI streaming helpers
|       +-- langsmith.py             # LangSmith tracing setup
+-- scripts/
|   +-- auto-pipeline.py             # Backward-compatible wrapper (calls langgraph_pipeline.cli)
|   +-- setup-slack.py               # Slack app and channel setup
+-- .claude/
|   +-- plans/
|   |   +-- sample-plan.yaml         # Template plan
|   |   +-- task-status.json         # Auto-generated task status
|   |   +-- .stop                    # Graceful stop semaphore
|   |   +-- .pipeline.pid            # Running process PID
|   +-- agents/                       # Agent definitions (YAML frontmatter)
|   +-- skills/implement/SKILL.md    # Implementation skill
|   +-- commands/implement.md         # /implement command
|   +-- orchestrator-config.yaml     # Project-specific config
|   +-- slack.local.yaml             # Slack credentials (user-created, gitignored)
|   +-- pipeline-state.db            # SQLite checkpoint database
|   +-- slack-last-read.json         # Per-channel Slack polling timestamps
|   +-- subagent-status/             # Parallel task heartbeats
|   +-- agent-claims.json            # File claim coordination
+-- docs/
    +-- plans/                        # Design documents
    +-- defect-backlog/              # Active defects
    +-- feature-backlog/             # Active features
    +-- completed-backlog/           # Archived completed items
    +-- setup-guide.md               # Full setup walkthrough
    +-- narrative/                    # Development history
```

## Tips

1. **Start Small**: Test with 2-3 tasks before running large plans
2. **Detailed Designs**: The design doc is crucial - be specific about file paths and steps
3. **Use Dependencies**: Declare `depends_on` to ensure correct execution order
4. **Parallel Where Possible**: Group independent tasks with `parallel_group` for faster execution
5. **Graceful Stop**: Use `touch .claude/plans/.stop` or Ctrl+C instead of `kill -9`
6. **Self-Extending Plans**: Let Claude add tasks during execution with `plan_modified: true`
7. **Monitor Progress**: Check the YAML file for status updates during execution
8. **Budget Caps**: Use `--budget-cap` for unattended runs to prevent runaway costs

## Troubleshooting

**Task keeps failing:**
- Check the error message in `last_error` field
- Increase `max_attempts` for complex tasks (default: 3, max recommended: 5)
- Simplify the task description
- The circuit breaker trips after 3 consecutive failures (300s cooldown)
- Model escalation automatically tries more capable models after failures

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
- The stop is checked between graph invocations, not mid-task
- For immediate termination, use `kill $(cat .claude/plans/.pipeline.pid)` instead

**Stale worktrees after crash:**
- Run `git worktree list` and `git worktree remove <path>` for orphans
- The orchestrator attempts cleanup, but crashes may leave worktrees behind

**Pipeline won't start (stale PID file):**
- If a previous run crashed without cleanup, a warning about an existing PID is logged
- The pipeline proceeds anyway; the PID file is overwritten on startup

**Checkpoint database issues:**
- The SQLite checkpoint database is at `.claude/pipeline-state.db`
- To force a clean start, delete this file (loses crash-recovery state)

## Development History

The orchestrator evolved from a 454-line sequential executor to a parallel execution engine, and was later rewritten as a modular LangGraph pipeline with SQLite-backed checkpointing, replacing the monolithic scripts. See [docs/narrative/](docs/narrative/) for the complete development history, including:

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
- LangGraph migration: unified pipeline and executor subgraphs

## License

MIT License - see [LICENSE](LICENSE)
