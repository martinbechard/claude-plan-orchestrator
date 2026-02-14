# Plugin Packaging and Distribution

## Status: Open

## Priority: Medium

## Summary

Package the orchestrator, auto-pipeline, agents, skills, and commands as a
Claude Code plugin for one-command installation and automatic updates. Replace
the current "copy files manually" distribution with a proper plugin manifest,
marketplace configuration, and versioned releases.

## Scope

### Plugin Directory Structure

Restructure the project to follow Claude Code plugin conventions:

- .claude-plugin/plugin.json - Plugin manifest with name, version, description
- agents/ - All agent definitions
- skills/ - implement skill, coding-rules skill
- commands/ - /implement command
- hooks/ - Event handlers (SubagentStop for validation)
- scripts/ - plan-orchestrator.py, auto-pipeline.py

### Plugin Manifest

Create plugin.json with proper metadata, version (semver), author, repository,
license, and keywords.

### Skills Packaging

Package CODING-RULES.md as a preloadable skill with progressive disclosure:
- SKILL.md as concise entry point
- Full rules as supporting file loaded on demand
- Optional subsets for different agent roles (coder, reviewer, designer)

### Distribution Strategy

1. GitHub repository with marketplace.json for team marketplace installation
2. Document installation via: claude plugin install plan-orchestrator
3. Document development workflow via: --plugin-dir flag
4. Migration guide for existing manual-copy users

### README and Documentation

- Update README with plugin installation instructions
- Add CHANGELOG.md for version tracking
- Document the agent architecture and validation flow

## Verification

- Test plugin install from local directory (--plugin-dir)
- Test that skills, commands, agents, and hooks are discovered correctly
- Test plugin update and uninstall lifecycle
- Verify manual-copy workflow still works as fallback

## Dependencies

- 02-agent-definition-framework.md
- 03-per-task-validation-pipeline.md
