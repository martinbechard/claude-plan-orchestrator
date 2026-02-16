# tests/test_qa_auditor_integration.py
# Unit tests for qa-auditor agent integration: agent loading, checklist parsing,
# keyword inference, and validator registration.
# Design ref: docs/plans/2026-02-16-11-qa-audit-pipeline-design.md

import importlib.util
import os

# plan-orchestrator.py has a hyphen in the filename, so we must use importlib
# to load it as a module under a valid Python identifier.
spec = importlib.util.spec_from_file_location(
    "plan_orchestrator", "scripts/plan-orchestrator.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

load_agent_definition = mod.load_agent_definition
infer_agent_for_task = mod.infer_agent_for_task
ValidationConfig = mod.ValidationConfig


# --- Agent Definition Tests ---


def test_qa_auditor_agent_loads():
    """qa-auditor agent should load with correct name, model, and tools."""
    agent = load_agent_definition("qa-auditor")
    assert agent is not None, "qa-auditor agent should exist"
    assert agent["name"] == "qa-auditor", f"Wrong name: {agent['name']}"
    assert agent["model"] == "sonnet", f"Wrong model: {agent['model']}"

    tools = agent["tools"]
    assert "Read" in tools, "Missing Read tool"
    assert "Grep" in tools, "Missing Grep tool"
    assert "Glob" in tools, "Missing Glob tool"
    assert "Bash" in tools, "Missing Bash tool"


def test_qa_auditor_agent_body_has_pipeline_sections():
    """qa-auditor agent body should contain key sections from the design."""
    agent = load_agent_definition("qa-auditor")
    assert agent is not None, "qa-auditor agent should exist"

    body = agent["body"]
    assert "Audit Pipeline" in body, "Missing 'Audit Pipeline' section"
    assert "Output Format" in body, "Missing 'Output Format' section"
    assert "Verdict" in body, "Missing 'Verdict' section"
    assert "Constraints" in body, "Missing 'Constraints' section"


# --- Checklist File Tests ---


def test_checklist_crud_operations_exists():
    """CRUD operations checklist should exist with expected content."""
    checklist_path = ".claude/checklists/crud-operations.md"
    assert os.path.isfile(checklist_path), f"Missing checklist: {checklist_path}"

    with open(checklist_path, "r") as f:
        content = f.read()

    assert "Create and edit" in content, "Missing 'Create and edit' rule"
    assert "Delete requires a confirmation" in content, "Missing 'Delete requires a confirmation' rule"


def test_checklist_navigation_exists():
    """Navigation checklist should exist with expected content."""
    checklist_path = ".claude/checklists/navigation.md"
    assert os.path.isfile(checklist_path), f"Missing checklist: {checklist_path}"

    with open(checklist_path, "r") as f:
        content = f.read()

    assert "Deep links" in content, "Missing 'Deep links' rule"
    assert "Breadcrumbs" in content, "Missing 'Breadcrumbs' rule"


def test_checklist_data_display_exists():
    """Data display checklist should exist with expected content."""
    checklist_path = ".claude/checklists/data-display.md"
    assert os.path.isfile(checklist_path), f"Missing checklist: {checklist_path}"

    with open(checklist_path, "r") as f:
        content = f.read()

    assert "Empty state" in content, "Missing 'Empty state' rule"
    assert "Loading state" in content, "Missing 'Loading state' rule"


# --- Agent Inference Tests ---


def test_infer_agent_for_qa_audit_task():
    """Task with 'qa audit' keyword should infer qa-auditor agent."""
    task = {
        "name": "Run QA audit",
        "description": "Run qa audit on the implemented feature"
    }
    result = infer_agent_for_task(task)
    assert result == "qa-auditor", f"Expected 'qa-auditor', got '{result}'"


def test_infer_agent_for_checklist_audit_task():
    """Task with 'coverage matrix' keyword should infer qa-auditor agent."""
    task = {
        "name": "QA validation",
        "description": "Generate coverage matrix for the feature"
    }
    result = infer_agent_for_task(task)
    assert result == "qa-auditor", f"Expected 'qa-auditor', got '{result}'"


def test_infer_agent_for_test_plan_task():
    """Task with 'test plan' keyword should infer qa-auditor agent."""
    task = {
        "name": "Generate test plan",
        "description": "Create a test plan from the functional spec"
    }
    result = infer_agent_for_task(task)
    assert result == "qa-auditor", f"Expected 'qa-auditor', got '{result}'"


def test_infer_agent_non_qa_task():
    """Non-QA task should NOT infer qa-auditor (should return 'coder')."""
    task = {
        "name": "Implement feature",
        "description": "Implement the feature according to spec"
    }
    result = infer_agent_for_task(task)
    assert result != "qa-auditor", f"Non-QA task should not infer qa-auditor, got '{result}'"
    assert result == "coder", f"Expected 'coder', got '{result}'"


# --- ValidationConfig Tests ---


def test_qa_auditor_in_validators_list():
    """qa-auditor should be valid in ValidationConfig.validators list."""
    config = ValidationConfig(
        enabled=True,
        validators=["validator", "qa-auditor"]
    )
    assert "qa-auditor" in config.validators, "qa-auditor should be in validators list"
    assert config.enabled is True, "ValidationConfig should be enabled"
