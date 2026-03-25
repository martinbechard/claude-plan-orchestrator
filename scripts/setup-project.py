#!/usr/bin/env python3
# scripts/setup-project.py
# Bootstrap a new project with claude-plan-orchestrator.
# Design: docs/plans/2026-03-25-17-project-setup-script-design.md

import argparse
import shutil
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

    # Phases 2-4 are stubs, implemented in later plan tasks
    if not args.no_claude:
        print("\n[Phase 2] Interactive configuration: not yet implemented.")
        if not args.no_slack:
            print("[Phase 3] Slack setup: not yet implemented.")

    print("\n[Phase 4] Smoke test: not yet implemented.")
    print("\nSetup complete.")


if __name__ == "__main__":
    main()
