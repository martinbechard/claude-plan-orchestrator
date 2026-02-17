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

    def mock_post_message(payload, channel_id=None):
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
    assert mod.SLACK_POLL_INTERVAL_SECONDS == 15
    assert mod.SLACK_LAST_READ_PATH == ".claude/slack-last-read.json"
    assert mod.SLACK_INBOUND_POLL_LIMIT == 20
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


# --- Test: _load_last_read with no file ---


def test_load_last_read_no_file(tmp_path):
    """_load_last_read_all should return empty dict when no state file exists."""
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

    # Monkey-patch SLACK_LAST_READ_PATH to a nonexistent path
    original_path = mod.SLACK_LAST_READ_PATH
    mod.SLACK_LAST_READ_PATH = str(tmp_path / "nonexistent-last-read.json")

    try:
        result = notifier._load_last_read_all()
        assert result == {}
    finally:
        mod.SLACK_LAST_READ_PATH = original_path


# --- Test: save and load last-read state ---


def test_save_and_load_last_read(tmp_path):
    """_save_last_read_all should persist per-channel state and _load_last_read_all should retrieve it."""
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

    # Monkey-patch SLACK_LAST_READ_PATH to tmp_path
    original_path = mod.SLACK_LAST_READ_PATH
    last_read_file = tmp_path / "last-read.json"
    mod.SLACK_LAST_READ_PATH = str(last_read_file)

    try:
        channels = {"C0123456789": "1234567890.123456", "C9876543210": "9999.1111"}
        notifier._save_last_read_all(channels)
        result = notifier._load_last_read_all()
        assert result == channels

        # Verify the file uses the multi-channel format
        with open(last_read_file, "r") as f:
            data = json.load(f)
        assert "channels" in data
        assert data["channels"]["C0123456789"] == "1234567890.123456"
    finally:
        mod.SLACK_LAST_READ_PATH = original_path


# --- Test: poll_messages when disabled ---


def test_poll_messages_disabled(tmp_path):
    """poll_messages should return empty list when disabled."""
    nonexistent_path = tmp_path / "nonexistent.yaml"
    notifier = SlackNotifier(config_path=str(nonexistent_path))

    result = notifier.poll_messages()
    assert result == []


# --- Test: poll_messages first run sets timestamp ---


def test_poll_messages_first_run_sets_timestamp(tmp_path):
    """poll_messages should seed timestamps on first discovery and fetch recent messages."""
    import urllib.request

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

    # Monkey-patch SLACK_LAST_READ_PATH to tmp_path
    original_path = mod.SLACK_LAST_READ_PATH
    last_read_file = tmp_path / "last-read.json"
    mod.SLACK_LAST_READ_PATH = str(last_read_file)

    # Mock _discover_channels to return a test channel
    notifier._discover_channels = lambda: {"orchestrator-questions": "C0123456789"}

    # Mock conversations.history to return no messages (empty channel)
    original_urlopen = urllib.request.urlopen

    def mock_urlopen(req, timeout=None):
        class MockResponse:
            def read(self_inner):
                return json.dumps({"ok": True, "messages": []}).encode("utf-8")
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, *args):
                pass
        return MockResponse()

    urllib.request.urlopen = mock_urlopen

    try:
        result = notifier.poll_messages()
        assert result == []

        # Verify the last-read file was created
        assert last_read_file.exists()

        # Verify it uses the multi-channel format with a seeded timestamp
        with open(last_read_file, "r") as f:
            data = json.load(f)
        assert "channels" in data
        assert "C0123456789" in data["channels"]
        assert float(data["channels"]["C0123456789"]) > 0
    finally:
        urllib.request.urlopen = original_urlopen
        mod.SLACK_LAST_READ_PATH = original_path


# --- Test: poll_messages filters bot messages ---


def test_poll_messages_filters_bots(tmp_path):
    """poll_messages should filter out bot messages and messages with subtypes."""
    import urllib.request

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

    # Monkey-patch SLACK_LAST_READ_PATH
    original_path = mod.SLACK_LAST_READ_PATH
    last_read_file = tmp_path / "last-read.json"
    mod.SLACK_LAST_READ_PATH = str(last_read_file)

    # Set up initial last-read state in multi-channel format
    notifier._save_last_read_all({"C0123456789": "1.0"})

    # Mock _discover_channels to return our test channel
    notifier._discover_channels = lambda: {"orchestrator-questions": "C0123456789"}

    # Mock conversations.history response
    mock_response_data = {
        "ok": True,
        "messages": [
            {"text": "joined", "subtype": "channel_join", "ts": "1.3"},
            {"text": "status update", "bot_id": "B123", "ts": "1.2"},
            {"text": "hello", "user": "U123", "ts": "1.1"},
        ]
    }

    original_urlopen = urllib.request.urlopen

    def mock_urlopen(req, timeout=None):
        class MockResponse:
            def read(self_inner):
                return json.dumps(mock_response_data).encode("utf-8")
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, *args):
                pass
        return MockResponse()

    urllib.request.urlopen = mock_urlopen

    try:
        result = notifier.poll_messages()
        # Should return only the human message
        assert len(result) == 1
        assert result[0]["text"] == "hello"
        assert result[0]["user"] == "U123"
        # Should have channel metadata tags
        assert result[0]["_channel_name"] == "orchestrator-questions"
        assert result[0]["_channel_id"] == "C0123456789"
    finally:
        urllib.request.urlopen = original_urlopen
        mod.SLACK_LAST_READ_PATH = original_path


# --- Test: poll_messages updates last-read timestamp ---


def test_poll_messages_updates_last_read(tmp_path):
    """poll_messages should update last-read timestamp to newest message per channel."""
    import urllib.request

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

    # Monkey-patch SLACK_LAST_READ_PATH
    original_path = mod.SLACK_LAST_READ_PATH
    last_read_file = tmp_path / "last-read.json"
    mod.SLACK_LAST_READ_PATH = str(last_read_file)

    # Set up initial last-read state in multi-channel format
    notifier._save_last_read_all({"C0123456789": "1.0"})

    # Mock _discover_channels
    notifier._discover_channels = lambda: {"orchestrator-questions": "C0123456789"}

    # Mock conversations.history response (newest first)
    mock_response_data = {
        "ok": True,
        "messages": [
            {"text": "newest", "user": "U123", "ts": "1.5"},
            {"text": "older", "user": "U123", "ts": "1.2"},
        ]
    }

    original_urlopen = urllib.request.urlopen

    def mock_urlopen(req, timeout=None):
        class MockResponse:
            def read(self_inner):
                return json.dumps(mock_response_data).encode("utf-8")
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, *args):
                pass
        return MockResponse()

    urllib.request.urlopen = mock_urlopen

    try:
        result = notifier.poll_messages()
        assert len(result) == 2

        # Verify last-read was updated to newest timestamp for this channel
        all_ts = notifier._load_last_read_all()
        assert all_ts.get("C0123456789") == "1.5"
    finally:
        urllib.request.urlopen = original_urlopen
        mod.SLACK_LAST_READ_PATH = original_path


# --- Test: classify_message patterns ---


def test_classify_feature_request(tmp_path):
    """classify_message should identify 'feature:' prefix as new_feature."""
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

    classification, title, body = notifier.classify_message("feature: Add cache TTL")
    assert classification == "new_feature"
    assert title == "Add cache TTL"
    assert body == ""


def test_classify_feature_with_body(tmp_path):
    """classify_message should parse multi-line feature messages."""
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

    classification, title, body = notifier.classify_message(
        "feature: Cache TTL\nNeeds configurable expiry"
    )
    assert classification == "new_feature"
    assert title == "Cache TTL"
    assert body == "Needs configurable expiry"


def test_classify_enhancement(tmp_path):
    """classify_message should identify 'enhancement:' as new_feature."""
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

    classification, title, body = notifier.classify_message("enhancement: Better logging")
    assert classification == "new_feature"
    assert title == "Better logging"
    assert body == ""


def test_classify_defect(tmp_path):
    """classify_message should identify 'defect:' prefix as new_defect."""
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

    classification, title, body = notifier.classify_message(
        "defect: Broken import in auth"
    )
    assert classification == "new_defect"
    assert title == "Broken import in auth"
    assert body == ""


def test_classify_bug(tmp_path):
    """classify_message should identify 'bug:' prefix as new_defect."""
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

    classification, title, body = notifier.classify_message(
        "bug: NullPointerException on startup"
    )
    assert classification == "new_defect"
    assert title == "NullPointerException on startup"
    assert body == ""


def test_classify_stop(tmp_path):
    """classify_message should identify 'stop' command as control_stop."""
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

    classification, title, body = notifier.classify_message("stop")
    assert classification == "control_stop"
    assert title == "stop"
    assert body == ""


def test_classify_pause(tmp_path):
    """classify_message should identify 'pause' command as control_stop."""
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

    classification, title, body = notifier.classify_message("pause")
    assert classification == "control_stop"
    assert title == "pause"
    assert body == ""


def test_classify_skip(tmp_path):
    """classify_message should identify 'skip' command as control_skip."""
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

    classification, title, body = notifier.classify_message("skip")
    assert classification == "control_skip"
    assert title == "skip"
    assert body == ""


def test_classify_status(tmp_path):
    """classify_message should identify 'status' as info_request."""
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

    classification, title, body = notifier.classify_message("status")
    assert classification == "info_request"
    assert title == "status"
    assert body == ""


def test_classify_question_mark(tmp_path):
    """classify_message should identify messages ending with '?' as question."""
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

    classification, title, body = notifier.classify_message("how much budget is left?")
    assert classification == "question"
    # Title and body content is implementation-dependent; just verify classification


def test_classify_question_word(tmp_path):
    """classify_message should identify messages starting with question words."""
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

    classification, title, body = notifier.classify_message("what is in the backlog")
    assert classification == "question"


def test_classify_acknowledgement(tmp_path):
    """classify_message should classify generic messages as acknowledgement."""
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

    classification, title, body = notifier.classify_message("sounds good")
    assert classification == "acknowledgement"
    assert title == "sounds good"
    assert body == ""


def test_classify_empty(tmp_path):
    """classify_message should handle empty strings as acknowledgement."""
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

    classification, title, body = notifier.classify_message("")
    assert classification == "acknowledgement"
    assert title == ""
    assert body == ""


def test_classify_case_insensitive(tmp_path):
    """classify_message should perform case-insensitive matching."""
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

    # Test uppercase FEATURE
    classification, title, body = notifier.classify_message("FEATURE: Test")
    assert classification == "new_feature"
    assert title == "Test"

    # Test mixed case Bug
    classification, title, body = notifier.classify_message("Bug: something")
    assert classification == "new_defect"
    assert title == "something"


# --- Test: create_backlog_item creates feature file ---


def test_create_backlog_feature(tmp_path, monkeypatch):
    """create_backlog_item should create a numbered feature file."""
    import os

    # Create temp working directory structure
    monkeypatch.chdir(tmp_path)
    os.makedirs("docs/feature-backlog")

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

    # Create backlog item
    result = notifier.create_backlog_item(
        "feature", "Cache TTL", "Add configurable expiry", "U123", "1234.5678"
    )

    # Verify file was created
    assert result
    assert os.path.exists(result['filepath'])

    # Verify metadata
    assert result['item_number'] == 1
    assert result['filename'].startswith("1-")

    # Verify filename starts with "1-"
    filename = os.path.basename(result['filepath'])
    assert filename.startswith("1-")
    assert filename.endswith(".md")

    # Verify file content
    with open(result['filepath'], "r") as f:
        content = f.read()

    assert "# Cache TTL" in content
    assert "## Status: Open" in content
    assert "## Priority: Medium" in content
    assert "Add configurable expiry" in content
    assert "Created from Slack message" in content
    assert "by U123" in content
    assert "at 1234.5678" in content


# --- Test: create_backlog_item creates defect file ---


def test_create_backlog_defect(tmp_path, monkeypatch):
    """create_backlog_item should create a numbered defect file."""
    import os

    # Create temp working directory structure
    monkeypatch.chdir(tmp_path)
    os.makedirs("docs/defect-backlog")

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

    # Create defect item
    result = notifier.create_backlog_item(
        "defect", "Broken import", "Import fails in auth module", "U456", "2345.6789"
    )

    # Verify file was created in defect-backlog
    assert result
    assert "defect-backlog" in result['filepath']
    assert os.path.exists(result['filepath'])

    # Verify content
    with open(result['filepath'], "r") as f:
        content = f.read()

    assert "# Broken import" in content
    assert "Import fails in auth module" in content


# --- Test: create_backlog_item numbering ---


def test_create_backlog_numbering(tmp_path, monkeypatch):
    """create_backlog_item should use next available number."""
    import os

    # Create temp working directory structure
    monkeypatch.chdir(tmp_path)
    os.makedirs("docs/feature-backlog")

    # Create an existing file with number 15
    existing_file = "docs/feature-backlog/15-existing.md"
    with open(existing_file, "w") as f:
        f.write("# Existing\n")

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
    notifier._post_message = lambda payload, channel_id=None: True

    # Create new item
    result = notifier.create_backlog_item("feature", "New Feature", "", "", "")

    # Verify filename starts with "16-"
    filename = os.path.basename(result['filepath'])
    assert filename.startswith("16-")


# --- Test: process_inbound when disabled ---


def test_process_inbound_disabled(tmp_path):
    """process_inbound should be a no-op when disabled."""
    nonexistent_path = tmp_path / "nonexistent.yaml"
    notifier = SlackNotifier(config_path=str(nonexistent_path))

    # Should not raise any errors
    notifier.process_inbound()


# --- Test: process_inbound dispatches feature ---


def test_process_inbound_dispatches_feature(tmp_path, monkeypatch):
    """process_inbound should call create_backlog_item for feature messages."""
    import os

    # Create temp working directory structure
    monkeypatch.chdir(tmp_path)
    os.makedirs("docs/feature-backlog")

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

    # Monkey-patch poll_messages
    def mock_poll_messages():
        return [{"text": "feature: New feature", "user": "U1", "ts": "1.0"}]

    notifier.poll_messages = mock_poll_messages

    # Track create_backlog_item calls
    backlog_calls = []

    original_create_backlog_item = notifier.create_backlog_item

    def mock_create_backlog_item(item_type, title, body, user, ts):
        backlog_calls.append((item_type, title, body, user, ts))
        return original_create_backlog_item(item_type, title, body, user, ts)

    notifier.create_backlog_item = mock_create_backlog_item

    # Monkey-patch _post_message
    notifier._post_message = lambda payload, channel_id=None: True

    # Process inbound
    notifier.process_inbound()

    # Verify create_backlog_item was called
    assert len(backlog_calls) == 1
    assert backlog_calls[0][0] == "feature"
    assert backlog_calls[0][1] == "New feature"
    assert backlog_calls[0][3] == "U1"
    assert backlog_calls[0][4] == "1.0"


# --- Test: process_inbound dispatches stop command ---


def test_process_inbound_dispatches_stop(tmp_path):
    """process_inbound should call handle_control_command for stop messages."""
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

    # Monkey-patch poll_messages
    def mock_poll_messages():
        return [{"text": "stop", "user": "U1", "ts": "1.0"}]

    notifier.poll_messages = mock_poll_messages

    # Track handle_control_command calls
    control_calls = []

    original_handle_control_command = notifier.handle_control_command

    def mock_handle_control_command(command, classification, channel_id=None):
        control_calls.append((command, classification))
        original_handle_control_command(command, classification, channel_id=channel_id)

    notifier.handle_control_command = mock_handle_control_command

    # Monkey-patch _post_message
    notifier._post_message = lambda payload, channel_id=None: True

    # Process inbound
    notifier.process_inbound()

    # Verify handle_control_command was called
    assert len(control_calls) == 1
    assert control_calls[0][0] == "stop"
    assert control_calls[0][1] == "control_stop"


# --- Test: process_inbound error resilience ---


def test_process_inbound_error_resilience(tmp_path):
    """process_inbound should not propagate exceptions."""
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

    # Monkey-patch poll_messages to raise an exception
    def mock_poll_messages():
        raise RuntimeError("Test error")

    notifier.poll_messages = mock_poll_messages

    # Should not raise any errors
    notifier.process_inbound()


# ============================================================================
# Tests for answer_question (LLM-powered) and pipeline state gathering
# ============================================================================


def _make_notifier(tmp_path):
    """Helper to create a test-configured SlackNotifier."""
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
    return SlackNotifier(config_path=str(config_file))


# --- Test: _gather_pipeline_state with empty directories ---


def test_gather_state_empty(tmp_path, monkeypatch):
    """_gather_pipeline_state should return None sections when no files exist."""
    monkeypatch.chdir(tmp_path)
    notifier = _make_notifier(tmp_path)

    state = notifier._gather_pipeline_state()
    assert state["active_plan"] is None
    assert state["last_task"] is None
    assert state["session_cost"] is None


# --- Test: _gather_pipeline_state with populated state ---


def test_gather_state_populated(tmp_path, monkeypatch):
    """_gather_pipeline_state should read real state from disk."""
    import os

    monkeypatch.chdir(tmp_path)

    # Create a plan yaml
    plans_dir = tmp_path / ".claude" / "plans"
    plans_dir.mkdir(parents=True)
    plan_data = {
        "meta": {"name": "Test Plan"},
        "sections": [
            {
                "id": "phase-1",
                "name": "Phase 1",
                "status": "in_progress",
                "tasks": [
                    {"id": "1.1", "name": "Task A", "status": "completed"},
                    {"id": "1.2", "name": "Task B", "status": "in_progress"},
                    {"id": "1.3", "name": "Task C", "status": "pending"},
                ],
            }
        ],
    }
    with open(plans_dir / "01-test.yaml", "w") as f:
        yaml.dump(plan_data, f)

    # Create sample-plan.yaml (should be skipped)
    with open(plans_dir / "sample-plan.yaml", "w") as f:
        yaml.dump({"meta": {"name": "Sample"}, "sections": []}, f)

    # Create task-status.json
    task_status = {
        "task_id": "1.1",
        "status": "completed",
        "message": "All done",
        "timestamp": "2026-02-16T12:00:00",
    }
    with open(plans_dir / "task-status.json", "w") as f:
        json.dump(task_status, f)

    # Create backlog directories with files
    os.makedirs("docs/feature-backlog")
    Path("docs/feature-backlog/1-feat.md").write_text("# Feature")
    Path("docs/feature-backlog/2-feat2.md").write_text("# Feature 2")
    os.makedirs("docs/defect-backlog")
    Path("docs/defect-backlog/1-bug.md").write_text("# Bug")

    # Create completed directory
    os.makedirs("docs/completed-backlog/features", exist_ok=True)
    Path("docs/completed-backlog/features/1-done.md").write_text("# Done")
    os.makedirs("docs/completed-backlog/defects", exist_ok=True)

    # Create session log
    logs_dir = plans_dir / "logs"
    logs_dir.mkdir()
    session_data = {
        "session_timestamp": "2026-02-16T10:00:00",
        "total_cost_usd": 2.50,
        "work_items": [{"name": "item1"}, {"name": "item2"}],
    }
    with open(logs_dir / "pipeline-session-20260216-100000.json", "w") as f:
        json.dump(session_data, f)

    notifier = _make_notifier(tmp_path)
    state = notifier._gather_pipeline_state()

    # Active plan
    assert state["active_plan"] is not None
    assert state["active_plan"]["name"] == "Test Plan"
    assert state["active_plan"]["total"] == 3
    assert state["active_plan"]["completed"] == 1
    assert state["active_plan"]["in_progress"] == 1

    # Last task
    assert state["last_task"] is not None
    assert state["last_task"]["task_id"] == "1.1"
    assert state["last_task"]["status"] == "completed"

    # Backlog
    assert state["backlog"]["pending_features"] == 2
    assert state["backlog"]["pending_defects"] == 1

    # Completed
    assert state["completed"]["completed_features"] == 1
    assert state["completed"]["completed_defects"] == 0

    # Session cost
    assert state["session_cost"]["total_cost_usd"] == 2.50
    assert state["session_cost"]["work_items"] == 2


# --- Test: _format_state_context includes all sections ---


def test_format_state_context_populated(tmp_path, monkeypatch):
    """_format_state_context should produce plain text with all state sections."""
    notifier = SlackNotifier.__new__(SlackNotifier)
    state = {
        "active_plan": {
            "name": "Test Plan",
            "total": 5,
            "completed": 3,
            "in_progress": 1,
            "failed": 0,
        },
        "last_task": {
            "task_id": "2.1",
            "status": "completed",
            "message": "Task passed",
            "timestamp": "2026-02-16T12:00:00",
        },
        "backlog": {"pending_features": 2, "pending_defects": 1},
        "completed": {"completed_features": 5, "completed_defects": 2},
        "session_cost": {"total_cost_usd": 1.23, "work_items": 3},
    }

    result = notifier._format_state_context(state)
    assert "Test Plan" in result
    assert "3/5" in result
    assert "2.1" in result
    assert "2 features" in result
    assert "1 defects" in result
    assert "API-equivalent" in result
    assert "subscription" in result.lower()


# --- Test: _format_state_context with empty state ---


def test_format_state_context_empty():
    """_format_state_context should handle None values gracefully."""
    notifier = SlackNotifier.__new__(SlackNotifier)
    state = {
        "active_plan": None,
        "last_task": None,
        "backlog": None,
        "completed": None,
        "session_cost": None,
    }

    result = notifier._format_state_context(state)
    assert "none" in result.lower()


# --- Test: answer_question calls LLM with state context ---


def test_answer_question_calls_llm(tmp_path, monkeypatch):
    """answer_question should call Claude CLI directly and send the result."""
    import subprocess as sp

    monkeypatch.chdir(tmp_path)

    plans_dir = tmp_path / ".claude" / "plans"
    plans_dir.mkdir(parents=True)

    notifier = _make_notifier(tmp_path)

    cli_calls = []
    sent = []

    def mock_subprocess_run(*args, **kwargs):
        cli_calls.append(args[0] if args else kwargs.get("args"))
        result = sp.CompletedProcess(
            args=args[0] if args else [],
            returncode=0,
            stdout=json.dumps({
                "result": "Nope, no active work right now. Last task was 3.1."
            }),
            stderr="",
        )
        return result

    def mock_send_status(msg, level="info", channel_id=None):
        sent.append({"msg": msg, "level": level, "channel_id": channel_id})

    monkeypatch.setattr(sp, "run", mock_subprocess_run)
    notifier.send_status = mock_send_status

    notifier.answer_question("do you have any work?", channel_id="C999")

    # CLI was called with sonnet model and the question in the prompt
    assert len(cli_calls) == 1
    cmd = cli_calls[0]
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    prompt_arg = cmd[cmd.index("--print") + 1]
    assert "do you have any work?" in prompt_arg

    # LLM response was sent to Slack
    assert len(sent) == 1
    assert "no active work" in sent[0]["msg"].lower()
    assert sent[0]["channel_id"] == "C999"


# --- Test: answer_question falls back on CLI failure ---


def test_answer_question_fallback_on_llm_failure(tmp_path, monkeypatch):
    """answer_question should send raw state if CLI returns non-zero."""
    import subprocess as sp

    monkeypatch.chdir(tmp_path)

    plans_dir = tmp_path / ".claude" / "plans"
    plans_dir.mkdir(parents=True)

    notifier = _make_notifier(tmp_path)

    sent = []

    def mock_subprocess_run(*args, **kwargs):
        return sp.CompletedProcess(args=[], returncode=1, stdout="", stderr="error")

    def mock_send_status(msg, level="info", channel_id=None):
        sent.append({"msg": msg})

    monkeypatch.setattr(sp, "run", mock_subprocess_run)
    notifier.send_status = mock_send_status

    notifier.answer_question("what's happening?")

    assert len(sent) == 1
    assert "LLM returned empty" in sent[0]["msg"]


# --- Test: answer_question falls back on exception ---


def test_answer_question_fallback_on_exception(tmp_path, monkeypatch):
    """answer_question should send raw state if subprocess raises."""
    import subprocess as sp

    monkeypatch.chdir(tmp_path)

    plans_dir = tmp_path / ".claude" / "plans"
    plans_dir.mkdir(parents=True)

    notifier = _make_notifier(tmp_path)

    sent = []

    def mock_subprocess_run(*args, **kwargs):
        raise RuntimeError("connection failed")

    def mock_send_status(msg, level="info", channel_id=None):
        sent.append({"msg": msg})

    monkeypatch.setattr(sp, "run", mock_subprocess_run)
    notifier.send_status = mock_send_status

    notifier.answer_question("hello?")

    assert len(sent) == 1
    assert "LLM unavailable" in sent[0]["msg"]


# --- Test: handle_control_command info_request uses answer_question ---


def test_info_request_uses_answer_question(tmp_path, monkeypatch):
    """handle_control_command with info_request should call answer_question."""
    monkeypatch.chdir(tmp_path)

    plans_dir = tmp_path / ".claude" / "plans"
    plans_dir.mkdir(parents=True)

    notifier = _make_notifier(tmp_path)

    aq_calls = []

    def mock_answer_question(question, channel_id=None):
        aq_calls.append({"question": question, "channel_id": channel_id})

    notifier.answer_question = mock_answer_question

    notifier.handle_control_command("status", "info_request", channel_id="C888")

    assert len(aq_calls) == 1
    assert aq_calls[0]["question"] == "status"
    assert aq_calls[0]["channel_id"] == "C888"


# --- Test: QUESTION_ANSWER_PROMPT contains expected placeholders ---


def test_question_answer_prompt():
    """QUESTION_ANSWER_PROMPT should contain required placeholders."""
    prompt = mod.QUESTION_ANSWER_PROMPT
    assert "{state_context}" in prompt
    assert "{question}" in prompt
    assert "Max subscription" in prompt
    assert "API-equivalent" in prompt


# ============================================================================
# Tests for Change C: Async LLM-Powered Intake with 5 Whys
# ============================================================================

IntakeState = mod.IntakeState


# --- Test: IntakeState dataclass creation ---


def test_intake_state_creation():
    """IntakeState should initialize with correct defaults."""
    intake = IntakeState(
        channel_id="C123",
        channel_name="orchestrator-features",
        original_text="Add caching",
        user="U456",
        ts="123.456",
        item_type="feature",
    )
    assert intake.status == "analyzing"
    assert intake.analysis == ""


# --- Test: IntakeState instances are independent ---


def test_intake_state_independent_events():
    """Each IntakeState should track its own status independently."""
    intake1 = IntakeState(
        channel_id="C1", channel_name="ch1", original_text="t1",
        user="U1", ts="1.0", item_type="feature"
    )
    intake2 = IntakeState(
        channel_id="C2", channel_name="ch2", original_text="t2",
        user="U2", ts="2.0", item_type="defect"
    )
    intake1.status = "done"
    assert intake1.status == "done"
    assert intake2.status == "analyzing"


# --- Test: _parse_intake_response extracts structured fields ---


def test_parse_intake_response_structured():
    """_parse_intake_response should extract Title, Root Need, Description, 5 Whys."""
    text = (
        "Title: Implement Redis caching\n\n"
        "5 Whys:\n"
        "1. Users want faster responses\n"
        "2. API calls are slow\n"
        "3. No caching layer\n"
        "4. Architecture gap\n"
        "5. Need low-latency data access\n\n"
        "Root Need: Low-latency data access for user retention\n\n"
        "Description:\n"
        "Add a Redis caching layer to reduce API response times."
    )
    result = SlackNotifier._parse_intake_response(text)

    assert result["title"] == "Implement Redis caching"
    assert result["root_need"] == "Low-latency data access for user retention"
    assert "Redis caching layer" in result["description"]
    assert len(result["five_whys"]) == 5
    assert "faster responses" in result["five_whys"][0]


def test_parse_intake_response_unstructured():
    """_parse_intake_response should return empty fields for plain prose."""
    text = "This is just a plain analysis without any structure."
    result = SlackNotifier._parse_intake_response(text)

    assert result["title"] == ""
    assert result["root_need"] == ""
    assert result["description"] == ""
    assert result["five_whys"] == []


# --- Test: _run_intake_analysis with clear request ---


def test_intake_analysis_clear_request(tmp_path, monkeypatch):
    """_run_intake_analysis should create backlog item when request is clear."""
    import os

    monkeypatch.chdir(tmp_path)
    os.makedirs("docs/feature-backlog")

    notifier = _make_notifier(tmp_path)

    # Track calls
    created_items = []
    sent_messages = []

    def mock_create(item_type, title, body, user="", ts=""):
        created_items.append({"type": item_type, "title": title, "body": body})
        return "docs/feature-backlog/1-test.md"

    def mock_send(msg, level="info", channel_id=None):
        sent_messages.append({"msg": msg, "level": level})

    notifier.create_backlog_item = mock_create
    notifier.send_status = mock_send

    # Mock _call_claude_print to return plain-text analysis
    llm_response = (
        "Title: Add response caching\n\n"
        "5 Whys:\n"
        "1. Surface need\n"
        "2. Deeper need\n"
        "3. Core need\n"
        "4. Business need\n"
        "5. Root need\n\n"
        "Root Need: Fast page loads for user retention\n\n"
        "Description:\n"
        "Implement caching layer for API responses to reduce latency."
    )
    notifier._call_claude_print = lambda prompt, model="sonnet", timeout=120: llm_response

    intake = IntakeState(
        channel_id="C123",
        channel_name="orchestrator-features",
        original_text="Add caching to the API",
        user="U456",
        ts="100.200",
        item_type="feature",
    )
    notifier._pending_intakes[f"{intake.channel_name}:{intake.ts}"] = intake

    notifier._run_intake_analysis(intake)

    assert intake.status == "done"
    assert len(created_items) == 1
    assert created_items[0]["title"] == "Add response caching"
    assert "5 Whys Analysis" in created_items[0]["body"]
    assert "Fast page loads" in created_items[0]["body"]
    # Success notification sent
    assert any("created" in m["msg"].lower() for m in sent_messages)


# --- Test: _run_intake_analysis with unstructured LLM response ---


def test_intake_analysis_unstructured_response(tmp_path, monkeypatch):
    """_run_intake_analysis should use raw text when LLM returns no structure."""
    import os

    monkeypatch.chdir(tmp_path)
    os.makedirs("docs/defect-backlog")

    notifier = _make_notifier(tmp_path)

    sent_messages = []
    created_items = []

    def mock_create(item_type, title, body, user="", ts=""):
        created_items.append({"type": item_type, "title": title, "body": body})
        return "docs/defect-backlog/1-test.md"

    def mock_send(msg, level="info", channel_id=None):
        sent_messages.append({"msg": msg, "level": level})

    notifier.create_backlog_item = mock_create
    notifier.send_status = mock_send

    # LLM returns plain prose without structured format
    llm_response = "The app crashes because of a memory leak in the event handler."
    notifier._call_claude_print = lambda prompt, model="sonnet", timeout=120: llm_response

    intake = IntakeState(
        channel_id="C789",
        channel_name="orchestrator-defects",
        original_text="App crashes sometimes",
        user="U111",
        ts="200.300",
        item_type="defect",
    )
    notifier._pending_intakes[f"{intake.channel_name}:{intake.ts}"] = intake

    notifier._run_intake_analysis(intake)

    assert intake.status == "done"
    assert len(created_items) == 1
    # Falls back to first line of original text as title
    assert created_items[0]["title"] == "App crashes sometimes"
    # Description is the raw LLM response
    assert "memory leak" in created_items[0]["body"]
    # Notification sent
    assert any("created" in m["msg"].lower() for m in sent_messages)


# --- Test: feature message starts new intake analysis ---


def test_intake_feature_starts_analysis(tmp_path, monkeypatch):
    """process_inbound should start a new intake for each feature message."""
    import time

    notifier = _make_notifier(tmp_path)

    intake_started = []

    def mock_run_intake(intake_state):
        intake_started.append(intake_state)

    notifier._run_intake_analysis = mock_run_intake

    def mock_poll():
        return [{
            "text": "Add Redis caching please",
            "user": "U456",
            "ts": "100.300",
            "_channel_name": "orchestrator-features",
            "_channel_id": "C123",
        }]

    notifier.poll_messages = mock_poll

    notifier.process_inbound()
    time.sleep(0.1)  # Let thread start

    assert len(intake_started) == 1
    assert intake_started[0].item_type == "feature"
    assert intake_started[0].original_text == "Add Redis caching please"


# --- Test: intake thread does not block main loop ---


def test_intake_thread_nonblocking(tmp_path, monkeypatch):
    """Starting an intake should not block process_inbound."""
    import time

    notifier = _make_notifier(tmp_path)

    # Track that _run_intake_analysis was called
    intake_started = []

    def mock_run_intake(intake_state):
        intake_started.append(intake_state)
        # Simulate long-running analysis
        time.sleep(0.5)

    notifier._run_intake_analysis = mock_run_intake

    # Mock poll_messages to return a feature message
    def mock_poll():
        return [{
            "text": "Add new feature X",
            "user": "U789",
            "ts": "300.400",
            "_channel_name": "orchestrator-features",
            "_channel_id": "C555",
        }]

    notifier.poll_messages = mock_poll

    start = time.time()
    notifier.process_inbound()
    elapsed = time.time() - start

    # process_inbound should return quickly (< 0.2s) even though
    # the intake analysis takes 0.5s
    assert elapsed < 0.2
    # Give thread time to start
    time.sleep(0.1)
    assert len(intake_started) == 1


# --- Test: intake timeout creates fallback item ---


def test_intake_empty_response_creates_fallback(tmp_path, monkeypatch):
    """_run_intake_analysis should create item with raw text when LLM returns empty."""
    import os

    monkeypatch.chdir(tmp_path)
    os.makedirs("docs/feature-backlog")

    notifier = _make_notifier(tmp_path)

    created_items = []
    sent_messages = []

    def mock_create(item_type, title, body, user="", ts=""):
        created_items.append({"type": item_type, "title": title, "body": body})
        return "docs/feature-backlog/1-test.md"

    def mock_send(msg, level="info", channel_id=None):
        sent_messages.append({"msg": msg, "level": level})

    notifier.create_backlog_item = mock_create
    notifier.send_status = mock_send

    # Mock _call_claude_print to return empty (LLM failure)
    notifier._call_claude_print = lambda prompt, model="sonnet", timeout=120: ""

    intake = IntakeState(
        channel_id="C123",
        channel_name="orchestrator-features",
        original_text="Some feature\nWith details",
        user="U456",
        ts="400.500",
        item_type="feature",
    )
    notifier._pending_intakes[f"{intake.channel_name}:{intake.ts}"] = intake

    notifier._run_intake_analysis(intake)

    assert intake.status == "done"
    assert len(created_items) == 1
    # Fallback: uses first line as title
    assert created_items[0]["title"] == "Some feature"
    # Still sends confirmation
    assert any("received" in m["msg"].lower() for m in sent_messages)


# --- Test: intake constants exist ---


def test_intake_constants():
    """Verify intake-related constants are defined."""
    assert mod.INTAKE_ANALYSIS_TIMEOUT_SECONDS == 120
    assert "{item_type}" in mod.INTAKE_ANALYSIS_PROMPT
    assert "{text}" in mod.INTAKE_ANALYSIS_PROMPT


# --- Test: Background polling ---


def test_background_polling_noop_when_disabled(tmp_path):
    """start_background_polling should be a no-op when Slack is disabled."""
    config_file = tmp_path / "slack.yaml"
    config_data = {"slack": {"enabled": False}}
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))
    notifier.start_background_polling()

    assert notifier._poll_thread is None


def test_background_polling_starts_thread(tmp_path, monkeypatch):
    """start_background_polling should spawn a daemon thread that calls process_inbound."""
    import threading
    import time

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

    call_count = 0

    def mock_poll_messages():
        nonlocal call_count
        call_count += 1
        return []

    monkeypatch.setattr(notifier, "poll_messages", mock_poll_messages)
    monkeypatch.setattr(mod, "SLACK_POLL_INTERVAL_SECONDS", 0.05)

    notifier.start_background_polling()

    assert notifier._poll_thread is not None
    assert notifier._poll_thread.daemon is True
    assert notifier._poll_thread.is_alive()

    # Wait enough for at least one poll cycle
    time.sleep(0.2)

    notifier.stop_background_polling()

    assert call_count >= 1
    assert notifier._poll_thread is None


def test_background_polling_idempotent(tmp_path, monkeypatch):
    """Calling start_background_polling twice should not create a second thread."""
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
    monkeypatch.setattr(notifier, "poll_messages", lambda: [])
    monkeypatch.setattr(mod, "SLACK_POLL_INTERVAL_SECONDS", 0.05)

    notifier.start_background_polling()
    first_thread = notifier._poll_thread

    notifier.start_background_polling()
    second_thread = notifier._poll_thread

    assert first_thread is second_thread

    notifier.stop_background_polling()


def test_background_polling_stop_without_start(tmp_path):
    """stop_background_polling should be safe to call even if never started."""
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
    # Should not raise
    notifier.stop_background_polling()
    assert notifier._poll_thread is None


def test_background_polling_survives_process_inbound_error(tmp_path, monkeypatch):
    """Background polling thread should survive exceptions in process_inbound."""
    import threading

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

    call_count = 0
    second_call = threading.Event()

    def failing_poll_messages():
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            second_call.set()
        raise RuntimeError("Simulated poll failure")

    monkeypatch.setattr(notifier, "poll_messages", failing_poll_messages)
    monkeypatch.setattr(mod, "SLACK_POLL_INTERVAL_SECONDS", 0.05)

    notifier.start_background_polling()

    # Wait for the thread to make at least 2 calls (proving it survives exceptions)
    got_second = second_call.wait(timeout=5)

    assert got_second, f"Expected at least 2 calls, got {call_count}"
    assert notifier._poll_thread.is_alive()

    notifier.stop_background_polling()


# ============================================================================
# Tests for configurable channel prefix
# ============================================================================


# --- Test: default channel prefix when not configured ---


def test_default_channel_prefix(tmp_path):
    """SlackNotifier should use default prefix when channel_prefix is not set."""
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
    assert notifier._channel_prefix == "orchestrator-"


# --- Test: custom channel prefix ---


def test_custom_channel_prefix(tmp_path):
    """SlackNotifier should use custom channel_prefix from config."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "channel_id": "C0123456789",
            "channel_prefix": "myproject-",
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))
    assert notifier._channel_prefix == "myproject-"


# --- Test: channel prefix auto append dash ---


def test_channel_prefix_auto_append_dash(tmp_path):
    """SlackNotifier should append dash to channel_prefix if missing."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "channel_id": "C0123456789",
            "channel_prefix": "myproject",
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))
    assert notifier._channel_prefix == "myproject-"


# --- Test: get_channel_role with default prefix ---


def test_get_channel_role_default_prefix(tmp_path):
    """_get_channel_role should match channels with default prefix."""
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

    assert notifier._get_channel_role("orchestrator-features") == "feature"
    assert notifier._get_channel_role("orchestrator-defects") == "defect"
    assert notifier._get_channel_role("orchestrator-questions") == "question"
    assert notifier._get_channel_role("orchestrator-notifications") == "control"
    assert notifier._get_channel_role("orchestrator-unknown") == ""
    assert notifier._get_channel_role("other-channel") == ""


# --- Test: get_channel_role with custom prefix ---


def test_get_channel_role_custom_prefix(tmp_path):
    """_get_channel_role should match channels with custom prefix."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "channel_id": "C0123456789",
            "channel_prefix": "proj-",
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))

    assert notifier._get_channel_role("proj-features") == "feature"
    assert notifier._get_channel_role("proj-defects") == "defect"
    assert notifier._get_channel_role("orchestrator-features") == ""


# --- Test: SLACK_CHANNEL_ROLE_SUFFIXES constant ---


def test_slack_channel_role_suffixes_constant():
    """SLACK_CHANNEL_ROLE_SUFFIXES should have exactly 4 entries."""
    suffixes = mod.SLACK_CHANNEL_ROLE_SUFFIXES

    assert len(suffixes) == 4
    assert suffixes["features"] == "feature"
    assert suffixes["defects"] == "defect"
    assert suffixes["questions"] == "question"
    assert suffixes["notifications"] == "control"

    # Verify the old SLACK_CHANNEL_ROLES constant no longer exists
    assert getattr(mod, "SLACK_CHANNEL_ROLES", None) is None
