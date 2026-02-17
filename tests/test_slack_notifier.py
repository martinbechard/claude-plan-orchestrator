# tests/test_slack_notifier.py
# Unit tests for SlackNotifier class.
# Design ref: docs/plans/2026-02-16-13-slack-agent-communication-design.md

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
    """SlackNotifier should be enabled when config has enabled: true and webhook_url."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "webhook_url": "https://hooks.slack.com/services/TEST",
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
            "webhook_url": "https://hooks.slack.com/services/TEST",
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
            "webhook_url": "https://hooks.slack.com/services/TEST",
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
            "webhook_url": "https://hooks.slack.com/services/TEST",
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))
    result = notifier._build_status_block("msg", "unknown_level")

    # Default emoji is large_blue_circle
    assert ":large_blue_circle:" in result["blocks"][0]["text"]["text"]


# --- Test: _post_webhook called on send_status ---


def test_post_webhook_called_on_send_status(tmp_path):
    """send_status should call _post_webhook with correct payload."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "webhook_url": "https://hooks.slack.com/services/TEST",
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))

    # Monkey-patch _post_webhook to record calls
    calls = []

    def mock_post_webhook(payload):
        calls.append(payload)
        return True

    notifier._post_webhook = mock_post_webhook

    notifier.send_status("Plan started", level="info")

    assert len(calls) == 1
    assert "blocks" in calls[0]
    assert "Plan started" in calls[0]["blocks"][0]["text"]["text"]


# --- Test: send_status noop when disabled ---


def test_send_status_noop_when_disabled(tmp_path):
    """send_status should be a no-op when disabled."""
    nonexistent_path = tmp_path / "nonexistent.yaml"
    notifier = SlackNotifier(config_path=str(nonexistent_path))

    # Should not raise any errors
    notifier.send_status("test")


# --- Test: process_agent_messages with defect ---


def test_process_agent_messages_defect(tmp_path):
    """process_agent_messages should send defect messages via _post_webhook."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "webhook_url": "https://hooks.slack.com/services/TEST",
            "notify": {
                "on_defect_found": True,
            },
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))

    # Monkey-patch _post_webhook
    calls = []

    def mock_post_webhook(payload):
        calls.append(payload)
        return True

    notifier._post_webhook = mock_post_webhook

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
    """process_agent_messages should send idea messages via _post_webhook."""
    config_file = tmp_path / "slack.yaml"
    config_data = {
        "slack": {
            "enabled": True,
            "webhook_url": "https://hooks.slack.com/services/TEST",
            "notify": {
                "on_idea_found": True,
            },
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))

    # Monkey-patch _post_webhook
    calls = []

    def mock_post_webhook(payload):
        calls.append(payload)
        return True

    notifier._post_webhook = mock_post_webhook

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
            "webhook_url": "https://hooks.slack.com/services/TEST",
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))

    # Monkey-patch _post_webhook
    calls = []

    def mock_post_webhook(payload):
        calls.append(payload)
        return True

    notifier._post_webhook = mock_post_webhook

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
            "webhook_url": "https://hooks.slack.com/services/TEST",
        }
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    notifier = SlackNotifier(config_path=str(config_file))

    # Monkey-patch _post_webhook
    calls = []

    def mock_post_webhook(payload):
        calls.append(payload)
        return True

    notifier._post_webhook = mock_post_webhook

    status = {}
    notifier.process_agent_messages(status)

    assert len(calls) == 0


# --- Test: send_question returns None when disabled ---


def test_send_question_returns_none_when_disabled(tmp_path):
    """send_question should return None when disabled."""
    nonexistent_path = tmp_path / "nonexistent.yaml"
    notifier = SlackNotifier(config_path=str(nonexistent_path))

    result = notifier.send_question("Question?", ["A", "B"])
    assert result is None


# --- Test: Slack config constants exist ---


def test_slack_config_constants_exist():
    """Verify SLACK_* constants are defined in the module."""
    assert mod.SLACK_CONFIG_PATH == ".claude/slack.local.yaml"
    assert mod.SLACK_QUESTION_PATH == ".claude/slack-pending-question.json"
    assert mod.SLACK_ANSWER_PATH == ".claude/slack-answer.json"
    assert mod.SLACK_POLL_INTERVAL_SECONDS == 30


# --- Test: Slack level emoji map ---


def test_slack_level_emoji_map():
    """Verify SLACK_LEVEL_EMOJI has the expected keys and format."""
    emoji_map = mod.SLACK_LEVEL_EMOJI

    required_keys = ["info", "success", "error", "warning", "question"]
    for key in required_keys:
        assert key in emoji_map, f"Missing emoji for level: {key}"
        assert emoji_map[key].startswith(":"), f"Emoji for {key} should start with ':'"
        assert emoji_map[key].endswith(":"), f"Emoji for {key} should end with ':'"
