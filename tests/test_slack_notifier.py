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
    """_load_last_read should return '0' when no state file exists."""
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
        result = notifier._load_last_read()
        assert result == "0"
    finally:
        mod.SLACK_LAST_READ_PATH = original_path


# --- Test: save and load last-read state ---


def test_save_and_load_last_read(tmp_path):
    """_save_last_read should persist state and _load_last_read should retrieve it."""
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
        notifier._save_last_read("1234567890.123456")
        result = notifier._load_last_read()
        assert result == "1234567890.123456"

        # Verify the file contains the channel_id
        with open(last_read_file, "r") as f:
            data = json.load(f)
        assert data.get("channel_id") == "C0123456789"
        assert data.get("last_ts") == "1234567890.123456"
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
    """poll_messages should save current time on first run and return empty list."""
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
        result = notifier.poll_messages()
        assert result == []

        # Verify the last-read file was created
        assert last_read_file.exists()

        # Verify it contains a timestamp (not "0")
        with open(last_read_file, "r") as f:
            data = json.load(f)
        assert data.get("last_ts") != "0"
        assert float(data.get("last_ts")) > 0
    finally:
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

    # Set up an initial last-read state
    notifier._save_last_read("1.0")

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
            def read(self):
                return json.dumps(mock_response_data).encode("utf-8")
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        return MockResponse()

    urllib.request.urlopen = mock_urlopen

    try:
        result = notifier.poll_messages()
        # Should return only the human message
        assert len(result) == 1
        assert result[0]["text"] == "hello"
        assert result[0]["user"] == "U123"
    finally:
        urllib.request.urlopen = original_urlopen
        mod.SLACK_LAST_READ_PATH = original_path


# --- Test: poll_messages updates last-read timestamp ---


def test_poll_messages_updates_last_read(tmp_path):
    """poll_messages should update last-read timestamp to newest message."""
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

    # Set up an initial last-read state
    notifier._save_last_read("1.0")

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
            def read(self):
                return json.dumps(mock_response_data).encode("utf-8")
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        return MockResponse()

    urllib.request.urlopen = mock_urlopen

    try:
        result = notifier.poll_messages()
        assert len(result) == 2

        # Verify last-read was updated to newest timestamp
        saved_ts = notifier._load_last_read()
        assert saved_ts == "1.5"
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

    # Monkey-patch _post_message to capture calls
    calls = []

    def mock_post_message(payload):
        calls.append(payload)
        return True

    notifier._post_message = mock_post_message

    # Create backlog item
    result = notifier.create_backlog_item(
        "feature", "Cache TTL", "Add configurable expiry", "U123", "1234.5678"
    )

    # Verify file was created
    assert result != ""
    assert os.path.exists(result)

    # Verify filename starts with "1-"
    filename = os.path.basename(result)
    assert filename.startswith("1-")
    assert filename.endswith(".md")

    # Verify file content
    with open(result, "r") as f:
        content = f.read()

    assert "# Cache TTL" in content
    assert "## Status: Open" in content
    assert "## Priority: Medium" in content
    assert "Add configurable expiry" in content
    assert "Created from Slack message" in content
    assert "by U123" in content
    assert "at 1234.5678" in content

    # Verify Slack notification
    assert len(calls) == 1


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

    # Monkey-patch _post_message
    calls = []

    def mock_post_message(payload):
        calls.append(payload)
        return True

    notifier._post_message = mock_post_message

    # Create defect item
    result = notifier.create_backlog_item(
        "defect", "Broken import", "Import fails in auth module", "U456", "2345.6789"
    )

    # Verify file was created in defect-backlog
    assert result != ""
    assert "defect-backlog" in result
    assert os.path.exists(result)

    # Verify content
    with open(result, "r") as f:
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
    notifier._post_message = lambda payload: True

    # Create new item
    result = notifier.create_backlog_item("feature", "New Feature", "", "", "")

    # Verify filename starts with "16-"
    filename = os.path.basename(result)
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
    notifier._post_message = lambda payload: True

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

    def mock_handle_control_command(command, classification):
        control_calls.append((command, classification))
        original_handle_control_command(command, classification)

    notifier.handle_control_command = mock_handle_control_command

    # Monkey-patch _post_message
    notifier._post_message = lambda payload: True

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
