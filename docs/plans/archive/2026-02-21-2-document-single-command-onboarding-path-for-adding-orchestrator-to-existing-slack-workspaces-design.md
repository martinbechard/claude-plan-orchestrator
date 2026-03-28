# Design: Single-Command Onboarding for Existing Slack Workspaces

## Source

docs/feature-backlog/2-document-single-command-onboarding-path-for-adding-orchestrator-to-existing-slack-workspaces.md

## Problem

Cross-project adopters who already have a Slack app running in one project cannot
easily discover the one-liner to add the orchestrator to a second project. The
existing docs bury the "reuse an existing app" path under the first-time setup flow.
Adopters conclude they need browser automation instead of the already-supported
non-interactive mode.

## Current State

- setup-slack.py supports --bot-token, --app-token, --prefix, --non-interactive
- setup-guide.md mentions the second-project flow in a one-line paragraph at step 3
- README.md mentions --bot-token/--app-token in the Slack Integration section (line 459)
  but doesn't highlight it as a primary onboarding path
- No prominent "Adding to an existing workspace" section exists in either doc

## Design

### Documentation Changes

#### README.md

Add a new subsection under "Slack Integration" called "Adding a Second Project to
an Existing Workspace" immediately after the "Setup:" paragraph (after line 459).
This section provides:

1. The copy-pasteable one-liner command
2. A brief explanation of what it does (creates new prefix-* channels, writes config)
3. A pointer to the setup guide for full details

#### docs/setup-guide.md

Add a new section "Adding to an Existing Workspace" between step 3 (Set up Slack)
and step 4 (Configure the project). This section provides:

1. When to use this path (you already have a Slack app from another project)
2. Where to find your existing tokens (the other project's .claude/slack.local.yaml)
3. The full copy-pasteable command with all flags explained
4. What the command creates (channels, config file)
5. Next steps (proceed to step 4 for project config)

### Script Verification

Verify the --non-interactive flow works end-to-end:

1. Run setup-slack.py --prefix testprefix --bot-token ... --app-token ...
   --non-interactive --dry-run (if supported) or review the code path
2. Confirm no gaps exist (e.g., missing scope checks, error handling)
3. If gaps are found, fix them in the script

### Key Files

| File | Action |
|------|--------|
| README.md | Add "Adding a Second Project" subsection |
| docs/setup-guide.md | Add "Adding to an Existing Workspace" section |
| scripts/setup-slack.py | Verify non-interactive flow; fix any gaps |

### Design Decisions

1. Documentation-first: The script already works. The primary deliverable is
   making it discoverable.
2. Copy-pasteable command: The docs must contain a single command that a user
   can copy, fill in their tokens, and run. No multi-step instructions.
3. No browser automation: The 5 Whys analysis confirmed that browser automation
   is not needed. The docs should make this clear.
4. Preserve existing structure: New sections are inserted at logical positions
   in the existing docs, not restructured.
