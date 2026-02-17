# tests/test_slack_notifier.py
# Unit tests for SlackNotifier class.
# Design ref: docs/plans/2026-02-16-14-slack-app-migration-design.md

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

# plan-orchestrator.py has a hyphen in the filename, so we must use importlib
# to load it as a module under a valid Python identifier.
spec = importlib.util.spec_from_file_location(
    "plan_orchestrator", "scripts/plan-orchestrator.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SlackNotifier = mod.SlackNotifier


# --- Test: Disabled when no config file ---


def test_disabled_when_no_config_file(tmp_path):
    """SlackNotifier should be disabled when config file does not exist."""
    nonexistent_path = tmp_path / "nonexistent.yaml"
    notifier = SlackNotifier(config_path=str(nonexistent_path))

    assert notifier.is_enabled() is False
    # send_status should not error when disabled
    notifier.send_status("test message")


# --- Test: Disabled when slack.enabled is false ---


def test_disabled_when_slack_not_enabled(tmp_path):
    """SlackNotifier should be disabled when slack.enabled is false."""
    config_file = tmp_path / "slack.yaml"
    config_data = {"slack": {"enabled": False}}

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))
    assert notifier.is_enabled() is False


# --- Test: Enabled when config is valid ---


def test_enabled_when_config_valid(tmp_path):
    """SlackNotifier should be enabled when config has enabled: true and bot_token/channel_id."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "channel_id": "C0123456789",
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))
    assert notifier.is_enabled() is True


# --- Test: _should_notify respects config ---


def test_should_notify_respects_config(tmp_path):
    """_should_notify should return True/False based on notify config."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "channel_id": "C0123456789",
            "notify": {
                "on_plan_start": True,
                "on_task_complete": False,
            },
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))
    assert notifier._should_notify("on_plan_start") is True
    assert notifier._should_notify("on_task_complete") is False


# --- Test: _build_status_block format ---


def test_build_status_block_format(tmp_path):
    """_build_status_block should return a valid Slack Block Kit payload."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "channel_id": "C0123456789",
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))
    result = notifier._build_status_block("Test message", "success")

    assert "blocks" in result
    assert len(result["blocks"]) == 1
    assert result["blocks"][0]["type"] == "section"
    assert ":white_check_mark:" in result["blocks"][0]["text"]["text"]
    assert "Test message" in result["blocks"][0]["text"]["text"]


# --- Test: _build_status_block default emoji ---


def test_build_status_block_default_emoji(tmp_path):
    """_build_status_block should use default emoji for unknown levels."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "channel_id": "C0123456789",
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))
    result = notifier._build_status_block("msg", "unknown_level")

    # Default emoji is large_blue_circle
    assert ":large_blue_circle:" in result["blocks"][0]["text"]["text"]


# --- Test: _post_message called on send_status ---


def test_post_message_called_on_send_status(tmp_path):
    """send_status should call _post_message with correct payload."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "channel_id": "C0123456789",
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))

    # Monkey-patch _post_message to record calls
    calls = []

    def mock_post_message(payload):
        calls.append(payload)
        return True

    notifier._post_message = mock_post_message

    notifier.send_status("Plan started", level="info")

    assert len(calls) == 1
    assert "blocks" in calls[0]
    assert "Plan started" in calls[0]["blocks"][0]["text"]["text"]


# --- Test: _post_message includes channel_id ---


def test_post_message_includes_channel(tmp_path):
    """_post_message should include channel_id in payload."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "channel_id": "C999",
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))

    # Test _post_message directly
    test_payload = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "test"}}]}

    # Monkey-patch urllib.request.urlopen to capture the request
    import urllib.request
    captured_request = None

    original_urlopen = urllib.request.urlopen

    def mock_urlopen(req, timeout=None):
        nonlocal captured_request
        captured_request = req
        # Return a mock response
        class MockResponse:
            def read(self):
                return b'{"ok": true}'
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        return MockResponse()

    urllib.request.urlopen = mock_urlopen

    try:
        result = notifier._post_message(test_payload)
        assert result is True
        assert captured_request is not None

        # Parse the payload from the request
        payload_bytes = captured_request.data
        payload = json.loads(payload_bytes.decode("utf-8"))
        assert payload.get("channel") == "C999"
    finally:
        urllib.request.urlopen = original_urlopen


# --- Test: send_status noop when disabled ---


def test_send_status_noop_when_disabled(tmp_path):
    """send_status should be a no-op when disabled."""
    nonexistent_path = tmp_path / "nonexistent.yaml"
    notifier = SlackNotifier(config_path=str(nonexistent_path))

    # Should not raise any errors
    notifier.send_status("test")


# --- Test: process_agent_messages with defect ---


def test_process_agent_messages_defect(tmp_path):
    """process_agent_messages should send defect messages via _post_message."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "channel_id": "C0123456789",
            "notify": {
                "on_defect_found": True,
            },
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))

    # Monkey-patch _post_message
    calls = []

    def mock_post_message(payload):
        calls.append(payload)
        return True

    notifier._post_message = mock_post_message

    status = {
        "slack_messages": [
            {"type": "defect", "title": "Bug", "description": "Details"}
        ]
    }

    notifier.process_agent_messages(status)

    assert len(calls) == 1
    payload_text = calls[0]["blocks"][0]["text"]["text"]
    assert "Bug" in payload_text
    assert "Details" in payload_text


# --- Test: process_agent_messages with idea ---


def test_process_agent_messages_idea(tmp_path):
    """process_agent_messages should send idea messages via _post_message."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "channel_id": "C0123456789",
            "notify": {
                "on_idea_found": True,
            },
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))

    # Monkey-patch _post_message
    calls = []

    def mock_post_message(payload):
        calls.append(payload)
        return True

    notifier._post_message = mock_post_message

    status = {
        "slack_messages": [
            {"type": "idea", "title": "Feature", "description": "Cool idea"}
        ]
    }

    notifier.process_agent_messages(status)

    assert len(calls) == 1
    payload_text = calls[0]["blocks"][0]["text"]["text"]
    assert ":bulb:" in payload_text
    assert "Feature" in payload_text


# --- Test: process_agent_messages empty list ---


def test_process_agent_messages_empty(tmp_path):
    """process_agent_messages should do nothing when slack_messages is empty."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "channel_id": "C0123456789",
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))

    # Monkey-patch _post_message
    calls = []

    def mock_post_message(payload):
        calls.append(payload)
        return True

    notifier._post_message = mock_post_message

    status = {"slack_messages": []}
    notifier.process_agent_messages(status)

    assert len(calls) == 0


# --- Test: process_agent_messages no field ---


def test_process_agent_messages_no_field(tmp_path):
    """process_agent_messages should do nothing when slack_messages field is missing."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "channel_id": "C0123456789",
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))

    # Monkey-patch _post_message
    calls = []

    def mock_post_message(payload):
        calls.append(payload)
        return True

    notifier._post_message = mock_post_message

    status = {}
    notifier.process_agent_messages(status)

    assert len(calls) == 0


# --- Test: enabled requires both bot_token and channel_id ---


def test_enabled_requires_bot_token_and_channel_id(tmp_path):
    """SlackNotifier requires both bot_token and channel_id to be enabled."""
    # Config with enabled: true but no bot_token
    config_file1 = tmp_path / "slack1.yaml"
    config_data1 = {
        "slack": {
            "enabled": True,
            "channel_id": "C0123456789",
        }
    }

    with open(config_file1, "w") as f:
        yaml.dump(config_data1, f)

    notifier1 = SlackNotifier(config_path=str(config_file1))

    # Monkey-patch _post_message to verify it's not called
    calls1 = []

    def mock_post_message1(payload):
        calls1.append(payload)
        return True

    notifier1._post_message = mock_post_message1

    notifier1.send_status("test")
    assert len(calls1) == 0

    # Config with bot_token but no channel_id
    config_file2 = tmp_path / "slack2.yaml"
    config_data2 = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
        }
    }

    with open(config_file2, "w") as f:
        yaml.dump(config_data2, f)

    notifier2 = SlackNotifier(config_path=str(config_file2))

    calls2 = []

    def mock_post_message2(payload):
        calls2.append(payload)
        return True

    notifier2._post_message = mock_post_message2

    notifier2.send_status("test")
    assert len(calls2) == 0


# --- Test: send_question returns None when disabled ---


def test_send_question_returns_none_when_disabled(tmp_path):
    """send_question should return None when disabled."""
    nonexistent_path = tmp_path / "nonexistent.yaml"
    notifier = SlackNotifier(config_path=str(nonexistent_path))

    result = notifier.send_question("Question?", ["A", "B"])
    assert result is None


# --- Test: send_question falls back to file polling when Socket Mode unavailable ---


def test_send_question_falls_back_to_file_polling(tmp_path):
    """send_question should fall back to file polling when Socket Mode unavailable."""
    import time

    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "channel_id": "C0123456789",
            "notify": {
                "on_question": True,
            },
            "questions": {
                "enabled": True,
                "timeout_minutes": 0.01,  # Very short timeout (0.6 seconds)
                "fallback": "skip",
            },
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))

    # Monkey-patch _post_message to succeed
    def mock_post_message(payload):
        return True

    notifier._post_message = mock_post_message

    # Monkey-patch _ensure_socket_mode to return False (no Socket Mode)
    notifier._ensure_socket_mode = lambda: False

    # Mock time functions to simulate timeout immediately
    original_time = time.time
    time_calls = [0]

    def mock_time():
        time_calls[0] += 1
        # First call: start time = 0
        # Second call in while condition: return > timeout to exit loop
        if time_calls[0] == 1:
            return 0
        else:
            return 1000  # Far past timeout

    time.time = mock_time
    time.sleep = lambda x: None  # No-op sleep

    try:
        result = notifier.send_question("Question?", ["A", "B"])
        assert result == "skip"  # Should return fallback value
    finally:
        time.time = original_time


# --- Test: Socket Mode available constant ---


def test_socket_mode_available_constant():
    """Verify SOCKET_MODE_AVAILABLE is a bool."""
    assert isinstance(mod.SOCKET_MODE_AVAILABLE, bool)


# --- Test: Slack config constants exist ---


def test_slack_config_constants_exist():
    """Verify SLACK_* constants are defined in the module."""
    assert mod.SLACK_CONFIG_PATH == ".claude/slack.local.yaml"
    assert mod.SLACK_QUESTION_PATH == ".claude/slack-pending-question.json"
    assert mod.SLACK_ANSWER_PATH == ".claude/slack-answer.json"
    assert mod.SLACK_POLL_INTERVAL_SECONDS == 30
    assert isinstance(mod.SOCKET_MODE_AVAILABLE, bool)


# --- Test: Slack level emoji map ---


def test_slack_level_emoji_map():
    """Verify SLACK_LEVEL_EMOJI has the expected keys and format."""
    emoji_map = mod.SLACK_LEVEL_EMOJI

    required_keys = ["info", "success", "error", "warning", "question"]
    for key in required_keys:
        assert key in emoji_map, f"Missing emoji for level: {key}"
        assert emoji_map[key].startswith(":"), f"Emoji for {key} should start with ':'"
        assert emoji_map[key].endswith(":"), f"Emoji for {key} should end with ':'"
