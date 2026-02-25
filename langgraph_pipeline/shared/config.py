# langgraph_pipeline/shared/config.py
# Shared orchestrator configuration loader and project-level defaults.
# Design: docs/plans/2026-02-25-02-extract-shared-modules-design.md

"""Orchestrator configuration loading and default constants."""

import yaml

from langgraph_pipeline.shared.paths import ORCHESTRATOR_CONFIG_PATH

# ─── Configuration defaults ───────────────────────────────────────────────────

DEFAULT_DEV_SERVER_PORT = 3000
DEFAULT_BUILD_COMMAND = "pnpm run build"
DEFAULT_TEST_COMMAND = "pnpm test"
DEFAULT_DEV_SERVER_COMMAND = "pnpm dev"
DEFAULT_AGENTS_DIR = ".claude/agents/"
DEFAULT_E2E_COMMAND = "npx playwright test"


def load_orchestrator_config() -> dict:
    """Load project-level orchestrator config from .claude/orchestrator-config.yaml.

    Returns the parsed dict, or an empty dict if the file doesn't exist or
    cannot be parsed.
    """
    try:
        with open(ORCHESTRATOR_CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)
        return config if isinstance(config, dict) else {}
    except (IOError, yaml.YAMLError):
        return {}
