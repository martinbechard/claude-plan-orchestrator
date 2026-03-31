# langgraph_pipeline/shared/paths.py
# Centralized path constants shared by auto-pipeline.py and plan-orchestrator.py.
# Design: docs/plans/2026-02-25-02-extract-shared-modules-design.md
# Validation pipeline test v4
# full pipeline test v2
# yaml rescue test
# tmp plans test
# live stats test
# final stats test
# val results test
# val json test

"""Centralized path constants for the pipeline and orchestrator scripts."""

from pathlib import Path

# ─── Orchestrator config ───────────────────────────────────────────────────────

ORCHESTRATOR_CONFIG_PATH = ".claude/orchestrator-config.yaml"

# ─── Runtime env vars ─────────────────────────────────────────────────────────

ENV_ORCHESTRATOR_WEB_URL = "ORCHESTRATOR_WEB_URL"

# ─── Plans directory ───────────────────────────────────────────────────────────

PLANS_DIR = "tmp/plans"
STATUS_FILE_PATH = "tmp/task-status.json"
TASK_LOG_DIR = Path("tmp/plans/logs")
PID_FILE_PATH = "tmp/plans/.pipeline.pid"
LANGGRAPH_PID_FILE_PATH = "tmp/plans/.lg-pipeline.pid"

# ─── Worker output directories ────────────────────────────────────────────────

WORKER_OUTPUT_DIR = Path("docs/reports/worker-output")

# ─── Backlog directories ───────────────────────────────────────────────────────

DEFECT_DIR = "docs/defect-backlog"
FEATURE_DIR = "docs/feature-backlog"
ANALYSIS_DIR = "docs/analysis-backlog"
INVESTIGATION_DIR = "docs/investigation-backlog"

BACKLOG_DIRS = {
    "defect": DEFECT_DIR,
    "feature": FEATURE_DIR,
    "analysis": ANALYSIS_DIR,
    "investigation": INVESTIGATION_DIR,
}

# ─── Ideas intake directories ─────────────────────────────────────────────────

IDEAS_DIR = "docs/ideas"
IDEAS_PROCESSED_DIR = "docs/ideas/processed"

# ─── Parallel item processing ─────────────────────────────────────────────────

CLAIMED_DIR = "tmp/plans/.claimed"
WORKER_RESULT_DIR = "tmp/plans"

# ─── Completed backlog directories ────────────────────────────────────────────

COMPLETED_DEFECTS_DIR = "docs/completed-backlog/defects"
COMPLETED_FEATURES_DIR = "docs/completed-backlog/features"
COMPLETED_ANALYSES_DIR = "docs/completed-backlog/analyses"
COMPLETED_INVESTIGATIONS_DIR = "docs/completed-backlog/investigations"

COMPLETED_DIRS = {
    "defect": COMPLETED_DEFECTS_DIR,
    "feature": COMPLETED_FEATURES_DIR,
    "analysis": COMPLETED_ANALYSES_DIR,
    "investigation": COMPLETED_INVESTIGATIONS_DIR,
}

# ─── Per-item workspace ─────────────────────────────────────────────────────

WORKSPACE_DIR = Path("tmp/workspace")


def workspace_path(slug: str) -> Path:
    """Return the workspace directory path for a given item slug."""
    return WORKSPACE_DIR / slug


def ensure_workspace(slug: str) -> Path:
    """Create the per-item workspace directory structure and return the root path.

    Layout:
        tmp/workspace/{slug}/
            logs/         -- task execution logs
            validation/   -- validation result JSON files
    """
    ws = workspace_path(slug)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "logs").mkdir(exist_ok=True)
    (ws / "validation").mkdir(exist_ok=True)
    return ws
