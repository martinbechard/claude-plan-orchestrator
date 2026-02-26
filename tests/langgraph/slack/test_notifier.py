# tests/langgraph/slack/test_notifier.py
# Unit tests for langgraph_pipeline.slack.notifier module.
# Design: docs/plans/2026-02-26-03-extract-slack-modules-design.md

"""Unit tests for SlackNotifier: config loading, message posting, channel
discovery, formatting, and send methods. All Slack API calls are mocked."""

import json
from io import BytesIO
from unittest.mock import MagicMock, mock_open, patch

import pytest
import yaml

from langgraph_pipeline.slack.identity import (
    AGENT_ROLE_ORCHESTRATOR,
    AgentIdentity,
)
from langgraph_pipeline.slack.notifier import (
    MESSAGE_ROUTING_PROMPT,
    SLACK_BLOCK_TEXT_MAX_LENGTH,
    SLACK_CHANNEL_PREFIX,
    SLACK_LEVEL_EMOJI,
    SlackNotifier,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_config_yaml(
    enabled: bool = True,
    bot_token: str = "xoxb-test",
    app_token: str = "",
    channel_id: str = "C123",
    notify: dict | None = None,
    channel_prefix: str = "",
) -> str:
    slack_section: dict = {
        "enabled": enabled,
        "bot_token": bot_token,
        "channel_id": channel_id,
    }
    if app_token:
        slack_section["app_token"] = app_token
    if notify:
        slack_section["notify"] = notify
    if channel_prefix:
        slack_section["channel_prefix"] = channel_prefix
    return yaml.dump({"slack": slack_section})


def _make_notifier(
    enabled: bool = True,
    bot_token: str = "xoxb-test",
    channel_id: str = "C123",
    notify: dict | None = None,
    channel_prefix: str = "",
) -> SlackNotifier:
    """Return a SlackNotifier initialised from in-memory config."""
    config_text = _make_config_yaml(
        enabled=enabled,
        bot_token=bot_token,
        channel_id=channel_id,
        notify=notify,
        channel_prefix=channel_prefix,
    )
    with patch("builtins.open", mock_open(read_data=config_text)):
        return SlackNotifier()


def _api_response(ok: bool = True, ts: str = "1700000000.000001", **extra) -> BytesIO:
    """Fake urllib response body."""
    body = {"ok": ok, "ts": ts, **extra}
    return BytesIO(json.dumps(body).encode())


# ── Init and is_enabled ──────────────────────────────────────────────────────


class TestInit:
    """SlackNotifier.__init__ reads config and sets state."""

    def test_enabled_when_config_ok(self):
        n = _make_notifier(enabled=True)
        assert n.is_enabled() is True

    def test_disabled_when_enabled_false(self):
        n = _make_notifier(enabled=False)
        assert n.is_enabled() is False

    def test_disabled_when_file_missing(self):
        with patch("builtins.open", side_effect=IOError("no file")):
            n = SlackNotifier()
        assert n.is_enabled() is False

    def test_disabled_when_yaml_invalid(self):
        with patch("builtins.open", mock_open(read_data=": invalid: yaml: [")):
            n = SlackNotifier()
        assert n.is_enabled() is False

    def test_channel_prefix_normalised(self):
        """Prefix without trailing dash gets one appended."""
        n = _make_notifier(channel_prefix="mybot")
        assert n._channel_prefix == "mybot-"

    def test_channel_prefix_with_dash_unchanged(self):
        n = _make_notifier(channel_prefix="mybot-")
        assert n._channel_prefix == "mybot-"

    def test_default_channel_prefix(self):
        n = _make_notifier()
        assert n._channel_prefix == SLACK_CHANNEL_PREFIX


# ── _should_notify ───────────────────────────────────────────────────────────


class TestShouldNotify:
    """_should_notify gates event-specific notifications."""

    def test_returns_true_when_event_enabled(self):
        n = _make_notifier(notify={"on_task_complete": True})
        assert n._should_notify("on_task_complete") is True

    def test_returns_false_when_event_absent(self):
        n = _make_notifier()
        assert n._should_notify("on_task_complete") is False

    def test_returns_false_when_event_disabled(self):
        n = _make_notifier(notify={"on_task_complete": False})
        assert n._should_notify("on_task_complete") is False

    def test_returns_false_when_notifier_disabled(self):
        n = _make_notifier(enabled=False)
        assert n._should_notify("on_task_complete") is False


# ── _truncate_for_slack ──────────────────────────────────────────────────────


class TestTruncateForSlack:
    """_truncate_for_slack trims oversized text."""

    def test_short_text_unchanged(self):
        text = "hello"
        assert SlackNotifier._truncate_for_slack(text) == text

    def test_exact_max_unchanged(self):
        text = "x" * SLACK_BLOCK_TEXT_MAX_LENGTH
        assert SlackNotifier._truncate_for_slack(text) == text

    def test_over_limit_truncated(self):
        text = "a" * (SLACK_BLOCK_TEXT_MAX_LENGTH + 100)
        result = SlackNotifier._truncate_for_slack(text)
        assert len(result) <= SLACK_BLOCK_TEXT_MAX_LENGTH
        assert "omitted" in result

    def test_custom_max_length(self):
        text = "x" * 200
        result = SlackNotifier._truncate_for_slack(text, max_length=100)
        assert len(result) <= 100
        assert "omitted" in result


# ── _build_status_block ──────────────────────────────────────────────────────


class TestBuildStatusBlock:
    """_build_status_block produces correct Block Kit structure."""

    def test_structure_has_blocks_and_section(self):
        n = _make_notifier()
        block = n._build_status_block("test message", "info")
        assert "blocks" in block
        assert block["blocks"][0]["type"] == "section"

    def test_info_level_uses_correct_emoji(self):
        n = _make_notifier()
        block = n._build_status_block("msg", "info")
        text = block["blocks"][0]["text"]["text"]
        assert SLACK_LEVEL_EMOJI["info"] in text

    def test_error_level_uses_correct_emoji(self):
        n = _make_notifier()
        block = n._build_status_block("msg", "error")
        text = block["blocks"][0]["text"]["text"]
        assert SLACK_LEVEL_EMOJI["error"] in text

    def test_unknown_level_falls_back_to_info_emoji(self):
        n = _make_notifier()
        block = n._build_status_block("msg", "unknown-level")
        text = block["blocks"][0]["text"]["text"]
        assert SLACK_LEVEL_EMOJI["info"] in text

    def test_includes_agent_signature_when_identity_set(self):
        n = _make_notifier()
        identity = AgentIdentity(
            project="test", agents={"orchestrator": "Test-Orchestrator"}
        )
        n.set_identity(identity, AGENT_ROLE_ORCHESTRATOR)
        block = n._build_status_block("msg", "info")
        text = block["blocks"][0]["text"]["text"]
        assert "Test-Orchestrator" in text

    def test_no_signature_without_identity(self):
        n = _make_notifier()
        block = n._build_status_block("msg", "info")
        text = block["blocks"][0]["text"]["text"]
        assert "\u2014" not in text


# ── _post_message ────────────────────────────────────────────────────────────


class TestPostMessage:
    """_post_message sends HTTP request and handles responses."""

    def _url_open_mock(self, ok=True, ts="1700.1"):
        ctx = MagicMock()
        ctx.__enter__ = lambda s: BytesIO(json.dumps({"ok": ok, "ts": ts}).encode())
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx

    def test_returns_true_on_success(self):
        n = _make_notifier()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: BytesIO(
            json.dumps({"ok": True, "ts": "1700.1"}).encode()
        )
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = n._post_message({"text": "hello"})
        assert result is True

    def test_returns_false_on_api_error(self):
        n = _make_notifier()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: BytesIO(
            json.dumps({"ok": False, "error": "channel_not_found"}).encode()
        )
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = n._post_message({"text": "hello"})
        assert result is False

    def test_returns_false_when_no_token(self):
        n = _make_notifier(bot_token="")
        result = n._post_message({"text": "hello"})
        assert result is False

    def test_tracks_sent_ts(self):
        n = _make_notifier()
        ts = "1700000000.000001"
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: BytesIO(
            json.dumps({"ok": True, "ts": ts}).encode()
        )
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            n._post_message({"text": "hello"})
        assert ts in n._own_sent_ts

    def test_returns_false_on_network_exception(self):
        n = _make_notifier()
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = n._post_message({"text": "hello"})
        assert result is False


# ── _post_message_get_ts ─────────────────────────────────────────────────────


class TestPostMessageGetTs:
    """_post_message_get_ts returns timestamp or None."""

    def test_returns_ts_on_success(self):
        n = _make_notifier()
        ts = "1700000000.000002"
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: BytesIO(
            json.dumps({"ok": True, "ts": ts}).encode()
        )
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = n._post_message_get_ts({"text": "hello"})
        assert result == ts

    def test_returns_none_on_api_error(self):
        n = _make_notifier()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: BytesIO(
            json.dumps({"ok": False, "error": "channel_not_found"}).encode()
        )
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = n._post_message_get_ts({"text": "hello"})
        assert result is None

    def test_returns_none_when_no_token(self):
        n = _make_notifier(bot_token="")
        result = n._post_message_get_ts({"text": "hello"})
        assert result is None

    def test_tracks_sent_ts(self):
        n = _make_notifier()
        ts = "1700000000.000003"
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: BytesIO(
            json.dumps({"ok": True, "ts": ts}).encode()
        )
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            n._post_message_get_ts({"text": "hello"})
        assert ts in n._own_sent_ts


# ── _discover_channels ───────────────────────────────────────────────────────


class TestDiscoverChannels:
    """_discover_channels fetches prefix-matched channels and caches results."""

    def _make_channels_resp(self, channel_names: list[str]) -> MagicMock:
        channels_data = [{"name": n, "id": f"C{i}"} for i, n in enumerate(channel_names)]
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: BytesIO(
            json.dumps({"ok": True, "channels": channels_data}).encode()
        )
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_returns_prefix_matched_channels(self):
        n = _make_notifier()
        channel_names = [
            "orchestrator-notifications",
            "orchestrator-features",
            "unrelated-channel",
        ]
        with patch("urllib.request.urlopen", return_value=self._make_channels_resp(channel_names)):
            result = n._discover_channels()
        assert "orchestrator-notifications" in result
        assert "orchestrator-features" in result
        assert "unrelated-channel" not in result

    def test_returns_cached_result_within_ttl(self):
        n = _make_notifier()
        n._discovered_channels = {"orchestrator-notifications": "C999"}
        n._channels_discovered_at = 9999999999.0  # far future

        with patch("urllib.request.urlopen") as mock_open:
            result = n._discover_channels()
            mock_open.assert_not_called()

        assert result == {"orchestrator-notifications": "C999"}

    def test_refreshes_cache_after_ttl(self):
        n = _make_notifier()
        n._discovered_channels = {"old": "C0"}
        n._channels_discovered_at = 0.0  # expired

        channel_names = ["orchestrator-features"]
        with patch("urllib.request.urlopen", return_value=self._make_channels_resp(channel_names)):
            result = n._discover_channels()

        assert "orchestrator-features" in result
        assert "old" not in result

    def test_returns_previous_on_api_error(self):
        n = _make_notifier()
        n._discovered_channels = {"orchestrator-notifications": "C1"}
        n._channels_discovered_at = 0.0  # expired

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: BytesIO(
            json.dumps({"ok": False, "error": "not_authed"}).encode()
        )
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = n._discover_channels()

        # Falls back to previous cache on error
        assert result == {"orchestrator-notifications": "C1"}

    def test_returns_previous_on_network_exception(self):
        n = _make_notifier()
        n._discovered_channels = {"orchestrator-features": "C2"}
        n._channels_discovered_at = 0.0

        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            result = n._discover_channels()

        assert result == {"orchestrator-features": "C2"}


# ── _get_notifications_channel_id ────────────────────────────────────────────


class TestGetNotificationsChannelId:
    """_get_notifications_channel_id resolves the notifications channel."""

    def test_returns_discovered_notifications_channel(self):
        n = _make_notifier()
        n._discovered_channels = {"orchestrator-notifications": "C_NOTIF"}
        n._channels_discovered_at = 9999999999.0

        result = n._get_notifications_channel_id()
        assert result == "C_NOTIF"

    def test_falls_back_to_channel_id_when_not_discovered(self):
        n = _make_notifier(channel_id="C_LEGACY")
        n._discovered_channels = {}
        n._channels_discovered_at = 9999999999.0

        result = n._get_notifications_channel_id()
        assert result == "C_LEGACY"


# ── get_type_channel_id ──────────────────────────────────────────────────────


class TestGetTypeChannelId:
    """get_type_channel_id resolves type-specific channels."""

    def _notifier_with_channels(self) -> SlackNotifier:
        n = _make_notifier()
        n._discovered_channels = {
            "orchestrator-features": "C_FEAT",
            "orchestrator-defects": "C_DEFECT",
            "orchestrator-reports": "C_REPORT",
        }
        n._channels_discovered_at = 9999999999.0
        return n

    def test_returns_feature_channel(self):
        n = self._notifier_with_channels()
        assert n.get_type_channel_id("feature") == "C_FEAT"

    def test_returns_defect_channel(self):
        n = self._notifier_with_channels()
        assert n.get_type_channel_id("defect") == "C_DEFECT"

    def test_returns_analysis_channel(self):
        n = self._notifier_with_channels()
        assert n.get_type_channel_id("analysis") == "C_REPORT"

    def test_returns_empty_for_unknown_type(self):
        n = self._notifier_with_channels()
        assert n.get_type_channel_id("unknown") == ""

    def test_returns_empty_when_channel_not_found(self):
        n = _make_notifier()
        n._discovered_channels = {}
        n._channels_discovered_at = 9999999999.0
        assert n.get_type_channel_id("feature") == ""


# ── send_status ──────────────────────────────────────────────────────────────


class TestSendStatus:
    """send_status sends to the notifications channel."""

    def test_posts_to_notifications_channel(self):
        n = _make_notifier()
        n._discovered_channels = {"orchestrator-notifications": "C_NOTIF"}
        n._channels_discovered_at = 9999999999.0

        with patch.object(n, "_post_message", return_value=True) as mock_post:
            n.send_status("Pipeline started", "info")

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs.get("channel_id") == "C_NOTIF" or mock_post.call_args[0][1] == "C_NOTIF"

    def test_noop_when_disabled(self):
        n = _make_notifier(enabled=False)
        with patch.object(n, "_post_message") as mock_post:
            n.send_status("msg")
        mock_post.assert_not_called()

    def test_uses_override_channel_id(self):
        n = _make_notifier()
        with patch.object(n, "_post_message", return_value=True) as mock_post:
            n.send_status("msg", channel_id="C_OVERRIDE")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        # channel_id can be positional or keyword
        channel_used = kwargs.get("channel_id") or (args[1] if len(args) > 1 else None)
        assert channel_used == "C_OVERRIDE"


# ── send_defect ──────────────────────────────────────────────────────────────


class TestSendDefect:
    """send_defect posts defect reports when notify event is enabled."""

    def test_posts_when_event_enabled(self):
        n = _make_notifier(notify={"on_defect_found": True})
        with patch.object(n, "_post_message", return_value=True) as mock_post:
            n.send_defect("NullPointerException", "happens on startup")
        mock_post.assert_called_once()

    def test_noop_when_event_disabled(self):
        n = _make_notifier(notify={"on_defect_found": False})
        with patch.object(n, "_post_message") as mock_post:
            n.send_defect("Bug", "desc")
        mock_post.assert_not_called()

    def test_includes_file_path_in_message(self):
        n = _make_notifier(notify={"on_defect_found": True})
        posted_payloads = []

        def capture(payload, **kwargs):
            posted_payloads.append(payload)
            return True

        with patch.object(n, "_post_message", side_effect=capture):
            n.send_defect("Bug", "description", file_path="src/app.py")

        text = posted_payloads[0]["blocks"][0]["text"]["text"]
        assert "src/app.py" in text

    def test_message_contains_beetle_emoji(self):
        n = _make_notifier(notify={"on_defect_found": True})
        posted_payloads = []

        def capture(payload, **kwargs):
            posted_payloads.append(payload)
            return True

        with patch.object(n, "_post_message", side_effect=capture):
            n.send_defect("Bug", "desc")

        text = posted_payloads[0]["blocks"][0]["text"]["text"]
        assert ":beetle:" in text


# ── send_idea ────────────────────────────────────────────────────────────────


class TestSendIdea:
    """send_idea posts feature ideas when notify event is enabled."""

    def test_posts_when_event_enabled(self):
        n = _make_notifier(notify={"on_idea_found": True})
        with patch.object(n, "_post_message", return_value=True) as mock_post:
            n.send_idea("Add dark mode", "users have been asking")
        mock_post.assert_called_once()

    def test_noop_when_event_disabled(self):
        n = _make_notifier(notify={"on_idea_found": False})
        with patch.object(n, "_post_message") as mock_post:
            n.send_idea("Idea", "desc")
        mock_post.assert_not_called()

    def test_message_contains_bulb_emoji(self):
        n = _make_notifier(notify={"on_idea_found": True})
        posted_payloads = []

        def capture(payload, **kwargs):
            posted_payloads.append(payload)
            return True

        with patch.object(n, "_post_message", side_effect=capture):
            n.send_idea("Dark mode", "desc")

        text = posted_payloads[0]["blocks"][0]["text"]["text"]
        assert ":bulb:" in text


# ── process_agent_messages ───────────────────────────────────────────────────


class TestProcessAgentMessages:
    """process_agent_messages dispatches defect and idea messages."""

    def test_dispatches_defect_message(self):
        n = _make_notifier(notify={"on_defect_found": True})
        status = {
            "slack_messages": [
                {"type": "defect", "title": "Bug found", "description": "desc", "file_path": "f.py"}
            ]
        }
        with patch.object(n, "send_defect") as mock_defect:
            n.process_agent_messages(status)
        mock_defect.assert_called_once_with("Bug found", "desc", "f.py")

    def test_dispatches_idea_message(self):
        n = _make_notifier(notify={"on_idea_found": True})
        status = {
            "slack_messages": [
                {"type": "idea", "title": "New feature", "description": "desc"}
            ]
        }
        with patch.object(n, "send_idea") as mock_idea:
            n.process_agent_messages(status)
        mock_idea.assert_called_once_with("New feature", "desc")

    def test_skips_unknown_message_type(self):
        n = _make_notifier()
        status = {
            "slack_messages": [
                {"type": "unknown", "title": "What?", "description": ""}
            ]
        }
        with patch.object(n, "send_defect") as mock_defect, \
                patch.object(n, "send_idea") as mock_idea:
            n.process_agent_messages(status)
        mock_defect.assert_not_called()
        mock_idea.assert_not_called()

    def test_handles_empty_slack_messages(self):
        n = _make_notifier()
        with patch.object(n, "send_defect") as mock_defect:
            n.process_agent_messages({})
        mock_defect.assert_not_called()

    def test_dispatches_multiple_messages(self):
        n = _make_notifier(notify={"on_defect_found": True, "on_idea_found": True})
        status = {
            "slack_messages": [
                {"type": "defect", "title": "Bug", "description": "d1", "file_path": ""},
                {"type": "idea", "title": "Idea", "description": "d2"},
            ]
        }
        with patch.object(n, "send_defect") as mock_defect, \
                patch.object(n, "send_idea") as mock_idea:
            n.process_agent_messages(status)
        mock_defect.assert_called_once()
        mock_idea.assert_called_once()


# ── MESSAGE_ROUTING_PROMPT ───────────────────────────────────────────────────


class TestMessageRoutingPrompt:
    """MESSAGE_ROUTING_PROMPT constant is well-formed."""

    def test_prompt_is_a_string(self):
        assert isinstance(MESSAGE_ROUTING_PROMPT, str)

    def test_prompt_contains_text_placeholder(self):
        assert "{text}" in MESSAGE_ROUTING_PROMPT

    def test_prompt_contains_a5_hint(self):
        """A5 classification hint: automated notifications -> 'none'."""
        assert "automated pipeline notifications" in MESSAGE_ROUTING_PROMPT.lower() or \
               "none" in MESSAGE_ROUTING_PROMPT
