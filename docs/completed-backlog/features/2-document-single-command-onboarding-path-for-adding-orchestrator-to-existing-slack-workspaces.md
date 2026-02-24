# Document single-command onboarding path for adding orchestrator to existing Slack workspaces

## Status: Open

## Priority: Medium

## Summary

Add a prominent "Adding to an existing workspace" section to the README and setup guide with a copy-pasteable `setup-slack.py --bot-token ... --app-token ... --prefix ... --non-interactive` command. Verify this flow works end-to-end for the cheapoville use case. If any gaps exist (e.g., missing scopes), fix them in the script rather than building browser automation.

## 5 Whys Analysis

  1. Why do users want Chrome MCP browser automation for Slack channel setup? Because setting up the private Slack channels and inviting the bot feels like a manual, error-prone process that creates onboarding friction for new projects.
  2. Why does channel setup feel manual when `setup-slack.py` already exists? Because the script's existence and its non-interactive mode aren't prominently documented — adopters from other projects (like cheapoville) don't discover it before concluding they need browser automation.
  3. Why isn't the setup script discoverable to cross-project adopters? Because the README and setup guide were written for first-time single-project setup, not for the "add orchestrator to a second project in an existing workspace" workflow.
  4. Why isn't the second-project workflow documented as a first-class path? Because the orchestrator evolved from a single-project tool, and multi-project reuse via `--bot-token --app-token --prefix --non-interactive` was added as a capability without updating the docs to highlight it as a primary use case.
  5. Why weren't the docs updated when multi-project support was added? Because there was no onboarding experience review after adding the feature — the assumption was that the person setting it up would already know the tool, missing the fact that cross-project adoption is the main growth vector.

**Root Need:** Cross-project adopters need a clearly documented, copy-pasteable single-command onboarding path for reusing an existing Slack app with a new project prefix, not browser automation.

## Source

Created from Slack message by U0AG70DCQ1K at 1771688535.933679.
