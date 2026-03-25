#!/usr/bin/env python3
# scripts/setup-project.py
# Bootstrap a new project with claude-plan-orchestrator.
# Design: docs/plans/2026-03-25-17-project-setup-script-design.md

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).parent.parent

TEMPLATE_CONFIG = SOURCE_ROOT / "scripts" / "setup-templates" / "orchestrator-config.yaml"
AGENTS_SRC = SOURCE_ROOT / ".claude" / "agents"
CODING_RULES_SRC = SOURCE_ROOT / "procedure-coding-rules.md"

BACKLOG_DIRS = [
    "docs/defect-backlog",
    "docs/feature-backlog",
    "docs/analysis-backlog",
]

CHROME_MCP_NAME = "chrome"

MANUAL_SLACK_INSTRUCTIONS = """
Manual Slack App Setup Instructions:
  1. Go to https://api.slack.com/apps and click "Create New App" > "From scratch"
  2. Name it after your project, select your workspace, click "Create App"
  3. Go to "OAuth & Permissions", add these Bot Token Scopes:
       channels:history, channels:read, chat:write, reactions:read,
       reactions:write, users:read
  4. Click "Install to Workspace" and authorize
  5. Copy the "Bot User OAuth Token" (starts with xoxb-)
  6. Go to "Basic Information" > "Signing Secret" and copy it
  7. Create a file at .claude/slack.local.yaml with:
       bot_token: "xoxb-your-token"
       signing_secret: "your-signing-secret"
  8. Add your channel names to .claude/orchestrator-config.yaml under:
       slack:
         channels:
           notifications: "#your-notifications-channel"
           defects: "#your-defects-channel"
           features: "#your-features-channel"
           questions: "#your-questions-channel"
"""

CONFIGURE_PROMPT_TEMPLATE = """You are helping set up a new project using claude-plan-orchestrator.
The project is located at: {target}

Read the file {config_path} to understand all available configuration fields.

Then use AskUserQuestion to collect the following values from the user:

1. Project name (used for Slack display names and LangSmith project)
2. Agent display name prefix (e.g. "MYPROJ" -> agents will be "MYPROJ-Pipeline", etc.)
   Defaults to project name uppercased if skipped.
3. LangSmith tracing: does the user want to enable it? (yes/no)
   If yes: ask for their LANGSMITH_API_KEY and LANGSMITH_WORKSPACE_ID.
   Write them to {env_local_path} (create the file if missing).
4. Web UI: should the web dashboard be enabled? (yes/no)
   If yes: ask for the port number (default 8080).
5. Build command (default: leave blank to keep existing default)
6. Test command (default: leave blank to keep existing default)
7. Slack integration: does the user want Slack notifications? (yes/no)
   (Just record yes/no - Slack credentials will be set up separately)

After collecting answers, update {config_path} with the provided values:
- Set identity.project to the project name
- Set identity.agents.pipeline, orchestrator, intake, qa using the prefix
- Set langsmith.enabled and langsmith.project if LangSmith was enabled
- Set dev_server_port if web UI was requested
- Set build_command if provided
- Set test_command if provided

Use the Edit or Write tool to write the updated YAML. Preserve all existing comments.
Print "CONFIGURATION_COMPLETE" when done, or "CONFIGURATION_FAILED: <reason>" if something went wrong.
"""

SLACK_MCP_PROMPT_TEMPLATE = """You are helping set up a Slack app for a project using claude-plan-orchestrator.
The project is located at: {target}
The project name is: {project_name}

Use the Chrome MCP tool to:
1. Open https://api.slack.com/apps in the browser
2. Click "Create New App" > "From scratch"
3. Name the app "{project_name}" and select the workspace
4. Go to "OAuth & Permissions" and add these Bot Token Scopes:
   channels:history, channels:read, chat:write, reactions:read, reactions:write, users:read
5. Click "Install to Workspace" and complete authorization
6. Copy the "Bot User OAuth Token" (starts with xoxb-)
7. Go to "Basic Information" > "Signing Secret" and copy it
8. Use AskUserQuestion to ask the user for:
   - Channel names for: notifications, defects, features, questions
   (User should create these Slack channels first if they don't exist)

Then write the credentials:
- Create {slack_local_path} with:
    bot_token: "<the xoxb- token>"
    signing_secret: "<the signing secret>"

- Update {config_path} to add:
    slack:
      channels:
        notifications: "<channel name>"
        defects: "<channel name>"
        features: "<channel name>"
        questions: "<channel name>"

Print "SLACK_SETUP_COMPLETE" when done, or "SLACK_SETUP_FAILED: <reason>" if something went wrong.
"""


def scaffold_files(target: Path, force: bool) -> None:
    """Copy template files and agent definitions into the target project."""
    copied = []
    skipped = []

    def copy_file(src: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not force:
            skipped.append(str(dest))
            return
        shutil.copy2(src, dest)
        copied.append(str(dest))

    # Copy orchestrator config template
    config_dest = target / ".claude" / "orchestrator-config.yaml"
    copy_file(TEMPLATE_CONFIG, config_dest)

    # Copy all agent .md files
    if AGENTS_SRC.is_dir():
        for agent_file in sorted(AGENTS_SRC.glob("*.md")):
            copy_file(agent_file, target / ".claude" / "agents" / agent_file.name)

    # Copy coding rules procedure
    if CODING_RULES_SRC.exists():
        copy_file(CODING_RULES_SRC, target / CODING_RULES_SRC.name)

    # Create backlog directories with .gitkeep
    for rel_dir in BACKLOG_DIRS:
        dest_dir = target / rel_dir
        is_new = not dest_dir.exists()
        dest_dir.mkdir(parents=True, exist_ok=True)
        gitkeep = dest_dir / ".gitkeep"
        if is_new:
            gitkeep.touch()
            copied.append(str(gitkeep))
        else:
            skipped.append(str(dest_dir) + " (already exists)")

    # Print summary
    print(f"\nScaffolding complete: {len(copied)} copied, {len(skipped)} skipped.")
    if copied:
        print("  Copied:")
        for path in copied:
            print(f"    + {path}")
    if skipped:
        print("  Skipped (use --force to overwrite):")
        for path in skipped:
            print(f"    - {path}")


def configure_interactive(target: Path) -> bool:
    """Launch a Claude Code session to interactively configure orchestrator-config.yaml.

    Returns True if configuration succeeded, False otherwise.
    """
    config_path = target / ".claude" / "orchestrator-config.yaml"
    env_local_path = target / ".env.local"

    prompt = CONFIGURE_PROMPT_TEMPLATE.format(
        target=target,
        config_path=config_path,
        env_local_path=env_local_path,
    )

    print("\n[Phase 2] Launching Claude Code for interactive configuration...")
    print("  Claude will ask you questions to configure the project.\n")

    result = subprocess.run(
        ["claude", "--print", prompt, "--dangerously-skip-permissions"],
        cwd=target,
        text=True,
    )

    if result.returncode != 0:
        print(f"\n[Phase 2] Configuration session failed (exit code {result.returncode}).")
        return False

    print("\n[Phase 2] Configuration complete.")
    return True


def check_chrome_mcp() -> bool:
    """Check whether the Chrome MCP server is available in the Claude config.

    Returns True if Chrome MCP is configured, False otherwise.
    """
    claude_config_paths = [
        Path.home() / ".claude" / "claude_desktop_config.json",
        Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
    ]

    for config_path in claude_config_paths:
        if not config_path.exists():
            continue
        try:
            with open(config_path) as f:
                config = json.load(f)
            mcp_servers = config.get("mcpServers", {})
            if CHROME_MCP_NAME in mcp_servers:
                return True
        except (json.JSONDecodeError, OSError):
            continue

    return False


def setup_slack_via_mcp(target: Path, project_name: str) -> bool:
    """Launch a Claude Code session to set up Slack via Chrome MCP.

    Returns True if Slack setup succeeded, False otherwise.
    """
    config_path = target / ".claude" / "orchestrator-config.yaml"
    slack_local_path = target / ".claude" / "slack.local.yaml"

    prompt = SLACK_MCP_PROMPT_TEMPLATE.format(
        target=target,
        project_name=project_name,
        config_path=config_path,
        slack_local_path=slack_local_path,
    )

    print("\n[Phase 3] Launching Claude Code for Slack setup via Chrome MCP...")
    print("  Claude will open Slack API in your browser and guide you through app creation.\n")

    result = subprocess.run(
        ["claude", "--print", prompt, "--dangerously-skip-permissions"],
        cwd=target,
        text=True,
    )

    if result.returncode != 0:
        print(f"\n[Phase 3] Slack setup session failed (exit code {result.returncode}).")
        return False

    print("\n[Phase 3] Slack setup complete.")
    return True


def run_smoke_test(target: Path, slack_configured: bool) -> bool:
    """Run the pipeline in dry-run mode to verify the setup.

    Returns True if the smoke test passed, False otherwise.
    """
    print("\n[Phase 4] Running smoke test...")

    cmd = [sys.executable, "-m", "langgraph_pipeline", "--dry-run"]
    if not slack_configured:
        cmd.append("--no-slack")

    result = subprocess.run(
        cmd,
        cwd=target,
        text=True,
        capture_output=True,
    )

    if result.stdout:
        print(result.stdout)

    if result.returncode == 0:
        print("\n[Phase 4] Smoke test PASSED.")
        print("\nSetup complete! Next steps:")
        print("  1. Review .claude/orchestrator-config.yaml and adjust any settings")
        print("  2. Add your backlog items to docs/feature-backlog/ or docs/defect-backlog/")
        print("  3. Run: python scripts/plan-orchestrator.py --plan .claude/plans/<plan>.yaml")
        return True
    else:
        print("\n[Phase 4] Smoke test FAILED.")
        if result.stderr:
            print("\nError output:")
            print(result.stderr)
        print("\nHint: Set DEBUG=true in your environment for more verbose output.")
        print("      Check that langgraph_pipeline is installed: pip install -e .")
        return False


def _read_project_name(target: Path) -> str:
    """Read project name from orchestrator-config.yaml, falling back to directory name."""
    config_path = target / ".claude" / "orchestrator-config.yaml"
    if config_path.exists():
        try:
            import re
            content = config_path.read_text()
            match = re.search(r"^\s*project:\s*(.+)$", content, re.MULTILINE)
            if match:
                return match.group(1).strip().strip('"').strip("'")
        except OSError:
            pass
    return target.name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap a new project with claude-plan-orchestrator."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Target project directory (default: current directory)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing config files",
    )
    parser.add_argument(
        "--no-slack",
        action="store_true",
        help="Skip Slack app setup (Phase 3)",
    )
    parser.add_argument(
        "--no-claude",
        action="store_true",
        help="Skip interactive Claude Code config (Phases 2-3); file scaffolding only",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target = Path(args.target).resolve()

    if not target.exists():
        print(f"Error: target directory does not exist: {target}")
        raise SystemExit(1)

    print(f"Setting up claude-plan-orchestrator in: {target}")

    # Phase 1: File scaffolding
    scaffold_files(target, force=args.force)

    if args.no_claude:
        print("\nSkipping Phases 2-3 (--no-claude). Run smoke test manually when ready.")
        run_smoke_test(target, slack_configured=False)
        return

    # Phase 2: Interactive Claude Code configuration
    configure_interactive(target)

    # Phase 3: Slack setup
    slack_configured = False
    if not args.no_slack:
        if check_chrome_mcp():
            project_name = _read_project_name(target)
            slack_configured = setup_slack_via_mcp(target, project_name)
        else:
            print("\n[Phase 3] Chrome MCP not found. Skipping automated Slack setup.")
            print(MANUAL_SLACK_INSTRUCTIONS)

    # Phase 4: Smoke test
    run_smoke_test(target, slack_configured=slack_configured)


if __name__ == "__main__":
    main()
