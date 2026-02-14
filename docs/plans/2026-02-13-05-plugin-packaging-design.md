# Plugin Packaging and Distribution - Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use the implement skill to execute this plan task-by-task.

**Goal:** Package the plan orchestrator as a Claude Code plugin for one-command installation, replacing the manual copy-files workflow.

**Architecture:** Create a plugin.json manifest in the project root, reorganize the CODING-RULES.md into a preloadable skill with progressive disclosure, add a marketplace.json for team distribution, update README with plugin installation instructions, and create a migration guide for existing manual-copy users. The existing .claude/ directory structure (agents, skills, commands) already matches Claude Code plugin conventions, so the restructuring is minimal.

**Tech Stack:** Python 3 (scripts), YAML (plans), Markdown with YAML frontmatter (agents, skills, commands), JSON (plugin.json, marketplace.json)

**Dependencies:** Feature 02 (Agent Definition Framework) - completed, Feature 03 (Per-Task Validation Pipeline) - completed

---

## Architecture Overview

### Current State

The project distributes via manual file copy:
- Users clone the repo and copy .claude/, scripts/, CODING-RULES.md to their project
- No version tracking, no update mechanism, no dependency declaration
- The .claude/ directory already follows plugin conventions (agents/, skills/, commands/)

### Target State

A Claude Code plugin installable via:
- Local development: claude --plugin-dir /path/to/claude-plan-orchestrator
- GitHub install: claude plugin install martinbechard/claude-plan-orchestrator
- Team marketplace: claude plugin install plan-orchestrator (via marketplace.json)

### What Changes

1. **plugin.json** at project root - manifest declaring plugin metadata, entry points
2. **skills/coding-rules/** - CODING-RULES.md packaged as a preloadable skill with SKILL.md entry
3. **marketplace.json** - team marketplace configuration for discovery
4. **CHANGELOG.md** - version history tracking
5. **README.md** - updated with plugin installation instructions
6. **Migration guide** - docs for existing manual-copy users

### What Does NOT Change

- The .claude/ directory structure (agents, skills, commands already in place)
- scripts/ directory (plan-orchestrator.py, auto-pipeline.py)
- The orchestrator-config.yaml in .claude/
- Existing YAML plans and design docs

---

## Key Files

### New Files

| File | Purpose |
|------|---------|
| plugin.json | Plugin manifest with name, version, description, entry points |
| marketplace.json | Team marketplace configuration for plugin discovery |
| .claude/skills/coding-rules/SKILL.md | Entry point for CODING-RULES.md as a preloadable skill |
| docs/migration-from-manual-copy.md | Migration guide for existing users |
| CHANGELOG.md | Version history tracking |

### Modified Files

| File | Change |
|------|--------|
| README.md | Add plugin installation section, keep manual-copy as fallback |
| .gitignore | Add plugin-specific ignores if needed |

---

## Design Decisions

### 1. Plugin Manifest (plugin.json)

The plugin.json lives at the project root and declares:
- name: "plan-orchestrator"
- version: "1.0.0" (semver)
- description: from README first paragraph
- author: "martinbechard"
- repository: GitHub URL
- license: "MIT"
- keywords: ["orchestrator", "plan", "automation", "parallel"]
- entry points: agents, skills, commands directories under .claude/

The manifest maps the .claude/ subdirectories as plugin components. Claude Code discovers agents from .claude/agents/, skills from .claude/skills/, and commands from .claude/commands/ automatically.

### 2. CODING-RULES as a Skill (Progressive Disclosure)

Package CODING-RULES.md with progressive disclosure:
- .claude/skills/coding-rules/SKILL.md - concise entry point (summary of rules with references)
- CODING-RULES.md stays at root as the full reference document
- SKILL.md references CODING-RULES.md for full details when needed

Role-specific subsets are NOT implemented in this phase. The full rules document is small enough to serve all agent roles. Role-specific subsets can be added later if needed.

### 3. Marketplace Configuration

marketplace.json at project root enables team discovery:
- Points to the GitHub repository
- Declares compatible Claude Code versions
- Includes installation instructions

### 4. Manual-Copy Fallback Preserved

The README keeps the manual-copy instructions in a "Manual Installation (Alternative)" section. This ensures existing users are not broken and provides a fallback for environments where plugin install is not available.

### 5. Version Strategy

Start at 1.0.0. The project is functional and has been used in production. Future versions follow semver. CHANGELOG.md tracks all releases.

### 6. Scripts Accessibility

The scripts/ directory (plan-orchestrator.py, auto-pipeline.py) must remain accessible after plugin install. Claude Code plugins expose their directory path, so scripts can be run via the plugin path. The README documents this with examples.

---

## Verification Strategy

1. Validate plugin.json syntax with Python json.load
2. Verify plugin install from local directory (--plugin-dir)
3. Verify skills, commands, agents are discovered correctly
4. Verify manual-copy workflow still works
5. Dry-run orchestrator to confirm no regressions
