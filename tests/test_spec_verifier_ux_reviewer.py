# tests/test_spec_verifier_ux_reviewer.py
# Unit tests for spec-verifier and ux-reviewer agent integration: agent loading,
# keyword inference, and validator registration.
# Design ref: docs/plans/2026-02-16-12-spec-verifier-ux-reviewer-agents-design.md

import importlib.util

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


# --- Spec Verifier Agent Definition Tests ---


def test_spec_verifier_agent_loads():
    """spec-verifier agent should load with correct name, model, and tools."""
    agent = load_agent_definition("spec-verifier")
    assert agent is not None, "spec-verifier agent should exist"
    assert agent["name"] == "spec-verifier", f"Wrong name: {agent['name']}"
    assert agent["model"] == "sonnet", f"Wrong model: {agent['model']}"

    tools = agent["tools"]
    assert "Read" in tools, "Missing Read tool"
    assert "Grep" in tools, "Missing Grep tool"
    assert "Glob" in tools, "Missing Glob tool"
    assert "Bash" not in tools, "spec-verifier should not have Bash tool (read-only)"


def test_spec_verifier_agent_body_has_sections():
    """spec-verifier agent body should contain key sections from the design."""
    agent = load_agent_definition("spec-verifier")
    assert agent is not None, "spec-verifier agent should exist"

    body = agent["body"]
    assert "Verification Checklist" in body, "Missing 'Verification Checklist' section"
    assert "Output Format" in body, "Missing 'Output Format' section"
    assert "Verdict" in body, "Missing 'Verdict' section"
    assert "Constraints" in body, "Missing 'Constraints' section"


def test_spec_verifier_references_crud_checklist():
    """spec-verifier agent body should reference CRUD operations checklist."""
    agent = load_agent_definition("spec-verifier")
    assert agent is not None, "spec-verifier agent should exist"

    body = agent["body"]
    assert ".claude/checklists/crud-operations.md" in body, \
        "spec-verifier should reference crud-operations.md checklist"


# --- UX Reviewer Agent Definition Tests ---


def test_ux_reviewer_agent_loads():
    """ux-reviewer agent should load with correct name, model, and tools."""
    agent = load_agent_definition("ux-reviewer")
    assert agent is not None, "ux-reviewer agent should exist"
    assert agent["name"] == "ux-reviewer", f"Wrong name: {agent['name']}"
    assert agent["model"] == "sonnet", f"Wrong model: {agent['model']}"

    tools = agent["tools"]
    assert "Read" in tools, "Missing Read tool"
    assert "Grep" in tools, "Missing Grep tool"
    assert "Glob" in tools, "Missing Glob tool"
    assert "Bash" not in tools, "ux-reviewer should not have Bash tool (read-only)"


def test_ux_reviewer_agent_body_has_sections():
    """ux-reviewer agent body should contain key sections from the design."""
    agent = load_agent_definition("ux-reviewer")
    assert agent is not None, "ux-reviewer agent should exist"

    body = agent["body"]
    assert "Review Checklist" in body, "Missing 'Review Checklist' section"
    assert "Output Format" in body, "Missing 'Output Format' section"
    assert "Verdict" in body, "Missing 'Verdict' section"
    assert "Quality Score" in body, "Missing 'Quality Score' section"
    assert "Constraints" in body, "Missing 'Constraints' section"


def test_ux_reviewer_distinct_from_ux_designer():
    """ux-reviewer should be distinct from ux-designer (different models)."""
    ux_reviewer = load_agent_definition("ux-reviewer")
    ux_designer = load_agent_definition("ux-designer")

    assert ux_reviewer is not None, "ux-reviewer agent should exist"
    assert ux_designer is not None, "ux-designer agent should exist"

    assert ux_reviewer["name"] != ux_designer["name"], \
        "ux-reviewer and ux-designer should have different names"
    assert ux_reviewer["model"] == "sonnet", \
        f"ux-reviewer should use sonnet model, got {ux_reviewer['model']}"
    assert ux_designer["model"] == "opus", \
        f"ux-designer should use opus model, got {ux_designer['model']}"


# --- Agent Inference Tests ---


def test_infer_agent_for_spec_verification_task():
    """Task with 'spec verification' keyword should infer spec-verifier agent."""
    task = {
        "name": "Verify spec compliance",
        "description": "Run spec verification on the implemented feature"
    }
    result = infer_agent_for_task(task)
    assert result == "spec-verifier", f"Expected 'spec-verifier', got '{result}'"


def test_infer_agent_for_functional_spec_task():
    """Task with 'functional spec' keyword should infer spec-verifier agent."""
    task = {
        "name": "Check spec",
        "description": "Validate functional spec compliance for the UI changes"
    }
    result = infer_agent_for_task(task)
    assert result == "spec-verifier", f"Expected 'spec-verifier', got '{result}'"


def test_infer_agent_for_ux_review_task():
    """Task with 'ux review' keyword should infer ux-reviewer agent."""
    task = {
        "name": "Review UX",
        "description": "Perform ux review on the implemented component"
    }
    result = infer_agent_for_task(task)
    assert result == "ux-reviewer", f"Expected 'ux-reviewer', got '{result}'"


def test_infer_agent_for_accessibility_review_task():
    """Task with 'accessibility review' keyword should infer ux-reviewer agent."""
    task = {
        "name": "Check accessibility",
        "description": "Run accessibility review on the new UI"
    }
    result = infer_agent_for_task(task)
    assert result == "ux-reviewer", f"Expected 'ux-reviewer', got '{result}'"


def test_infer_agent_non_spec_ux_task():
    """Non-spec/ux task should NOT infer spec-verifier or ux-reviewer (should return 'coder')."""
    task = {
        "name": "Implement feature",
        "description": "Implement the feature according to requirements"
    }
    result = infer_agent_for_task(task)
    assert result != "spec-verifier", f"Non-spec task should not infer spec-verifier, got '{result}'"
    assert result != "ux-reviewer", f"Non-ux task should not infer ux-reviewer, got '{result}'"
    assert result == "coder", f"Expected 'coder', got '{result}'"


# --- ValidationConfig Tests ---


def test_validators_list_accepts_new_agents():
    """ValidationConfig should accept spec-verifier and ux-reviewer in validators list."""
    config = ValidationConfig(
        enabled=True,
        validators=["code-reviewer", "spec-verifier", "ux-reviewer"]
    )
    assert "spec-verifier" in config.validators, "spec-verifier should be in validators list"
    assert "ux-reviewer" in config.validators, "ux-reviewer should be in validators list"
    assert config.enabled is True, "ValidationConfig should be enabled"
