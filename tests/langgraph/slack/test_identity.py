# tests/langgraph/slack/test_identity.py
# Unit tests for langgraph_pipeline.slack.identity module.
# Design: docs/plans/2026-02-26-03-extract-slack-modules-design.md

"""Unit tests for AgentIdentity, load_agent_identity, and IdentityMixin."""

from pathlib import Path
from unittest.mock import patch

import pytest

from langgraph_pipeline.slack.identity import (
    AGENT_ADDRESS_PATTERN,
    AGENT_ROLE_INTAKE,
    AGENT_ROLE_ORCHESTRATOR,
    AGENT_ROLE_PIPELINE,
    AGENT_ROLE_QA,
    AGENT_ROLES,
    AgentIdentity,
    IdentityMixin,
    load_agent_identity,
)


# ── load_agent_identity tests ────────────────────────────────────────────────


class TestLoadAgentIdentity:
    """Tests for load_agent_identity()."""

    def test_explicit_config(self):
        """Full identity config is loaded correctly."""
        config = {
            "identity": {
                "project": "my-project",
                "agents": {
                    "pipeline": "MP-Pipeline",
                    "orchestrator": "MP-Orchestrator",
                    "intake": "MP-Intake",
                    "qa": "MP-QA",
                },
            }
        }
        identity = load_agent_identity(config)

        assert identity.project == "my-project"
        assert identity.agents["pipeline"] == "MP-Pipeline"
        assert identity.agents["orchestrator"] == "MP-Orchestrator"
        assert identity.agents["intake"] == "MP-Intake"
        assert identity.agents["qa"] == "MP-QA"

    def test_defaults_from_cwd(self):
        """When no identity config, project defaults to cwd basename."""
        with patch.object(Path, "cwd", return_value=Path("/home/user/cheapoville")):
            identity = load_agent_identity({})

        assert identity.project == "cheapoville"
        assert identity.agents == {}

    def test_partial_config_project_only(self):
        """When only project is specified, agents remain empty."""
        config = {"identity": {"project": "cool-app"}}
        identity = load_agent_identity(config)

        assert identity.project == "cool-app"
        assert identity.agents == {}

    def test_missing_identity_section(self):
        """Empty config returns defaults derived from cwd."""
        with patch.object(Path, "cwd", return_value=Path("/tmp/test-proj")):
            identity = load_agent_identity({})

        assert identity.project == "test-proj"

    def test_invalid_identity_value(self):
        """Non-dict identity value is treated as missing."""
        config = {"identity": "invalid"}
        with patch.object(Path, "cwd", return_value=Path("/tmp/fallback")):
            identity = load_agent_identity(config)

        assert identity.project == "fallback"

    def test_invalid_agents_value(self):
        """Non-dict agents value is treated as empty."""
        config = {"identity": {"project": "test", "agents": "invalid"}}
        identity = load_agent_identity(config)

        assert identity.project == "test"
        assert identity.agents == {}


# ── AgentIdentity tests ──────────────────────────────────────────────────────


class TestAgentIdentity:
    """Tests for AgentIdentity dataclass methods."""

    def _make_identity(self):
        return AgentIdentity(
            project="my-proj",
            agents={
                "pipeline": "MP-Pipeline",
                "orchestrator": "MP-Orchestrator",
            },
        )

    def test_name_for_role_explicit(self):
        """Returns the configured name for an explicitly mapped role."""
        identity = self._make_identity()
        assert identity.name_for_role("pipeline") == "MP-Pipeline"
        assert identity.name_for_role("orchestrator") == "MP-Orchestrator"

    def test_name_for_role_default(self):
        """Returns derived name for an unmapped role."""
        identity = self._make_identity()
        name = identity.name_for_role("intake")
        assert name == "My-Proj-Intake"

    def test_name_for_role_default_with_hyphens(self):
        """Derived names correctly handle hyphenated project names."""
        identity = AgentIdentity(project="claude-plan-orchestrator", agents={})
        name = identity.name_for_role("pipeline")
        assert name == "Claude-Plan-Orchestrator-Pipeline"

    def test_all_names_includes_explicit(self):
        """all_names() includes explicitly configured names."""
        identity = self._make_identity()
        names = identity.all_names()
        assert "MP-Pipeline" in names
        assert "MP-Orchestrator" in names

    def test_all_names_includes_derived_defaults(self):
        """all_names() includes derived defaults for unmapped roles."""
        identity = self._make_identity()
        names = identity.all_names()
        assert "My-Proj-Intake" in names
        assert "My-Proj-Qa" in names

    def test_is_own_signed_text_matches_signature(self):
        """is_own_signed_text() returns True when text contains agent signature."""
        identity = AgentIdentity(
            project="test",
            agents={"orchestrator": "Test-Orchestrator"},
        )
        text = "Task complete \u2014 *Test-Orchestrator*"
        assert identity.is_own_signed_text(text) is True

    def test_is_own_signed_text_no_match(self):
        """is_own_signed_text() returns False for unrelated text."""
        identity = AgentIdentity(
            project="test",
            agents={"orchestrator": "Test-Orchestrator"},
        )
        text = "The login button is broken"
        assert identity.is_own_signed_text(text) is False

    def test_is_own_signed_text_matches_derived_name(self):
        """is_own_signed_text() matches signatures using derived role names."""
        identity = AgentIdentity(project="my-proj", agents={})
        # Derived pipeline name: My-Proj-Pipeline
        text = "Build finished \u2014 *My-Proj-Pipeline*"
        assert identity.is_own_signed_text(text) is True

    def test_is_own_signed_text_ignores_partial_name_in_text(self):
        """is_own_signed_text() does not match name appearing outside signature."""
        identity = AgentIdentity(
            project="test",
            agents={"orchestrator": "Test-Orchestrator"},
        )
        # Name appears but not in signature format
        text = "Test-Orchestrator says hello"
        assert identity.is_own_signed_text(text) is False


# ── AGENT_ROLES constants tests ──────────────────────────────────────────────


class TestAgentRoleConstants:
    """Tests for the AGENT_ROLE_* constants and AGENT_ROLES list."""

    def test_all_role_constants_are_strings(self):
        """Each role constant is a non-empty string."""
        for role in (AGENT_ROLE_PIPELINE, AGENT_ROLE_ORCHESTRATOR, AGENT_ROLE_INTAKE, AGENT_ROLE_QA):
            assert isinstance(role, str)
            assert len(role) > 0

    def test_agent_roles_list_contains_all_constants(self):
        """AGENT_ROLES contains all four role constants."""
        assert AGENT_ROLE_PIPELINE in AGENT_ROLES
        assert AGENT_ROLE_ORCHESTRATOR in AGENT_ROLES
        assert AGENT_ROLE_INTAKE in AGENT_ROLES
        assert AGENT_ROLE_QA in AGENT_ROLES

    def test_agent_roles_has_four_entries(self):
        """AGENT_ROLES has exactly four entries."""
        assert len(AGENT_ROLES) == 4


# ── AGENT_ADDRESS_PATTERN tests ──────────────────────────────────────────────


class TestAgentAddressPattern:
    """Tests for the AGENT_ADDRESS_PATTERN regex."""

    def test_matches_single_agent_mention(self):
        """Matches a single @AgentName mention."""
        text = "Hey @CPO-Pipeline can you check this?"
        matches = AGENT_ADDRESS_PATTERN.findall(text)
        assert matches == ["CPO-Pipeline"]

    def test_matches_multiple_mentions(self):
        """Matches multiple @AgentName mentions in one string."""
        text = "@Agent-A and @Agent-B please coordinate"
        matches = AGENT_ADDRESS_PATTERN.findall(text)
        assert set(matches) == {"Agent-A", "Agent-B"}

    def test_ignores_slack_native_mentions(self):
        """Does not match Slack native <@U12345> mentions."""
        text = "<@U12345> hello @CPO-Orchestrator"
        matches = AGENT_ADDRESS_PATTERN.findall(text)
        assert "U12345" not in matches
        assert "CPO-Orchestrator" in matches

    def test_no_matches_for_plain_text(self):
        """Returns empty list when no @mentions are present."""
        text = "No mentions here at all"
        matches = AGENT_ADDRESS_PATTERN.findall(text)
        assert matches == []


# ── IdentityMixin tests ──────────────────────────────────────────────────────


class TestIdentityMixin:
    """Tests for IdentityMixin: set_identity, _as_role, _sign_text."""

    def _make_mixin(self):
        """Instantiate a bare IdentityMixin for testing."""

        class _Subject(IdentityMixin):
            def __init__(self):
                super().__init__()

        return _Subject()

    def test_sign_text_without_identity_returns_unchanged(self):
        """_sign_text returns text unchanged when no identity is configured."""
        mixin = self._make_mixin()
        assert mixin._sign_text("Hello world") == "Hello world"

    def test_sign_text_with_identity_appends_signature(self):
        """_sign_text appends agent signature when identity is set."""
        mixin = self._make_mixin()
        identity = AgentIdentity(
            project="test",
            agents={"orchestrator": "Test-Orchestrator"},
        )
        mixin.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)
        result = mixin._sign_text("Hello world")
        assert result == "Hello world \u2014 *Test-Orchestrator*"

    def test_sign_text_uses_active_role(self):
        """_sign_text signs with the currently active role's name."""
        mixin = self._make_mixin()
        identity = AgentIdentity(
            project="test",
            agents={"orchestrator": "Test-Orch", "qa": "Test-QA"},
        )
        mixin.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)
        assert "Test-Orch" in mixin._sign_text("msg")

        mixin.set_identity(identity, AGENT_ROLE_QA)
        assert "Test-QA" in mixin._sign_text("msg")

    def test_as_role_switches_and_restores(self):
        """_as_role switches role within the block and restores on exit."""
        mixin = self._make_mixin()
        identity = AgentIdentity(
            project="test",
            agents={"orchestrator": "Test-Orch", "qa": "Test-QA"},
        )
        mixin.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)

        assert mixin._active_role == AGENT_ROLE_ORCHESTRATOR

        with mixin._as_role(AGENT_ROLE_QA):
            assert mixin._active_role == AGENT_ROLE_QA

        assert mixin._active_role == AGENT_ROLE_ORCHESTRATOR

    def test_as_role_restores_on_exception(self):
        """_as_role restores the previous role even when an exception occurs."""
        mixin = self._make_mixin()
        identity = AgentIdentity(
            project="test",
            agents={"orchestrator": "Test-Orch", "intake": "Test-Intake"},
        )
        mixin.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)

        try:
            with mixin._as_role(AGENT_ROLE_INTAKE):
                assert mixin._active_role == AGENT_ROLE_INTAKE
                raise ValueError("test error")
        except ValueError:
            pass

        assert mixin._active_role == AGENT_ROLE_ORCHESTRATOR

    def test_signing_reflects_active_role_within_as_role(self):
        """_sign_text uses the role active inside _as_role."""
        mixin = self._make_mixin()
        identity = AgentIdentity(
            project="test",
            agents={"orchestrator": "Test-Orch", "qa": "Test-QA"},
        )
        mixin.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)

        assert "Test-Orch" in mixin._sign_text("hello")

        with mixin._as_role(AGENT_ROLE_QA):
            assert "Test-QA" in mixin._sign_text("hello")

        assert "Test-Orch" in mixin._sign_text("hello")

    def test_set_identity_stores_role(self):
        """set_identity stores both identity and role."""
        mixin = self._make_mixin()
        identity = AgentIdentity(project="proj", agents={})
        mixin.set_identity(identity, AGENT_ROLE_PIPELINE)

        assert mixin._agent_identity is identity
        assert mixin._active_role == AGENT_ROLE_PIPELINE
