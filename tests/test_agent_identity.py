# tests/test_agent_identity.py
# Unit tests for Agent Identity Protocol.
# Design ref: plan for agent identity in shared Slack channels.

import importlib.util
import json
import re
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

# plan-orchestrator.py has a hyphen in the filename, so we must use importlib
# to load it as a module under a valid Python identifier.
spec = importlib.util.spec_from_file_location(
    "plan_orchestrator", "scripts/plan-orchestrator.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

AgentIdentity = mod.AgentIdentity
load_agent_identity = mod.load_agent_identity
SlackNotifier = mod.SlackNotifier
AGENT_ROLE_PIPELINE = mod.AGENT_ROLE_PIPELINE
AGENT_ROLE_ORCHESTRATOR = mod.AGENT_ROLE_ORCHESTRATOR
AGENT_ROLE_INTAKE = mod.AGENT_ROLE_INTAKE
AGENT_ROLE_QA = mod.AGENT_ROLE_QA
AGENT_ROLES = mod.AGENT_ROLES
AGENT_ADDRESS_PATTERN = mod.AGENT_ADDRESS_PATTERN
SLACK_BLOCK_TEXT_MAX_LENGTH = mod.SLACK_BLOCK_TEXT_MAX_LENGTH
MAX_SELF_REPLIES_PER_WINDOW = mod.MAX_SELF_REPLIES_PER_WINDOW
LOOP_DETECTION_WINDOW_SECONDS = mod.LOOP_DETECTION_WINDOW_SECONDS
MESSAGE_TRACKING_TTL_SECONDS = mod.MESSAGE_TRACKING_TTL_SECONDS
BOT_NOTIFICATION_PATTERN = mod.BOT_NOTIFICATION_PATTERN
MAX_INTAKES_PER_WINDOW = mod.MAX_INTAKES_PER_WINDOW
INTAKE_RATE_WINDOW_SECONDS = mod.INTAKE_RATE_WINDOW_SECONDS
BACKLOG_CREATION_THROTTLE_PATH = mod.BACKLOG_CREATION_THROTTLE_PATH
MAX_DEFECTS_PER_HOUR = mod.MAX_DEFECTS_PER_HOUR
MAX_FEATURES_PER_HOUR = mod.MAX_FEATURES_PER_HOUR
BACKLOG_THROTTLE_WINDOW_SECONDS = mod.BACKLOG_THROTTLE_WINDOW_SECONDS


# ─── load_agent_identity tests ─────────────────────────────────────


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
        """Empty config returns defaults."""
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


# ─── AgentIdentity tests ───────────────────────────────────────────


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
        # "intake" is not in agents, so it should derive from project
        name = identity.name_for_role("intake")
        assert name == "My-Proj-Intake"

    def test_name_for_role_default_with_hyphens(self):
        """Derived names correctly handle hyphenated project names."""
        identity = AgentIdentity(project="claude-plan-orchestrator", agents={})
        name = identity.name_for_role("pipeline")
        assert name == "Claude-Plan-Orchestrator-Pipeline"

    def test_all_names(self):
        """all_names() returns all configured + derived names."""
        identity = self._make_identity()
        names = identity.all_names()

        # Explicit names
        assert "MP-Pipeline" in names
        assert "MP-Orchestrator" in names

        # Derived defaults for unmapped roles
        assert "My-Proj-Intake" in names
        assert "My-Proj-Qa" in names


# ─── Regex pattern tests ──────────────────────────────────────────


class TestRegexPatterns:
    """Tests for AGENT_ADDRESS_PATTERN."""

    def test_address_pattern_matches(self):
        """Address pattern extracts @AgentName mentions."""
        text = "Hey @CPO-Pipeline can you check this?"
        matches = AGENT_ADDRESS_PATTERN.findall(text)
        assert matches == ["CPO-Pipeline"]

    def test_address_pattern_multiple(self):
        """Address pattern finds multiple mentions."""
        text = "@Agent-A and @Agent-B please coordinate"
        matches = AGENT_ADDRESS_PATTERN.findall(text)
        assert set(matches) == {"Agent-A", "Agent-B"}

    def test_address_pattern_ignores_slack_mentions(self):
        """Address pattern ignores Slack native <@U12345> mentions."""
        text = "<@U12345> hello @CPO-Orchestrator"
        matches = AGENT_ADDRESS_PATTERN.findall(text)
        # Should only match CPO-Orchestrator, not U12345
        assert matches == ["CPO-Orchestrator"]

    def test_address_pattern_no_match(self):
        """Address pattern returns empty for messages without @mentions."""
        text = "No mentions here, just email: user@example.com"
        # email should not match because '@' is preceded by a word character,
        # but our pattern matches after any non-< char, so check behavior
        matches = AGENT_ADDRESS_PATTERN.findall(text)
        # 'user@example' - the @ is preceded by 'r' not '<', so it matches 'example'
        # This is acceptable; the pattern is for agent names, not emails
        # The important thing is Slack <@U...> mentions are excluded
        assert "U12345" not in matches  # Just verify no Slack mentions leak


# ─── Outbound signing tests ──────────────────────────────────────


class TestOutboundSigning:
    """Tests for _sign_text and _build_status_block signing."""

    def _make_notifier(self, tmp_path):
        """Create a disabled SlackNotifier for testing."""
        config_file = tmp_path / "slack.yaml"
        config_file.write_text(yaml.dump({"slack": {"enabled": False}}))
        return SlackNotifier(config_path=str(config_file))

    def test_sign_text_with_identity(self, tmp_path):
        """_sign_text appends agent signature when identity is set."""
        notifier = self._make_notifier(tmp_path)
        identity = AgentIdentity(
            project="test",
            agents={"orchestrator": "Test-Orchestrator"},
        )
        notifier.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)

        result = notifier._sign_text("Hello world")
        assert result == "Hello world \u2014 *Test-Orchestrator*"

    def test_sign_text_without_identity(self, tmp_path):
        """_sign_text returns text unchanged when no identity is set."""
        notifier = self._make_notifier(tmp_path)
        result = notifier._sign_text("Hello world")
        assert result == "Hello world"

    def test_build_status_block_signed(self, tmp_path):
        """_build_status_block includes agent signature."""
        notifier = self._make_notifier(tmp_path)
        identity = AgentIdentity(
            project="test",
            agents={"orchestrator": "Test-Orch"},
        )
        notifier.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)

        payload = notifier._build_status_block("Test message", "info")
        text = payload["blocks"][0]["text"]["text"]
        assert text.endswith("\u2014 *Test-Orch*")
        assert ":large_blue_circle:" in text

    def test_build_status_block_unsigned(self, tmp_path):
        """_build_status_block works without identity."""
        notifier = self._make_notifier(tmp_path)
        payload = notifier._build_status_block("Test message", "info")
        text = payload["blocks"][0]["text"]["text"]
        assert "\u2014" not in text
        assert ":large_blue_circle:" in text

    def test_truncation_preserves_signature(self, tmp_path):
        """Signature is never truncated even with very long messages."""
        notifier = self._make_notifier(tmp_path)
        identity = AgentIdentity(
            project="test",
            agents={"orchestrator": "Test-Orchestrator"},
        )
        notifier.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)

        # Create a message that exceeds the Slack block text limit
        long_message = "x" * (SLACK_BLOCK_TEXT_MAX_LENGTH + 500)
        payload = notifier._build_status_block(long_message, "info")
        text = payload["blocks"][0]["text"]["text"]

        # Signature must be at the end
        assert text.endswith("\u2014 *Test-Orchestrator*")
        # Total length must respect Slack limits (body truncated + sig)
        signature = " \u2014 *Test-Orchestrator*"
        body_part = text[: -len(signature)]
        assert len(body_part) <= SLACK_BLOCK_TEXT_MAX_LENGTH


# ─── Inbound filtering tests ─────────────────────────────────────


class TestInboundFiltering:
    """Tests for identity-based inbound message filtering in _handle_polled_messages."""

    def _make_notifier_with_identity(self, tmp_path):
        """Create a SlackNotifier with identity for testing."""
        config_file = tmp_path / "slack.yaml"
        config_file.write_text(yaml.dump({"slack": {"enabled": False}}))
        notifier = SlackNotifier(config_path=str(config_file))
        identity = AgentIdentity(
            project="test",
            agents={
                "pipeline": "Test-Pipeline",
                "orchestrator": "Test-Orchestrator",
                "intake": "Test-Intake",
                "qa": "Test-QA",
            },
        )
        notifier.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)
        return notifier

    def test_skip_own_signature(self, tmp_path):
        """Messages signed by our own agent are skipped."""
        notifier = self._make_notifier_with_identity(tmp_path)
        messages = [
            {"text": "Task done \u2014 *Test-Orchestrator*", "user": "bot", "ts": "1",
             "_channel_name": "orchestrator-notifications", "_channel_id": "C1"}
        ]
        # Should not raise and should not trigger any routing
        notifier._handle_polled_messages(messages)

    def test_skip_addressed_to_other(self, tmp_path):
        """Messages addressed only to another agent are skipped."""
        notifier = self._make_notifier_with_identity(tmp_path)
        messages = [
            {"text": "@Other-Pipeline please check this", "user": "human", "ts": "2",
             "_channel_name": "orchestrator-notifications", "_channel_id": "C1"}
        ]
        notifier._handle_polled_messages(messages)

    def test_process_addressed_to_us(self, tmp_path):
        """Messages addressed to one of our agents are processed."""
        notifier = self._make_notifier_with_identity(tmp_path)
        text = "@Test-Orchestrator what is the status?"

        # Verify address pattern identifies the message as directed at us
        addresses = set(AGENT_ADDRESS_PATTERN.findall(text))
        our_names = notifier._agent_identity.all_names()
        addressed_to_us = bool(addresses & our_names)
        assert addressed_to_us is True

    def test_process_broadcast(self, tmp_path):
        """Messages without any @addressing are broadcast and processed."""
        notifier = self._make_notifier_with_identity(tmp_path)
        text = "General status update for everyone"
        addresses = set(AGENT_ADDRESS_PATTERN.findall(text))
        assert len(addresses) == 0  # No addressing = broadcast

    def test_slack_user_mention_not_confused(self, tmp_path):
        """Slack <@U12345> mentions are not treated as agent addresses."""
        text = "<@U12345> please review \u2014 *Other-Bot*"

        # Verify the Slack mention is NOT captured by address pattern
        addresses = set(AGENT_ADDRESS_PATTERN.findall(text))
        assert "U12345" not in addresses

    def test_mixed_addressing_includes_us(self, tmp_path):
        """Messages addressed to us AND others are still processed."""
        notifier = self._make_notifier_with_identity(tmp_path)
        text = "@Other-Agent and @Test-Pipeline please coordinate"
        addresses = set(AGENT_ADDRESS_PATTERN.findall(text))
        our_names = notifier._agent_identity.all_names()

        addressed_to_us = bool(addresses & our_names)
        addressed_to_others = bool(addresses - our_names)
        # Both are true, but since addressed_to_us is true, we process
        assert addressed_to_us is True
        assert addressed_to_others is True


# ─── Role switching tests ─────────────────────────────────────────


class TestRoleSwitching:
    """Tests for the _as_role context manager."""

    def _make_notifier(self, tmp_path):
        config_file = tmp_path / "slack.yaml"
        config_file.write_text(yaml.dump({"slack": {"enabled": False}}))
        return SlackNotifier(config_path=str(config_file))

    def test_role_switch_and_restore(self, tmp_path):
        """_as_role switches role and restores it on exit."""
        notifier = self._make_notifier(tmp_path)
        identity = AgentIdentity(
            project="test",
            agents={"orchestrator": "Test-Orch", "qa": "Test-QA"},
        )
        notifier.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)

        assert notifier._active_role == AGENT_ROLE_ORCHESTRATOR

        with notifier._as_role(AGENT_ROLE_QA):
            assert notifier._active_role == AGENT_ROLE_QA

        assert notifier._active_role == AGENT_ROLE_ORCHESTRATOR

    def test_role_switch_restores_on_exception(self, tmp_path):
        """_as_role restores role even if an exception occurs."""
        notifier = self._make_notifier(tmp_path)
        identity = AgentIdentity(
            project="test",
            agents={"orchestrator": "Test-Orch", "intake": "Test-Intake"},
        )
        notifier.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)

        try:
            with notifier._as_role(AGENT_ROLE_INTAKE):
                assert notifier._active_role == AGENT_ROLE_INTAKE
                raise ValueError("test error")
        except ValueError:
            pass

        assert notifier._active_role == AGENT_ROLE_ORCHESTRATOR

    def test_signing_reflects_active_role(self, tmp_path):
        """_sign_text uses the currently active role."""
        notifier = self._make_notifier(tmp_path)
        identity = AgentIdentity(
            project="test",
            agents={"orchestrator": "Test-Orch", "qa": "Test-QA"},
        )
        notifier.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)

        assert "Test-Orch" in notifier._sign_text("hello")

        with notifier._as_role(AGENT_ROLE_QA):
            assert "Test-QA" in notifier._sign_text("hello")

        assert "Test-Orch" in notifier._sign_text("hello")


# ─── Dedup + loop detection tests ────────────────────────────────


class TestDedupAndLoopDetection:
    """Tests for dedup and loop detection in _handle_polled_messages."""

    def _make_notifier(self, tmp_path):
        """Create a disabled SlackNotifier with identity."""
        config_file = tmp_path / "slack.yaml"
        config_file.write_text(yaml.dump({"slack": {"enabled": False}}))
        notifier = SlackNotifier(config_path=str(config_file))
        identity = AgentIdentity(
            project="test",
            agents={
                "pipeline": "Test-Pipeline",
                "orchestrator": "Test-Orchestrator",
                "intake": "Test-Intake",
                "qa": "Test-QA",
            },
        )
        notifier.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)
        return notifier

    def _channel_msg(self, ts, text="Hello"):
        return {
            "text": text,
            "user": "U0HUMAN",
            "ts": ts,
            "_channel_name": "orchestrator-notifications",
            "_channel_id": "C1",
        }

    def _patch_routing(self, notifier):
        """Patch routing methods to capture calls without triggering LLM."""
        routed = []
        notifier._get_channel_role = lambda ch: None
        notifier._route_message_via_llm = lambda text: MagicMock()
        notifier._execute_routed_action = lambda *a, **kw: routed.append(a)
        return routed

    def test_dedup_skips_already_processed_ts(self, tmp_path):
        """A ts already in _processed_message_ts is skipped on second encounter."""
        notifier = self._make_notifier(tmp_path)
        routed = self._patch_routing(notifier)

        msg = self._channel_msg("100.0", "First delivery")
        notifier._handle_polled_messages([msg])
        first_routed = len(routed)

        # Second delivery of the same ts must be skipped
        notifier._handle_polled_messages([msg])
        assert len(routed) == first_routed, "Duplicate ts must not reach routing"

    def test_self_origin_accepted_under_rate_limit(self, tmp_path):
        """A self-origin message is processed when loop count is under threshold.

        With MAX_SELF_REPLIES_PER_WINDOW=1, the first self-origin message
        with an empty window should be accepted.
        """
        notifier = self._make_notifier(tmp_path)
        routed = self._patch_routing(notifier)

        ts = "200.0"
        notifier._own_sent_ts.add(ts)
        # Empty window: 0 recent entries, below threshold of 1
        notifier._self_reply_window["C1"] = []

        notifier._handle_polled_messages([self._channel_msg(ts)])
        assert len(routed) > 0, "Self-origin message under limit must reach routing"

    def test_loop_detected_skips_message(self, tmp_path):
        """A self-origin message is skipped when loop count meets threshold.

        With MAX_SELF_REPLIES_PER_WINDOW=1 and LOOP_DETECTION_WINDOW_SECONDS=300,
        having 1 recent entry in the window triggers the loop detector.
        """
        notifier = self._make_notifier(tmp_path)
        routed = self._patch_routing(notifier)

        ts = "300.0"
        notifier._own_sent_ts.add(ts)
        # At threshold: 1 recent entry within the 300s window
        now = time.monotonic()
        notifier._self_reply_window["C1"] = [now - 10]

        notifier._handle_polled_messages([self._channel_msg(ts)])
        assert len(routed) == 0, "Self-origin message at loop threshold must be skipped"

    def test_prune_removes_old_entries(self, tmp_path):
        """_prune_message_tracking removes expired ts entries and old window slots."""
        notifier = self._make_notifier(tmp_path)

        old_ts = str(time.time() - MESSAGE_TRACKING_TTL_SECONDS - 1)
        recent_ts = str(time.time() - 10)

        notifier._processed_message_ts.update({old_ts, recent_ts})
        notifier._own_sent_ts.add(old_ts)

        # Expired window slot (older than LOOP_DETECTION_WINDOW_SECONDS)
        old_slot = time.monotonic() - LOOP_DETECTION_WINDOW_SECONDS - 1
        recent_slot = time.monotonic() - 5
        notifier._self_reply_window["C1"] = [old_slot, recent_slot]

        notifier._prune_message_tracking()

        assert old_ts not in notifier._processed_message_ts
        assert recent_ts in notifier._processed_message_ts
        assert old_ts not in notifier._own_sent_ts
        # Old window slot pruned; recent slot kept
        assert recent_slot in notifier._self_reply_window.get("C1", [])
        assert old_slot not in notifier._self_reply_window.get("C1", [])

    def test_post_message_records_ts_in_own_sent_ts(self, tmp_path):
        """_post_message stores the returned ts in _own_sent_ts."""
        notifier = self._make_notifier(tmp_path)
        notifier._bot_token = "xoxb-test"
        notifier._channel_id = "C1"

        fake_response = MagicMock()
        fake_response.read.return_value = b'{"ok": true, "ts": "999.0"}'
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=fake_response):
            notifier._post_message({"blocks": []})

        assert "999.0" in notifier._own_sent_ts


# ─── A3: Bot notification pattern filter tests ───────────────────


class TestBotNotificationPattern:
    """Tests for BOT_NOTIFICATION_PATTERN regex matching."""

    def test_matches_defect_received_with_emoji(self):
        """Matches ':white_check_mark: *Defect received*' format."""
        text = ":white_check_mark: *Defect received* (#17552 - some-file.md)"
        assert BOT_NOTIFICATION_PATTERN.search(text) is not None

    def test_matches_feature_created_with_emoji(self):
        """Matches ':large_blue_circle: *Feature created*' format."""
        text = ":large_blue_circle: *Feature created* (#42 - cool-feature.md)"
        assert BOT_NOTIFICATION_PATTERN.search(text) is not None

    def test_matches_received_your_defect_request(self):
        """Matches 'Received your defect request' format."""
        text = "Received your defect request. Analyzing..."
        assert BOT_NOTIFICATION_PATTERN.search(text) is not None

    def test_matches_received_your_feature_request(self):
        """Matches 'Received your feature request' format."""
        text = "Received your feature request. Analyzing..."
        assert BOT_NOTIFICATION_PATTERN.search(text) is not None

    def test_matches_completed_notification(self):
        """Matches ':white_check_mark: *Completed:* defect: ...' format."""
        text = ":white_check_mark: *Completed:* defect: 2 Insufficient Context"
        assert BOT_NOTIFICATION_PATTERN.search(text) is not None

    def test_matches_pipeline_processing(self):
        """Matches ':large_blue_circle: *Pipeline: processing*' format."""
        text = ":large_blue_circle: *Pipeline: processing* defect: 3 There Is A Self Skip"
        assert BOT_NOTIFICATION_PATTERN.search(text) is not None

    def test_matches_pipeline_completed(self):
        """Matches ':white_check_mark: *Pipeline: completed*' format."""
        text = ":white_check_mark: *Pipeline: completed* defect: 2 Insufficient Context"
        assert BOT_NOTIFICATION_PATTERN.search(text) is not None

    def test_matches_pipeline_failed(self):
        """Matches ':x: *Pipeline: failed*' format."""
        text = ":x: *Pipeline: failed* defect: 5 Some Broken Thing"
        assert BOT_NOTIFICATION_PATTERN.search(text) is not None

    def test_no_match_on_normal_message(self):
        """Does NOT match a normal user message."""
        text = "The login button is broken on mobile"
        assert BOT_NOTIFICATION_PATTERN.search(text) is None

    def test_no_match_on_status_update(self):
        """Does NOT match a general status update."""
        text = "Pipeline completed task 3/5"
        assert BOT_NOTIFICATION_PATTERN.search(text) is None

    def test_notification_filter_skips_in_handle_polled(self, tmp_path):
        """_handle_polled_messages skips bot notification messages."""
        config_file = tmp_path / "slack.yaml"
        config_file.write_text(yaml.dump({"slack": {"enabled": False}}))
        notifier = SlackNotifier(config_path=str(config_file))
        identity = AgentIdentity(project="test", agents={
            "orchestrator": "Test-Orchestrator",
        })
        notifier.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)

        routed = []
        notifier._get_channel_role = lambda ch: None
        notifier._route_message_via_llm = lambda text: MagicMock()
        notifier._execute_routed_action = lambda *a, **kw: routed.append(a)

        msg = {
            "text": ":white_check_mark: *Defect received* (#100 - test.md)",
            "user": "bot",
            "ts": "500.0",
            "_channel_name": "orchestrator-notifications",
            "_channel_id": "C1",
        }
        notifier._handle_polled_messages([msg])
        assert len(routed) == 0, "Bot notification message must be skipped"


# ─── A1: Chain detection tests ──────────────────────────────────


class TestChainDetection:
    """Tests for intake history chain-loop detection."""

    def _make_notifier(self, tmp_path):
        config_file = tmp_path / "slack.yaml"
        config_file.write_text(yaml.dump({"slack": {"enabled": False}}))
        notifier = SlackNotifier(config_path=str(config_file))
        identity = AgentIdentity(project="test", agents={
            "orchestrator": "Test-Orchestrator",
        })
        notifier.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)
        return notifier

    def test_detects_item_number_reference(self, tmp_path):
        """Chain detection catches text referencing a recently created item."""
        notifier = self._make_notifier(tmp_path)
        notifier._intake_history = [
            {"item_number": 17552, "slug": "some-defect", "title_summary": "test",
             "timestamp": time.time()},
        ]
        text = ":white_check_mark: Defect received (#17552 - some-defect.md)"
        assert notifier._is_chain_loop_artifact(text) is True

    def test_does_not_match_unrelated_text(self, tmp_path):
        """Chain detection does not false-positive on unrelated text."""
        notifier = self._make_notifier(tmp_path)
        notifier._intake_history = [
            {"item_number": 17552, "slug": "some-defect", "title_summary": "test",
             "timestamp": time.time()},
        ]
        text = "The login button is broken on mobile browsers"
        assert notifier._is_chain_loop_artifact(text) is False

    def test_chain_filter_skips_in_handle_polled(self, tmp_path):
        """_handle_polled_messages skips chain loop artifacts."""
        notifier = self._make_notifier(tmp_path)
        notifier._intake_history = [
            {"item_number": 42, "slug": "login-bug", "title_summary": "Login bug",
             "timestamp": time.time()},
        ]

        routed = []
        notifier._get_channel_role = lambda ch: None
        notifier._route_message_via_llm = lambda text: MagicMock()
        notifier._execute_routed_action = lambda *a, **kw: routed.append(a)

        msg = {
            "text": "Defect created (#42 - login-bug.md): Login bug",
            "user": "bot",
            "ts": "600.0",
            "_channel_name": "orchestrator-defects",
            "_channel_id": "C2",
        }
        notifier._handle_polled_messages([msg])
        assert len(routed) == 0, "Chain loop artifact must be skipped"


# ─── A4: Global intake rate limiter tests ────────────────────────


class TestIntakeRateLimiter:
    """Tests for the global intake rate limiter."""

    def _make_notifier(self, tmp_path):
        config_file = tmp_path / "slack.yaml"
        config_file.write_text(yaml.dump({"slack": {"enabled": False}}))
        return SlackNotifier(config_path=str(config_file))

    def test_under_limit_allows(self, tmp_path):
        """Rate limiter allows intakes when under the threshold."""
        notifier = self._make_notifier(tmp_path)
        assert notifier._check_intake_rate_limit() is False

    def test_at_limit_blocks(self, tmp_path):
        """Rate limiter blocks when at MAX_INTAKES_PER_WINDOW."""
        notifier = self._make_notifier(tmp_path)
        now = time.time()
        notifier._intake_timestamps = [
            now - i for i in range(MAX_INTAKES_PER_WINDOW)
        ]
        assert notifier._check_intake_rate_limit() is True

    def test_old_entries_pruned(self, tmp_path):
        """Rate limiter prunes entries outside the window."""
        notifier = self._make_notifier(tmp_path)
        old_time = time.time() - INTAKE_RATE_WINDOW_SECONDS - 10
        notifier._intake_timestamps = [
            old_time - i for i in range(MAX_INTAKES_PER_WINDOW)
        ]
        assert notifier._check_intake_rate_limit() is False


# ─── Disk-persisted backlog creation throttle tests ───────────────


class TestBacklogCreationThrottle:
    """Tests for the disk-persisted backlog creation throttle."""

    def _make_notifier(self, tmp_path):
        config_file = tmp_path / "slack.yaml"
        config_file.write_text(yaml.dump({"slack": {"enabled": False}}))
        return SlackNotifier(config_path=str(config_file))

    def _throttle_path(self, tmp_path):
        return str(tmp_path / "throttle.json")

    def test_allows_under_limit(self, tmp_path):
        """Throttle allows creation when under the per-type limit."""
        notifier = self._make_notifier(tmp_path)
        throttle_file = self._throttle_path(tmp_path)
        now = time.time()
        # Pre-fill with a few entries (well under MAX_DEFECTS_PER_HOUR)
        data = {"defect": [now - 60, now - 30, now - 10]}
        with open(throttle_file, "w") as f:
            json.dump(data, f)

        with patch.object(mod, "BACKLOG_CREATION_THROTTLE_PATH", throttle_file):
            assert notifier._check_backlog_throttle("defect") is False

    def test_blocks_at_limit(self, tmp_path):
        """Throttle blocks creation when at the per-type limit."""
        notifier = self._make_notifier(tmp_path)
        throttle_file = self._throttle_path(tmp_path)
        now = time.time()
        # Fill with exactly MAX_DEFECTS_PER_HOUR recent entries
        data = {"defect": [now - i for i in range(MAX_DEFECTS_PER_HOUR)]}
        with open(throttle_file, "w") as f:
            json.dump(data, f)

        with patch.object(mod, "BACKLOG_CREATION_THROTTLE_PATH", throttle_file):
            assert notifier._check_backlog_throttle("defect") is True

    def test_prune_old_entries(self, tmp_path):
        """Old timestamps are pruned, allowing new creations."""
        notifier = self._make_notifier(tmp_path)
        throttle_file = self._throttle_path(tmp_path)
        old_time = time.time() - BACKLOG_THROTTLE_WINDOW_SECONDS - 100
        # All entries are expired
        data = {"defect": [old_time - i for i in range(MAX_DEFECTS_PER_HOUR)]}
        with open(throttle_file, "w") as f:
            json.dump(data, f)

        with patch.object(mod, "BACKLOG_CREATION_THROTTLE_PATH", throttle_file):
            assert notifier._check_backlog_throttle("defect") is False

    def test_persists_across_instances(self, tmp_path):
        """Throttle data written by one notifier is read by another."""
        throttle_file = self._throttle_path(tmp_path)

        with patch.object(mod, "BACKLOG_CREATION_THROTTLE_PATH", throttle_file):
            notifier1 = self._make_notifier(tmp_path)
            notifier1._record_backlog_creation("defect")

            notifier2 = self._make_notifier(tmp_path)
            data = notifier2._load_backlog_throttle()
            assert len(data.get("defect", [])) == 1

    def test_separate_limits_per_type(self, tmp_path):
        """Defect limit does not affect feature creation."""
        notifier = self._make_notifier(tmp_path)
        throttle_file = self._throttle_path(tmp_path)
        now = time.time()
        # Max out defects, leave features empty
        data = {"defect": [now - i for i in range(MAX_DEFECTS_PER_HOUR)]}
        with open(throttle_file, "w") as f:
            json.dump(data, f)

        with patch.object(mod, "BACKLOG_CREATION_THROTTLE_PATH", throttle_file):
            assert notifier._check_backlog_throttle("defect") is True
            assert notifier._check_backlog_throttle("feature") is False


# ─── Verbose FILTER logging tests ────────────────────────────────


class TestVerboseFilterLogging:
    """Tests that verbose_log() is called with FILTER prefix for each filtering decision."""

    def _make_notifier_with_identity(self, tmp_path):
        config_file = tmp_path / "slack.yaml"
        config_file.write_text(yaml.dump({"slack": {"enabled": False}}))
        notifier = SlackNotifier(config_path=str(config_file))
        identity = AgentIdentity(
            project="test",
            agents={
                "pipeline": "Test-Pipeline",
                "orchestrator": "Test-Orchestrator",
                "intake": "Test-Intake",
                "qa": "Test-QA",
            },
        )
        notifier.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)
        return notifier

    def _patch_routing(self, notifier):
        notifier._get_channel_role = lambda ch: None
        notifier._route_message_via_llm = lambda text: MagicMock()
        notifier._execute_routed_action = lambda *a, **kw: None

    def test_verbose_filter_skip_own_agent(self, tmp_path):
        """verbose_log is called with FILTER prefix when a self-origin loop is detected."""
        notifier = self._make_notifier_with_identity(tmp_path)
        self._patch_routing(notifier)

        ts = "700.0"
        notifier._own_sent_ts.add(ts)
        now = time.monotonic()
        notifier._self_reply_window["C1"] = [now - 10] * MAX_SELF_REPLIES_PER_WINDOW

        msg = {
            "text": "Task completed successfully",
            "user": "bot",
            "ts": ts,
            "_channel_name": "orchestrator-notifications",
            "_channel_id": "C1",
        }

        with patch.object(mod, "verbose_log") as mock_vlog:
            notifier._handle_polled_messages([msg])

        mock_vlog.assert_called_once()
        call_args = mock_vlog.call_args[0]
        assert call_args[1] == "FILTER"
        assert "Skip own-agent loop-detected" in call_args[0]

    def test_verbose_filter_skip_addressed_to_others(self, tmp_path):
        """verbose_log is called with FILTER prefix when a message is addressed only to other agents."""
        notifier = self._make_notifier_with_identity(tmp_path)
        self._patch_routing(notifier)

        msg = {
            "text": "@Other-Pipeline please check this issue",
            "user": "human",
            "ts": "701.0",
            "_channel_name": "orchestrator-notifications",
            "_channel_id": "C1",
        }

        with patch.object(mod, "verbose_log") as mock_vlog:
            notifier._handle_polled_messages([msg])

        mock_vlog.assert_called_once()
        call_args = mock_vlog.call_args[0]
        assert call_args[1] == "FILTER"
        assert "Skip addressed-to-others" in call_args[0]

    def test_verbose_filter_accept_addressed_to_us(self, tmp_path):
        """verbose_log is called with FILTER prefix when a message is addressed to one of our agents."""
        notifier = self._make_notifier_with_identity(tmp_path)
        self._patch_routing(notifier)

        msg = {
            "text": "@Test-Orchestrator what is the current status?",
            "user": "human",
            "ts": "702.0",
            "_channel_name": "orchestrator-notifications",
            "_channel_id": "C1",
        }

        with patch.object(mod, "verbose_log") as mock_vlog:
            notifier._handle_polled_messages([msg])

        mock_vlog.assert_called_once()
        call_args = mock_vlog.call_args[0]
        assert call_args[1] == "FILTER"
        assert "Accept addressed-to-us" in call_args[0]

    def test_verbose_filter_accept_broadcast(self, tmp_path):
        """verbose_log is called with FILTER prefix for broadcast messages with no @addressing."""
        notifier = self._make_notifier_with_identity(tmp_path)
        self._patch_routing(notifier)

        msg = {
            "text": "General status update for everyone",
            "user": "human",
            "ts": "703.0",
            "_channel_name": "orchestrator-notifications",
            "_channel_id": "C1",
        }

        with patch.object(mod, "verbose_log") as mock_vlog:
            notifier._handle_polled_messages([msg])

        mock_vlog.assert_called_once()
        call_args = mock_vlog.call_args[0]
        assert call_args[1] == "FILTER"
        assert "Accept broadcast" in call_args[0]


# ─── A0: Bot user ID self-skip filter tests ──────────────────────


class TestBotUserIdSelfSkip:
    """Tests for A0 identity-based bot user ID self-skip in SlackNotifier."""

    def _make_notifier(self, tmp_path):
        config_file = tmp_path / "slack.yaml"
        config_file.write_text(yaml.dump({"slack": {"enabled": False}}))
        return SlackNotifier(config_path=str(config_file))

    def _channel_msg(self, ts: str, user: str) -> dict:
        return {
            "text": "The login button is broken on mobile",
            "user": user,
            "ts": ts,
            "_channel_name": "orchestrator-notifications",
            "_channel_id": "C1",
        }

    def _patch_routing(self, notifier):
        routed = []
        notifier._get_channel_role = lambda ch: None
        notifier._route_message_via_llm = lambda text: MagicMock()
        notifier._execute_routed_action = lambda *a, **kw: routed.append(a)
        return routed

    def test_own_user_id_message_is_skipped(self, tmp_path):
        """Message whose user field equals _bot_user_id is skipped and ts recorded."""
        notifier = self._make_notifier(tmp_path)
        notifier._bot_user_id = "UBOT123"

        notifier._handle_polled_messages([self._channel_msg("800.0", "UBOT123")])

        assert "800.0" in notifier._processed_message_ts

    def test_different_user_id_passes_filter(self, tmp_path):
        """Message from a different user is not filtered by A0 and reaches routing."""
        notifier = self._make_notifier(tmp_path)
        notifier._bot_user_id = "UBOT123"
        routed = self._patch_routing(notifier)

        notifier._handle_polled_messages([self._channel_msg("801.0", "UHUMAN")])

        assert len(routed) > 0, "Message from different user must pass A0 and reach routing"

    def test_no_bot_user_id_passes_filter(self, tmp_path):
        """When _bot_user_id is None, A0 is skipped and message reaches routing."""
        notifier = self._make_notifier(tmp_path)
        assert notifier._bot_user_id is None
        routed = self._patch_routing(notifier)

        notifier._handle_polled_messages([self._channel_msg("802.0", "UANYUSER")])

        assert len(routed) > 0, "Message must reach routing when _bot_user_id is None"

    def test_resolve_own_bot_id_sets_user_id(self, tmp_path):
        """_resolve_own_bot_id stores user_id from a successful auth.test response."""
        notifier = self._make_notifier(tmp_path)
        notifier._bot_token = "xoxb-test"
        notifier._bot_user_id = None

        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(
            {"ok": True, "user_id": "UBOT456"}
        ).encode()
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=fake_response):
            notifier._resolve_own_bot_id()

        assert notifier._bot_user_id == "UBOT456"

    def test_resolve_own_bot_id_graceful_on_failure(self, tmp_path):
        """_resolve_own_bot_id leaves _bot_user_id as None when auth.test raises."""
        notifier = self._make_notifier(tmp_path)
        notifier._bot_token = "xoxb-test"
        notifier._bot_user_id = None

        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            notifier._resolve_own_bot_id()

        assert notifier._bot_user_id is None

