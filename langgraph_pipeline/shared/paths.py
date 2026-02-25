# langgraph_pipeline/shared/paths.py
# Centralized path constants shared by auto-pipeline.py and plan-orchestrator.py.
# Design: docs/plans/2026-02-25-02-extract-shared-modules-design.md

"""Centralized path constants for the pipeline and orchestrator scripts."""

from pathlib import Path

# ─── Orchestrator config ───────────────────────────────────────────────────────

ORCHESTRATOR_CONFIG_PATH = ".claude/orchestrator-config.yaml"

# ─── Plans directory ───────────────────────────────────────────────────────────

PLANS_DIR = ".claude/plans"
STATUS_FILE_PATH = ".claude/plans/task-status.json"
TASK_LOG_DIR = Path(".claude/plans/logs")
PID_FILE_PATH = ".claude/plans/.pipeline.pid"

# ─── Backlog directories ───────────────────────────────────────────────────────

DEFECT_DIR = "docs/defect-backlog"
FEATURE_DIR = "docs/feature-backlog"
ANALYSIS_DIR = "docs/analysis-backlog"

BACKLOG_DIRS = {
    "defect": DEFECT_DIR,
    "feature": FEATURE_DIR,
    "analysis": ANALYSIS_DIR,
}

# ─── Completed backlog directories ────────────────────────────────────────────

COMPLETED_DEFECTS_DIR = "docs/completed-backlog/defects"
COMPLETED_FEATURES_DIR = "docs/completed-backlog/features"
COMPLETED_ANALYSES_DIR = "docs/completed-backlog/analyses"

COMPLETED_DIRS = {
    "defect": COMPLETED_DEFECTS_DIR,
    "feature": COMPLETED_FEATURES_DIR,
    "analysis": COMPLETED_ANALYSES_DIR,
}
