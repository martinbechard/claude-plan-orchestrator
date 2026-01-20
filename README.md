# Claude Plan Orchestrator

Automate multi-step implementation plans with Claude Code.

## Overview

The Plan Orchestrator executes structured YAML plans through Claude Code, providing:

- **Automated Execution**: Run tasks sequentially with retry logic
- **Status Tracking**: JSON-based communication between orchestrator and Claude
- **Git Integration**: Auto-commit after each successful task
- **Plan Modification**: Claude can split, add, or skip tasks as needed

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    YAML      │────▶│ Orchestrator │────▶│ Claude Code  │
│    Plan      │     │   (Python)   │     │   (claude)   │
└──────────────┘     └──────────────┘     └──────────────┘
       ▲                                         │
       │           ┌──────────────┐              │
       └───────────│ task-status  │◀─────────────┘
                   │    .json     │
                   └──────────────┘
```

## Requirements

- Python 3.8+
- PyYAML (`pip install pyyaml`)
- Claude Code CLI installed and authenticated

## Installation

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
cp .claude/skills/implement/SKILL.md /your/project/.claude/skills/implement/

# Optional (for manual invocation)
cp .claude/commands/implement.md /your/project/.claude/commands/
cp .claude/plans/sample-plan.yaml /your/project/.claude/plans/
```

## Quick Start

### 1. Create your plan

```bash
# Copy the sample plan
cp .claude/plans/sample-plan.yaml .claude/plans/my-feature.yaml
```

Edit the plan with your tasks:

```yaml
meta:
  name: My Feature
  description: What this plan accomplishes
  plan_doc: docs/plans/2025-01-20-my-feature-design.md
  created: '2025-01-20'
  max_attempts_default: 3

sections:
- id: phase-1
  name: Setup
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
```

### 2. Create your design document

Write detailed implementation steps at `docs/plans/2025-01-20-my-feature-design.md`. The more detailed, the better Claude will execute.

### 3. Run the orchestrator

```bash
# Dry run first (shows what would execute)
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml --dry-run

# Run all pending tasks
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml

# Run single task then stop
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml --single-task

# Resume from specific task
python scripts/plan-orchestrator.py --plan .claude/plans/my-feature.yaml --resume-from 2.1
```

## Manual Execution

You can also run tasks manually using the `/implement` command in Claude Code:

```
/implement        # Run next pending task
/implement 2.1    # Run specific task by ID
```

## How It Works

1. **Find Next Task**: Orchestrator finds first `pending` or `in_progress` task
2. **Build Prompt**: Creates prompt with task details and plan document reference
3. **Execute Claude**: Runs `claude --dangerously-skip-permissions --print <prompt>`
4. **Check Status**: Reads `.claude/plans/task-status.json` for result
5. **Update Plan**: Marks task complete/failed in YAML
6. **Commit**: Auto-commits changes to git
7. **Repeat**: Continues until all tasks done or max attempts exceeded

## Status File

Claude writes its status to `.claude/plans/task-status.json`:

```json
{
  "task_id": "1.1",
  "status": "completed",
  "message": "What was accomplished",
  "timestamp": "2025-01-20T12:00:00Z",
  "plan_modified": false
}
```

The orchestrator reads this to determine success/failure.

## Task Statuses

- `pending` - Not yet started
- `in_progress` - Currently being executed
- `completed` - Successfully finished
- `failed` - Failed after max attempts
- `skipped` - Manually skipped with reason

## Plan Modification

Claude can modify the YAML plan during execution:

- **Split tasks**: Large task 2.1 becomes 2.1a, 2.1b, 2.1c
- **Add tasks**: Insert discovered work
- **Skip tasks**: Mark unnecessary tasks as skipped
- **Add notes**: Document important context

Set `plan_modified: true` in status file to trigger reload.

## Directory Structure

```
your-project/
├── .claude/
│   ├── plans/
│   │   ├── sample-plan.yaml    # Template plan
│   │   ├── current-plan.yaml   # Your active plan
│   │   └── task-status.json    # Auto-generated status
│   ├── skills/
│   │   └── implement/
│   │       └── SKILL.md        # Implementation skill
│   └── commands/
│       └── implement.md        # /implement command
├── scripts/
│   └── plan-orchestrator.py    # Orchestrator script
└── docs/
    └── plans/
        └── YYYY-MM-DD-*.md     # Design documents
```

## Tips

1. **Start Small**: Test with 2-3 tasks before running large plans
2. **Detailed Designs**: The design doc is crucial - be specific about file paths and steps
3. **Check Logs**: Review orchestrator output and task-status.json
4. **Commit Often**: The orchestrator commits after each successful task
5. **Manual Override**: You can manually edit task status in the YAML if needed

## Troubleshooting

**Task keeps failing:**
- Check the error message in `last_error` field
- Increase `max_attempts` for complex tasks
- Simplify the task description

**Claude doesn't write status file:**
- Ensure the implement skill is in `.claude/skills/implement/SKILL.md`
- Check Claude has write access to `.claude/plans/`

**Plan not found:**
- Use absolute path or run from project root
- Check file permissions

## License

MIT License - see [LICENSE](LICENSE)
