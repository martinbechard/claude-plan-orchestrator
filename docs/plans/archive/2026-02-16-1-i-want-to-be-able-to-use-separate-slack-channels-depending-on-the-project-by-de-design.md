# Per-Project Slack Channel Prefix Design

> **For Claude:** REQUIRED SUB-SKILL: Use the implement skill to execute this plan task-by-task.

**Goal:** Allow each project to use its own set of Slack channels by configuring
a custom channel name prefix. Currently the prefix is hardcoded as "orchestrator-"
which creates channels like orchestrator-features, orchestrator-defects, etc.
Projects that share a Slack workspace need independent channel sets (e.g.
"myproject-features", "myproject-defects").

**Architecture:** Add a "channel_prefix" field to two configuration files:
1. The Slack-specific config (.claude/slack.local.yaml) - where the user sets
   their project-specific prefix
2. The orchestrator config (.claude/orchestrator-config.yaml) - as an alternative
   location for non-Slack-specific settings

The SlackNotifier reads the prefix from its config and uses it instead of the
hardcoded constant. The SLACK_CHANNEL_PREFIX constant becomes the default
fallback. The SLACK_CHANNEL_ROLES dict is rebuilt dynamically from the prefix.

**Tech Stack:** Python (existing codebase), YAML config

---

## Key Design Decisions

1. **Config lives in slack.local.yaml.** The channel prefix is fundamentally a
   Slack configuration concern, so it belongs in the Slack config file. The user
   sets "channel_prefix: myproject-" and the system discovers channels named
   myproject-features, myproject-defects, myproject-questions, myproject-notifications.

2. **Default prefix is "orchestrator-".** If no channel_prefix is set, the
   system behaves exactly as before. This provides full backward compatibility
   with zero migration effort for existing users.

3. **Dynamic SLACK_CHANNEL_ROLES.** Instead of a hardcoded dict mapping full
   channel names to roles, we build the mapping at runtime from the prefix and
   a fixed set of role suffixes (features, defects, questions, notifications).
   This means the role suffixes are constant but the prefix is configurable.

4. **Template updated with documentation.** The slack.local.yaml.template gets
   the new field with a comment explaining its purpose and default value.

---

## Files to Modify

| File | Change |
|---|---|
| .claude/slack.local.yaml.template | Add channel_prefix field with documentation |
| scripts/plan-orchestrator.py | Read channel_prefix from config, use it in discovery and role mapping |
| tests/test_slack_notifier.py | Add tests for custom prefix behavior |

---

## Implementation Details

### Config Change

In .claude/slack.local.yaml.template, add after channel_id:

```
  # Prefix for Slack channel names used by this project.
  # Channels are discovered by this prefix + role suffix:
  #   {prefix}features, {prefix}defects, {prefix}questions, {prefix}notifications
  # Default: "orchestrator-"
  channel_prefix: "orchestrator-"
```

### Constants Change

Replace the hardcoded SLACK_CHANNEL_ROLES dict with:
- SLACK_CHANNEL_ROLE_SUFFIXES: a dict mapping suffix to role
  ("features" -> "feature", "defects" -> "defect", etc.)
- Keep SLACK_CHANNEL_PREFIX as the default fallback

### SlackNotifier Changes

- Read channel_prefix from slack config in __init__
- Store as self._channel_prefix
- In _discover_channels: use self._channel_prefix instead of SLACK_CHANNEL_PREFIX
- Add a _get_channel_role(channel_name) method that strips the prefix and
  looks up the suffix in SLACK_CHANNEL_ROLE_SUFFIXES
- In _handle_polled_messages: use _get_channel_role instead of SLACK_CHANNEL_ROLES.get
