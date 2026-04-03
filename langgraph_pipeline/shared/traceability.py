# langgraph_pipeline/shared/traceability.py
# Utility functions for loading validation skills and saving cross-reference reports.
# Design: design/architecture/pipeline-step-metamodel.md

"""I/O helpers for the traceability validation framework.

Provides functions to load validation skill files and save cross-reference
reports produced at each pipeline step.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

VALIDATOR_SKILLS_DIR = Path(".claude/agents/validator-skills")


# ─── Skill loading ────────────────────────────────────────────────────────────


def load_validation_skill(skill_name: str) -> str:
    """Read a validation skill file and return its content.

    Args:
        skill_name: Filename of the skill (e.g. 'clause-extraction-validation.md').

    Returns:
        The full text content of the skill file.

    Raises:
        FileNotFoundError: If the skill file does not exist.
    """
    skill_path = VALIDATOR_SKILLS_DIR / skill_name
    if not skill_path.exists():
        raise FileNotFoundError(f"Validation skill not found: {skill_path}")
    return skill_path.read_text(encoding="utf-8")


# ─── Cross-reference report saving ───────────────────────────────────────────


def save_cross_reference_report(
    slug: str,
    step_number: int,
    step_name: str,
    report_content: str,
) -> Path:
    """Save a cross-reference report to the workspace validation directory.

    The report is saved as a timestamped markdown file:
        tmp/workspace/{slug}/validation/step-{N}-{step_name}-{timestamp}.md

    Args:
        slug: Item slug identifying the workspace.
        step_number: Pipeline step number (1-8).
        step_name: Short kebab-case name for the step (e.g. 'clause-extraction').
        report_content: The markdown report content to save.

    Returns:
        The Path where the report was saved.
    """
    from langgraph_pipeline.shared.paths import workspace_path

    val_dir = workspace_path(slug) / "validation"
    val_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"step-{step_number}-{step_name}-{timestamp}.md"
    report_path = val_dir / filename

    report_path.write_text(report_content, encoding="utf-8")
    logger.info("Saved cross-reference report: %s", report_path)
    return report_path
