# tests/test_setup_project.py
# Unit tests for Phase 1 (file scaffolding) in scripts/setup-project.py
# Design ref: docs/plans/2026-03-25-17-project-setup-script-design.md

import importlib.util
import sys
from pathlib import Path

import pytest

# setup-project.py has a hyphen so we must load it via importlib
spec = importlib.util.spec_from_file_location(
    "setup_project", Path(__file__).parent.parent / "scripts" / "setup-project.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

scaffold_files = mod.scaffold_files
BACKLOG_DIRS = mod.BACKLOG_DIRS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source_tree(src_root: Path) -> None:
    """Build a minimal fake source tree mirroring the real layout."""
    # Config template
    template = src_root / "scripts" / "setup-templates" / "orchestrator-config.yaml"
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_text("# orchestrator config template\n")

    # Two agent .md files
    agents_dir = src_root / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "coder.md").write_text("# coder agent\n")
    (agents_dir / "qa-auditor.md").write_text("# qa-auditor agent\n")

    # Coding rules
    coding_rules = src_root / "procedure-coding-rules.md"
    coding_rules.write_text("# coding rules\n")


def _run_scaffold(src_root: Path, target: Path, *, force: bool = False) -> None:
    """Patch module-level source paths and run scaffold_files."""
    orig_template = mod.TEMPLATE_CONFIG
    orig_agents = mod.AGENTS_SRC
    orig_coding = mod.CODING_RULES_SRC

    mod.TEMPLATE_CONFIG = src_root / "scripts" / "setup-templates" / "orchestrator-config.yaml"
    mod.AGENTS_SRC = src_root / ".claude" / "agents"
    mod.CODING_RULES_SRC = src_root / "procedure-coding-rules.md"

    try:
        scaffold_files(target, force=force)
    finally:
        mod.TEMPLATE_CONFIG = orig_template
        mod.AGENTS_SRC = orig_agents
        mod.CODING_RULES_SRC = orig_coding


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestScaffoldCopiesConfigTemplate:
    def test_scaffold_copies_config_template(self, tmp_path):
        src = tmp_path / "src"
        target = tmp_path / "target"
        target.mkdir()
        _make_source_tree(src)

        _run_scaffold(src, target)

        dest = target / ".claude" / "orchestrator-config.yaml"
        assert dest.exists(), "orchestrator-config.yaml should be copied to .claude/"
        assert dest.read_text() == "# orchestrator config template\n"


class TestScaffoldCopiesAgents:
    def test_scaffold_copies_agents(self, tmp_path):
        src = tmp_path / "src"
        target = tmp_path / "target"
        target.mkdir()
        _make_source_tree(src)

        _run_scaffold(src, target)

        agents_dest = target / ".claude" / "agents"
        assert (agents_dest / "coder.md").exists()
        assert (agents_dest / "qa-auditor.md").exists()


class TestScaffoldCreatesBacklogDirs:
    def test_scaffold_creates_backlog_dirs(self, tmp_path):
        src = tmp_path / "src"
        target = tmp_path / "target"
        target.mkdir()
        _make_source_tree(src)

        _run_scaffold(src, target)

        for rel_dir in BACKLOG_DIRS:
            backlog_dir = target / rel_dir
            assert backlog_dir.is_dir(), f"{rel_dir} should be created"
            assert (backlog_dir / ".gitkeep").exists(), f".gitkeep missing in {rel_dir}"


class TestScaffoldCopiesCodingRules:
    def test_scaffold_copies_coding_rules(self, tmp_path):
        src = tmp_path / "src"
        target = tmp_path / "target"
        target.mkdir()
        _make_source_tree(src)

        _run_scaffold(src, target)

        dest = target / "procedure-coding-rules.md"
        assert dest.exists(), "procedure-coding-rules.md should be copied to target root"
        assert dest.read_text() == "# coding rules\n"


class TestScaffoldSkipsExistingWithoutForce:
    def test_scaffold_skips_existing_without_force(self, tmp_path):
        src = tmp_path / "src"
        target = tmp_path / "target"
        target.mkdir()
        _make_source_tree(src)

        # Pre-create the config with different content
        claude_dir = target / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        existing = claude_dir / "orchestrator-config.yaml"
        existing.write_text("# existing content\n")

        _run_scaffold(src, target, force=False)

        assert existing.read_text() == "# existing content\n", \
            "Existing file should not be overwritten without --force"


class TestScaffoldOverwritesWithForce:
    def test_scaffold_overwrites_with_force(self, tmp_path):
        src = tmp_path / "src"
        target = tmp_path / "target"
        target.mkdir()
        _make_source_tree(src)

        # Pre-create the config with different content
        claude_dir = target / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        existing = claude_dir / "orchestrator-config.yaml"
        existing.write_text("# existing content\n")

        _run_scaffold(src, target, force=True)

        assert existing.read_text() == "# orchestrator config template\n", \
            "--force should overwrite existing file with template content"


class TestScaffoldPrintsSummary:
    def test_scaffold_prints_summary(self, tmp_path, capsys):
        src = tmp_path / "src"
        target = tmp_path / "target"
        target.mkdir()
        _make_source_tree(src)

        _run_scaffold(src, target)
        out = capsys.readouterr().out

        assert "Scaffolding complete:" in out
        assert "copied" in out


class TestScaffoldGitkeepNotRecreatedInExistingDir:
    def test_scaffold_gitkeep_not_recreated_in_existing_dir(self, tmp_path):
        src = tmp_path / "src"
        target = tmp_path / "target"
        target.mkdir()
        _make_source_tree(src)

        # Pre-create one backlog dir without .gitkeep
        first_backlog = target / BACKLOG_DIRS[0]
        first_backlog.mkdir(parents=True, exist_ok=True)

        _run_scaffold(src, target, force=False)

        gitkeep = first_backlog / ".gitkeep"
        assert not gitkeep.exists(), \
            ".gitkeep should NOT be created in an already-existing backlog dir"
