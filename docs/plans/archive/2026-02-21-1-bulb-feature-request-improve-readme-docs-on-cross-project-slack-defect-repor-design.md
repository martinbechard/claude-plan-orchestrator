# Design: Consumer-Facing Cross-Project Slack Documentation

## Overview

Add a step-by-step "Reporting Issues to an Upstream Orchestrator" section to the
README that teaches consumer project operators how to set up cross-instance
defect/feature reporting via shared Slack channels.

## Problem

The README's "Cross-Instance Collaboration via Slack" section explains what is
architecturally possible but provides no actionable consumer-facing setup
instructions. A downstream project operator reading the docs cannot reproduce
the setup without tacit knowledge about Slack channel naming, bot invitations,
and message routing.

## Scope

Documentation-only change. No code modifications required.

### Files to Modify

- README.md -- add a new subsection under the existing "Cross-Instance
  Collaboration via Slack" section
- docs/setup-guide.md -- add a "Cross-Project Reporting" section with the
  consumer-side setup walkthrough

## Design Decisions

### 1. Where to put the documentation

The README already has a "Cross-Instance Collaboration via Slack" section
(lines 463-474). The new consumer-facing guide belongs as a subsection
immediately after that, titled "Setting Up Cross-Project Reporting (Consumer
Side)". The setup guide gets a corresponding section with the detailed
step-by-step walkthrough.

### 2. What the consumer guide must cover

Three topics (derived from the 5 Whys analysis in the backlog item):

1. **Channel naming convention** -- explain that orchestrator channels use a
   prefix (e.g., upstream-defects, upstream-features) and that the consumer
   project must know the upstream project's prefix to target the right channels.

2. **Bot invitation** -- the consumer project's Slack bot must be invited to
   the upstream project's channels. Document the Slack /invite command and
   the required bot scopes (channels:read, chat:write, channels:history).

3. **Message routing** -- explain how send_defect/send_idea post to the
   channels the bot has access to, and how the channel_prefix in
   orchestrator-config.yaml determines which channels are targeted.
   Cover the agent identity protocol that prevents self-loop messages.

### 3. Structure approach

Keep the README section concise (overview + pointer to setup guide).
Put the detailed step-by-step procedure in docs/setup-guide.md where
the existing setup instructions live.

## Task Breakdown

Single task: update README.md and docs/setup-guide.md with the consumer-facing
cross-project reporting documentation.
