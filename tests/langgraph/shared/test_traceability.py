# tests/langgraph/shared/test_traceability.py
# Unit tests for the traceability utility module.

"""Tests for langgraph_pipeline.shared.traceability."""

from pathlib import Path
from unittest.mock import patch

import pytest

from langgraph_pipeline.shared.traceability import (
    VALIDATOR_SKILLS_DIR,
    load_validation_skill,
    save_cross_reference_report,
)


class TestLoadValidationSkill:
    def test_loads_existing_skill(self):
        """Should read the skill file content."""
        content = load_validation_skill("clause-extraction-validation.md")
        assert "Validator Skill: Clause Extraction Validation" in content
        assert "QG-1.1" in content

    def test_raises_on_missing_skill(self):
        """Should raise FileNotFoundError for nonexistent skill."""
        with pytest.raises(FileNotFoundError, match="not found"):
            load_validation_skill("nonexistent-skill.md")

    def test_all_new_skills_loadable(self):
        """Every new skill file from the metamodel should be loadable."""
        expected_skills = [
            "clause-extraction-validation.md",
            "five-whys-validation.md",
            "requirements-structuring-validation.md",
            "ac-generation-validation.md",
            "design-validation.md",
            "plan-validation.md",
            "final-validation.md",
        ]
        for skill_name in expected_skills:
            content = load_validation_skill(skill_name)
            assert len(content) > 100, f"Skill {skill_name} is too short"


class TestSaveCrossReferenceReport:
    def test_saves_report_to_workspace(self, tmp_path):
        """Should save report to the workspace validation directory."""
        with patch(
            "langgraph_pipeline.shared.paths.workspace_path",
            return_value=tmp_path / "my-item",
        ):
            result = save_cross_reference_report(
                slug="my-item",
                step_number=1,
                step_name="clause-extraction",
                report_content="## Step 1 Report\n\nSome content",
            )
        assert result.exists()
        assert result.name.startswith("step-1-clause-extraction-")
        assert result.name.endswith(".md")
        assert result.read_text() == "## Step 1 Report\n\nSome content"

    def test_creates_validation_directory(self, tmp_path):
        """Should create the validation directory if it does not exist."""
        ws = tmp_path / "slug-1"
        with patch(
            "langgraph_pipeline.shared.paths.workspace_path",
            return_value=ws,
        ):
            result = save_cross_reference_report(
                slug="slug-1",
                step_number=3,
                step_name="requirements",
                report_content="content",
            )
        assert (ws / "validation").is_dir()
        assert result.parent == ws / "validation"

    def test_report_filename_contains_timestamp(self, tmp_path):
        """Filename should contain a UTC timestamp."""
        with patch(
            "langgraph_pipeline.shared.paths.workspace_path",
            return_value=tmp_path / "item",
        ):
            result = save_cross_reference_report(
                slug="item",
                step_number=5,
                step_name="design",
                report_content="x",
            )
        # Filename format: step-5-design-YYYYMMDDTHHMMSSz.md
        parts = result.stem.split("-")
        assert parts[0] == "step"
        assert parts[1] == "5"
        assert parts[2] == "design"
        # Timestamp part should start with 20
        assert parts[3].startswith("20")
