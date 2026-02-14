# Migrating from Manual-Copy to Plugin Installation

This guide helps existing users migrate from the manual file-copy installation
to the plugin-based installation of the Claude Plan Orchestrator.

---

## Why Migrate

The manual-copy workflow requires you to clone the repository and copy files
into each project. The plugin installation replaces this with a single command:

- **Automatic updates** -- run the install command again to get the latest version
- **Cleaner project directory** -- orchestrator files live in the plugin directory,
  not mixed into your project
- **No version drift** -- every project uses the same plugin version instead of
  whatever was copied at a given point in time
- **Simpler onboarding** -- new projects need only one install command

---

## Prerequisites

- Claude Code CLI with plugin support
- An existing project that was set up using the manual-copy workflow

---

## Migration Steps

### Step 1: Back Up Your Current .claude/ Directory

Before making any changes, create a backup of your entire .claude/ directory:

```bash
cp -r .claude .claude-backup
```

This ensures you can restore everything if something goes wrong.

### Step 2: Identify Your Project-Specific Files

Your .claude/ directory contains two kinds of files:

**Orchestrator-provided files** (will be replaced by the plugin):

- .claude/agents/coder.md
- .claude/agents/code-reviewer.md
- .claude/skills/implement/SKILL.md
- .claude/skills/coding-rules/SKILL.md
- .claude/commands/implement.md

**Project-provided files** (copied from the orchestrator repo as templates):

- .claude/orchestrator-config.yaml
- .claude/plans/sample-plan.yaml
- CODING-RULES.md (at project root)

**Your project-specific files** (created by you, must be preserved):

- .claude/orchestrator-config.yaml (if you customized it)
- .claude/plans/*.yaml (your implementation plans)
- docs/plans/*.md (your design documents)
- CODING-RULES.md (if you customized it for your project)

### Step 3: Remove Orchestrator-Provided Files

Remove the files that the plugin will provide. Keep your project-specific files:

```bash
rm .claude/agents/coder.md
rm .claude/agents/code-reviewer.md
rm .claude/skills/implement/SKILL.md
rm .claude/skills/coding-rules/SKILL.md
rm .claude/commands/implement.md
```

Also remove the copied scripts directory if you had one:

```bash
rm -rf scripts/plan-orchestrator.py scripts/auto-pipeline.py
```

Do NOT remove:

- .claude/orchestrator-config.yaml
- .claude/plans/ (your plans)
- docs/ (your design documents)
- CODING-RULES.md (if you customized it)

### Step 4: Install the Plugin

```bash
claude plugin install martinbechard/claude-plan-orchestrator
```

This installs the orchestrator as a plugin. Claude Code will automatically
discover the agents, skills, and commands from the plugin directory.

### Step 5: Verify the Plugin Is Active

Start Claude Code and verify:

1. The /implement command is available
2. The coder and code-reviewer agents are listed
3. The coding-rules and implement skills are available

You can also check installed plugins:

```bash
claude plugin list
```

### Step 6: Test With an Existing Plan

Run a dry-run of one of your existing plans to confirm everything works:

```bash
python3 "$(claude plugin path plan-orchestrator)/scripts/plan-orchestrator.py" \
  --plan .claude/plans/your-plan.yaml --dry-run
```

---

## What Stays the Same

After migrating to the plugin, the following are unchanged:

- **YAML plan format** -- your existing .yaml plan files work without modification
- **Design document structure** -- docs/plans/*.md files are unchanged
- **/implement command** -- same command, same behavior
- **orchestrator-config.yaml** -- same location (.claude/), same format
- **Agent behavior** -- the coder and code-reviewer agents work identically
- **CODING-RULES.md** -- your project-level customizations are preserved

---

## Accessing Scripts After Plugin Install

With the manual-copy workflow, scripts lived in your project's scripts/ directory.
After plugin install, they live in the plugin directory.

### Finding the Plugin Directory

```bash
claude plugin path plan-orchestrator
```

This prints the absolute path to the plugin directory.

### Running plan-orchestrator.py

```bash
python3 "$(claude plugin path plan-orchestrator)/scripts/plan-orchestrator.py" \
  --plan .claude/plans/your-plan.yaml
```

### Running auto-pipeline.py

```bash
python3 "$(claude plugin path plan-orchestrator)/scripts/auto-pipeline.py" \
  --config .claude/orchestrator-config.yaml
```

You can create a shell alias for convenience:

```bash
alias plan-orchestrator='python3 "$(claude plugin path plan-orchestrator)/scripts/plan-orchestrator.py"'
alias auto-pipeline='python3 "$(claude plugin path plan-orchestrator)/scripts/auto-pipeline.py"'
```

---

## Rollback

If you need to go back to the manual-copy workflow:

### Step 1: Uninstall the Plugin

```bash
claude plugin uninstall plan-orchestrator
```

### Step 2: Restore From Backup

If you kept your backup:

```bash
cp -r .claude-backup/* .claude/
```

### Step 3: Or Re-Copy From the Repository

Clone the orchestrator repository and copy the files back:

```bash
git clone https://github.com/martinbechard/claude-plan-orchestrator.git /tmp/orchestrator

cp /tmp/orchestrator/.claude/agents/*.md .claude/agents/
cp /tmp/orchestrator/.claude/skills/implement/SKILL.md .claude/skills/implement/
cp /tmp/orchestrator/.claude/skills/coding-rules/SKILL.md .claude/skills/coding-rules/
cp /tmp/orchestrator/.claude/commands/implement.md .claude/commands/
cp /tmp/orchestrator/scripts/plan-orchestrator.py scripts/
cp /tmp/orchestrator/scripts/auto-pipeline.py scripts/

rm -rf /tmp/orchestrator
```

Your project-specific files (orchestrator-config.yaml, plans, design docs)
are unaffected by either installation method.
