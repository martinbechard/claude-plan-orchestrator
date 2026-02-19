# tests/test_plan_orchestrator.py
# Unit tests for plan-orchestrator.py functions
# Design ref: docs/plans/2026-02-17-5-slack-bot-provides-truncated-unhelpful-responses-when-defect-submission-fails-validation-design.md
# Design ref: docs/plans/2026-02-17-7-pipeline-agent-commits-unrelated-working-tree-changes-design.md
# Design ref: docs/plans/2026-02-19-19-optional-step-by-step-notifications-design.md

import importlib.util
import os
import subprocess
import tempfile
import shutil
import unittest.mock
from pathlib import Path

# plan-orchestrator.py has a hyphen in the filename, so we must use importlib
# to load it as a module under a valid Python identifier.
spec = importlib.util.spec_from_file_location(
    "plan_orchestrator", "scripts/plan-orchestrator.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SlackNotifier = mod.SlackNotifier
SLACK_BLOCK_TEXT_MAX_LENGTH = mod.SLACK_BLOCK_TEXT_MAX_LENGTH
SLACK_CHANNEL_ROLE_SUFFIXES = mod.SLACK_CHANNEL_ROLE_SUFFIXES
IntakeState = mod.IntakeState
REQUIRED_FIVE_WHYS_COUNT = mod.REQUIRED_FIVE_WHYS_COUNT
git_stash_working_changes = mod.git_stash_working_changes
git_stash_pop = mod.git_stash_pop
ORCHESTRATOR_STASH_MESSAGE = mod.ORCHESTRATOR_STASH_MESSAGE
STASH_EXCLUDE_PLANS_PATHSPEC = mod.STASH_EXCLUDE_PLANS_PATHSPEC
STATUS_FILE_PATH = mod.STATUS_FILE_PATH
ensure_directories = mod.ensure_directories
parse_verification_blocks = mod.parse_verification_blocks
build_validation_prompt = mod.build_validation_prompt
TaskResult = mod.TaskResult
create_suspension_marker = mod.create_suspension_marker
read_suspension_marker = mod.read_suspension_marker
clear_suspension_marker = mod.clear_suspension_marker
is_item_suspended = mod.is_item_suspended
get_suspension_answer = mod.get_suspension_answer
find_next_task = mod.find_next_task
update_section_status = mod.update_section_status
AGENT_PERMISSION_PROFILES = mod.AGENT_PERMISSION_PROFILES
AGENT_TO_PROFILE = mod.AGENT_TO_PROFILE
build_permission_flags = mod.build_permission_flags
should_send_step_notifications = mod.should_send_step_notifications
STEP_NOTIFICATION_THRESHOLD = mod.STEP_NOTIFICATION_THRESHOLD


# --- _truncate_for_slack tests ---


def test_truncate_for_slack_short_message():
    """Short message should remain unchanged."""
    input_text = "Hello world"
    result = SlackNotifier._truncate_for_slack(input_text)
    assert result == "Hello world"


def test_truncate_for_slack_exact_limit():
    """Message exactly at limit should remain unchanged."""
    input_text = "x" * SLACK_BLOCK_TEXT_MAX_LENGTH
    result = SlackNotifier._truncate_for_slack(input_text)
    assert result == input_text
    assert len(result) == SLACK_BLOCK_TEXT_MAX_LENGTH


def test_truncate_for_slack_over_limit():
    """Message over limit should be truncated with omission indicator."""
    input_text = "x" * (SLACK_BLOCK_TEXT_MAX_LENGTH + 500)
    result = SlackNotifier._truncate_for_slack(input_text)
    assert len(result) <= SLACK_BLOCK_TEXT_MAX_LENGTH
    assert "chars omitted" in result


def test_truncate_for_slack_custom_limit():
    """Truncation should respect custom max_length parameter."""
    input_text = "x" * 200
    result = SlackNotifier._truncate_for_slack(input_text, max_length=100)
    assert len(result) <= 100
    assert "chars omitted" in result


# --- _parse_intake_response tests ---


def test_parse_intake_response_with_classification():
    """Parse response with classification field."""
    response = """Title: Fix login bug
Classification: defect - This describes a broken feature that should work
Root Need: Users need to authenticate
Description:
Login button is not responding when clicked.

5 Whys:
1. Why does the login fail? Button handler not attached.
2. Why wasn't it attached? Event listener setup was removed.
"""
    result = SlackNotifier._parse_intake_response(response)
    assert result["title"] == "Fix login bug"
    assert result["classification"] != ""
    assert "defect" in result["classification"].lower()
    assert result["root_need"] == "Users need to authenticate"
    assert "Login button is not responding" in result["description"]


def test_parse_intake_response_without_classification():
    """Parse response missing classification field."""
    response = """Title: Add dark mode
Root Need: Users want customizable themes
Description:
Implement dark mode toggle in settings.
"""
    result = SlackNotifier._parse_intake_response(response)
    assert result["title"] == "Add dark mode"
    assert result["classification"] == ""
    assert result["root_need"] == "Users want customizable themes"


# --- create_backlog_item tests ---


def test_create_backlog_item_returns_dict(tmp_path):
    """Verify create_backlog_item returns dict with expected keys."""
    # Create temporary backlog directories
    feature_dir = tmp_path / "docs" / "feature-backlog"
    defect_dir = tmp_path / "docs" / "defect-backlog"
    feature_dir.mkdir(parents=True)
    defect_dir.mkdir(parents=True)

    # Change to tmp directory to avoid creating real files
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Create a minimal SlackNotifier (disabled so it doesn't try to connect)
        nonexistent_config = tmp_path / "nonexistent-slack-config.yaml"
        notifier = SlackNotifier(config_path=str(nonexistent_config))

        # Call create_backlog_item for a defect
        result = notifier.create_backlog_item(
            item_type="defect",
            title="Test defect title",
            body="Test defect body",
            user="U123ABC",
            ts="1234567890.123456"
        )

        # Assert result has expected keys
        assert "filepath" in result
        assert "filename" in result
        assert "item_number" in result

        # Assert item_number is an int
        assert isinstance(result["item_number"], int)
        assert result["item_number"] == 1  # First item in empty backlog

        # Verify file was created
        assert os.path.exists(result["filepath"])

        # Verify filename format
        assert result["filename"].startswith("1-")
        assert result["filename"].endswith(".md")

    finally:
        os.chdir(original_cwd)


def test_create_backlog_item_increments_number(tmp_path):
    """Verify item numbers increment correctly."""
    defect_dir = tmp_path / "docs" / "defect-backlog"
    defect_dir.mkdir(parents=True)

    # Create an existing item
    (defect_dir / "1-existing-item.md").write_text("# Existing\n")

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        nonexistent_config = tmp_path / "nonexistent-slack-config.yaml"
        notifier = SlackNotifier(config_path=str(nonexistent_config))

        result = notifier.create_backlog_item(
            item_type="defect",
            title="Second item",
            body="Body"
        )

        # Should be numbered 2
        assert result["item_number"] == 2
        assert result["filename"].startswith("2-")

    finally:
        os.chdir(original_cwd)


def test_create_backlog_item_feature_type(tmp_path):
    """Verify feature items go to feature-backlog."""
    feature_dir = tmp_path / "docs" / "feature-backlog"
    feature_dir.mkdir(parents=True)

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        nonexistent_config = tmp_path / "nonexistent-slack-config.yaml"
        notifier = SlackNotifier(config_path=str(nonexistent_config))

        result = notifier.create_backlog_item(
            item_type="feature",
            title="New feature",
            body="Feature description"
        )

        # Should create in feature-backlog
        assert "feature-backlog" in result["filepath"]
        assert os.path.exists(result["filepath"])

    finally:
        os.chdir(original_cwd)


def test_create_backlog_item_invalid_type(tmp_path):
    """Verify invalid item type returns empty dict."""
    nonexistent_config = tmp_path / "nonexistent-slack-config.yaml"
    notifier = SlackNotifier(config_path=str(nonexistent_config))

    result = notifier.create_backlog_item(
        item_type="invalid",
        title="Test",
        body="Body"
    )

    # Should return empty dict
    assert result == {}


# --- _run_intake_analysis 5 Whys retry tests ---


def build_intake_response(num_whys=5, title="Test Title"):
    """Build a valid LLM response string with a given number of Whys."""
    whys = "\n".join(f"{i+1}. Why {i+1} goes here" for i in range(num_whys))
    return f"""Title: {title}
Classification: defect - test

5 Whys:
{whys}

Root Need: Test root need

Description:
Test description."""


def test_intake_no_retry_when_five_whys_complete(tmp_path):
    """Verify no retry when initial analysis has 5 Whys."""
    import unittest.mock

    # Setup directories
    defect_dir = tmp_path / "docs" / "defect-backlog"
    defect_dir.mkdir(parents=True)

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        nonexistent_config = tmp_path / "nonexistent-slack-config.yaml"
        notifier = SlackNotifier(config_path=str(nonexistent_config))

        # Mock _call_claude_print to return 5 Whys
        complete_response = build_intake_response(num_whys=5)
        with unittest.mock.patch.object(notifier, '_call_claude_print', return_value=complete_response):
            with unittest.mock.patch.object(notifier, 'create_backlog_item', return_value={"filepath": "test.md", "filename": "1-test.md", "item_number": 1}):
                with unittest.mock.patch.object(notifier, 'send_status'):
                    # Create IntakeState
                    intake = IntakeState(
                        channel_id="C123",
                        channel_name="test-channel",
                        original_text="Test defect submission",
                        user="U123",
                        ts="1234567890.123456",
                        item_type="defect",
                        analysis=None
                    )

                    # Run analysis
                    notifier._run_intake_analysis(intake)

                    # Assert _call_claude_print was called exactly once (no retry)
                    assert notifier._call_claude_print.call_count == 1

    finally:
        os.chdir(original_cwd)


def test_intake_retries_on_incomplete_whys(tmp_path):
    """Verify retry when initial analysis has fewer than 5 Whys."""
    import unittest.mock

    defect_dir = tmp_path / "docs" / "defect-backlog"
    defect_dir.mkdir(parents=True)

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        nonexistent_config = tmp_path / "nonexistent-slack-config.yaml"
        notifier = SlackNotifier(config_path=str(nonexistent_config))

        # Mock _call_claude_print: first returns 2 Whys, then 5 on retry
        incomplete_response = build_intake_response(num_whys=2)
        complete_response = build_intake_response(num_whys=5)

        with unittest.mock.patch.object(notifier, '_call_claude_print', side_effect=[incomplete_response, complete_response]):
            with unittest.mock.patch.object(notifier, 'create_backlog_item', return_value={"filepath": "test.md", "filename": "1-test.md", "item_number": 1}) as mock_create:
                with unittest.mock.patch.object(notifier, 'send_status'):
                    intake = IntakeState(
                        channel_id="C123",
                        channel_name="test-channel",
                        original_text="Test defect submission",
                        user="U123",
                        ts="1234567890.123456",
                        item_type="defect",
                        analysis=None
                    )

                    notifier._run_intake_analysis(intake)

                    # Assert _call_claude_print was called exactly twice (retry happened)
                    assert notifier._call_claude_print.call_count == 2
                    # Assert backlog item was created
                    assert mock_create.call_count == 1

    finally:
        os.chdir(original_cwd)


def test_intake_proceeds_after_failed_retry(tmp_path):
    """Verify backlog item created even when retry fails to get 5 Whys."""
    import unittest.mock

    defect_dir = tmp_path / "docs" / "defect-backlog"
    defect_dir.mkdir(parents=True)

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        nonexistent_config = tmp_path / "nonexistent-slack-config.yaml"
        notifier = SlackNotifier(config_path=str(nonexistent_config))

        # Mock _call_claude_print: both calls return 2 Whys
        incomplete_response = build_intake_response(num_whys=2)

        with unittest.mock.patch.object(notifier, '_call_claude_print', side_effect=[incomplete_response, incomplete_response]):
            with unittest.mock.patch.object(notifier, 'create_backlog_item', return_value={"filepath": "test.md", "filename": "1-test.md", "item_number": 1}) as mock_create:
                with unittest.mock.patch.object(notifier, 'send_status'):
                    intake = IntakeState(
                        channel_id="C123",
                        channel_name="test-channel",
                        original_text="Test defect submission",
                        user="U123",
                        ts="1234567890.123456",
                        item_type="defect",
                        analysis=None
                    )

                    notifier._run_intake_analysis(intake)

                    # Assert _call_claude_print was called twice
                    assert notifier._call_claude_print.call_count == 2
                    # Assert backlog item was still created (graceful degradation)
                    assert mock_create.call_count == 1

    finally:
        os.chdir(original_cwd)


def test_intake_retry_uses_better_result(tmp_path):
    """Verify retry result is used when it has more Whys than initial."""
    import unittest.mock

    defect_dir = tmp_path / "docs" / "defect-backlog"
    defect_dir.mkdir(parents=True)

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        nonexistent_config = tmp_path / "nonexistent-slack-config.yaml"
        notifier = SlackNotifier(config_path=str(nonexistent_config))

        # Mock _call_claude_print: first returns 2 Whys, retry returns 4
        first_response = build_intake_response(num_whys=2, title="Initial Title")
        retry_response = build_intake_response(num_whys=4, title="Retry Title")

        with unittest.mock.patch.object(notifier, '_call_claude_print', side_effect=[first_response, retry_response]):
            with unittest.mock.patch.object(notifier, 'create_backlog_item', return_value={"filepath": "test.md", "filename": "1-test.md", "item_number": 1}) as mock_create:
                with unittest.mock.patch.object(notifier, 'send_status'):
                    intake = IntakeState(
                        channel_id="C123",
                        channel_name="test-channel",
                        original_text="Test defect submission",
                        user="U123",
                        ts="1234567890.123456",
                        item_type="defect",
                        analysis=None
                    )

                    notifier._run_intake_analysis(intake)

                    # Assert _call_claude_print was called twice
                    assert notifier._call_claude_print.call_count == 2

                    # Check that create_backlog_item was called with data from retry
                    # The body should contain 4 Why items (from retry)
                    # create_backlog_item(item_type, title, body, user, ts)
                    call_args = mock_create.call_args.args
                    body_content = call_args[2]  # body is the 3rd positional arg

                    # Count the number of "Why" lines in the body
                    why_lines = [line for line in body_content.split('\n') if line.strip().startswith(('1.', '2.', '3.', '4.'))]
                    assert len(why_lines) >= 4  # Should have at least 4 Whys from retry

    finally:
        os.chdir(original_cwd)


# --- _run_intake_analysis acknowledgment tests ---


def test_intake_sends_immediate_ack(tmp_path):
    """Verify immediate ack is sent before LLM analysis begins."""
    import unittest.mock

    defect_dir = tmp_path / "docs" / "defect-backlog"
    defect_dir.mkdir(parents=True)

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        nonexistent_config = tmp_path / "nonexistent-slack-config.yaml"
        notifier = SlackNotifier(config_path=str(nonexistent_config))

        # Mock _call_claude_print to return complete response
        complete_response = build_intake_response(num_whys=5)
        with unittest.mock.patch.object(notifier, '_call_claude_print', return_value=complete_response):
            with unittest.mock.patch.object(notifier, 'create_backlog_item', return_value={"filepath": "test.md", "filename": "1-test.md", "item_number": 1}):
                with unittest.mock.patch.object(notifier, 'send_status') as mock_send:
                    intake = IntakeState(
                        channel_id="C123",
                        channel_name="test-channel",
                        original_text="Test feature request",
                        user="U123",
                        ts="1234567890.123456",
                        item_type="feature",
                        analysis=None
                    )

                    notifier._run_intake_analysis(intake)

                    # Verify send_status was called at least once
                    assert mock_send.call_count >= 1

                    # Check the first call contains the immediate ack
                    first_call_args = mock_send.call_args_list[0]
                    message = first_call_args[0][0]  # First positional arg
                    kwargs = first_call_args[1]

                    assert "Received your feature" in message
                    assert kwargs.get("level") == "info"
                    assert kwargs.get("channel_id") == "C123"

    finally:
        os.chdir(original_cwd)


def test_intake_sends_analysis_summary(tmp_path):
    """Verify analysis summary is sent with parsed details."""
    import unittest.mock

    defect_dir = tmp_path / "docs" / "defect-backlog"
    defect_dir.mkdir(parents=True)

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        nonexistent_config = tmp_path / "nonexistent-slack-config.yaml"
        notifier = SlackNotifier(config_path=str(nonexistent_config))

        # Mock _call_claude_print to return complete response
        complete_response = build_intake_response(num_whys=5, title="Test Feature Title")
        with unittest.mock.patch.object(notifier, '_call_claude_print', return_value=complete_response):
            with unittest.mock.patch.object(notifier, 'create_backlog_item', return_value={"filepath": "test.md", "filename": "1-test.md", "item_number": 1}):
                with unittest.mock.patch.object(notifier, 'send_status') as mock_send:
                    intake = IntakeState(
                        channel_id="C123",
                        channel_name="test-channel",
                        original_text="Test feature request",
                        user="U123",
                        ts="1234567890.123456",
                        item_type="feature",
                        analysis=None
                    )

                    notifier._run_intake_analysis(intake)

                    # Should have at least 3 calls: immediate ack, analysis summary, final success
                    assert mock_send.call_count >= 3

                    # Find the analysis summary call (contains "Here is my understanding")
                    summary_call = None
                    for call_args in mock_send.call_args_list:
                        message = call_args[0][0]
                        if "Here is my understanding" in message:
                            summary_call = call_args
                            break

                    assert summary_call is not None, "Analysis summary not found"
                    message = summary_call[0][0]
                    kwargs = summary_call[1]

                    # Verify content
                    assert "Test Feature Title" in message
                    assert "defect" in message.lower()  # classification
                    assert "Test root need" in message
                    assert kwargs.get("level") == "info"

    finally:
        os.chdir(original_cwd)


def test_intake_ack_on_empty_response(tmp_path):
    """Verify immediate ack is sent even when LLM returns empty."""
    import unittest.mock

    defect_dir = tmp_path / "docs" / "defect-backlog"
    defect_dir.mkdir(parents=True)

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        nonexistent_config = tmp_path / "nonexistent-slack-config.yaml"
        notifier = SlackNotifier(config_path=str(nonexistent_config))

        # Mock _call_claude_print to return empty string
        with unittest.mock.patch.object(notifier, '_call_claude_print', return_value=""):
            with unittest.mock.patch.object(notifier, 'create_backlog_item', return_value={"filepath": "test.md", "filename": "1-test.md", "item_number": 1}):
                with unittest.mock.patch.object(notifier, 'send_status') as mock_send:
                    intake = IntakeState(
                        channel_id="C123",
                        channel_name="test-channel",
                        original_text="Test defect submission",
                        user="U123",
                        ts="1234567890.123456",
                        item_type="defect",
                        analysis=None
                    )

                    notifier._run_intake_analysis(intake)

                    # Verify immediate ack was sent
                    first_call_args = mock_send.call_args_list[0]
                    message = first_call_args[0][0]
                    assert "Received your defect" in message

                    # Analysis summary should NOT be sent (empty response path)
                    all_messages = [call[0][0] for call in mock_send.call_args_list]
                    assert not any("Here is my understanding" in msg for msg in all_messages)

    finally:
        os.chdir(original_cwd)


def test_intake_ack_on_analysis_error(tmp_path):
    """Verify immediate ack is sent even when analysis raises exception."""
    import unittest.mock

    defect_dir = tmp_path / "docs" / "defect-backlog"
    defect_dir.mkdir(parents=True)

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        nonexistent_config = tmp_path / "nonexistent-slack-config.yaml"
        notifier = SlackNotifier(config_path=str(nonexistent_config))

        # Mock _call_claude_print to raise an exception
        with unittest.mock.patch.object(notifier, '_call_claude_print', side_effect=Exception("LLM error")):
            with unittest.mock.patch.object(notifier, 'send_status') as mock_send:
                intake = IntakeState(
                    channel_id="C123",
                    channel_name="test-channel",
                    original_text="Test defect submission",
                    user="U123",
                    ts="1234567890.123456",
                    item_type="defect",
                    analysis=None
                )

                # The exception will propagate, but we still verify immediate ack was sent
                try:
                    notifier._run_intake_analysis(intake)
                except Exception:
                    pass  # Expected

                # Verify immediate ack was sent before the error
                assert mock_send.call_count >= 1
                first_call_args = mock_send.call_args_list[0]
                message = first_call_args[0][0]
                assert "Received your defect" in message

                # Analysis summary should NOT be sent (error path)
                all_messages = [call[0][0] for call in mock_send.call_args_list]
                assert not any("Here is my understanding" in msg for msg in all_messages)

    finally:
        os.chdir(original_cwd)


# --- git stash helper tests ---


def _make_run_result(returncode=0, stdout=b"", stderr=b""):
    """Build a minimal subprocess.CompletedProcess mock result."""
    result = unittest.mock.MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _clean_tree_side_effect(cmd, **kwargs):
    """subprocess.run side_effect for a clean working tree."""
    if cmd[:2] == ["git", "diff"] and "--cached" not in cmd:
        return _make_run_result(returncode=0)
    if cmd[:3] == ["git", "diff", "--cached"]:
        return _make_run_result(returncode=0)
    if cmd[:2] == ["git", "ls-files"]:
        return _make_run_result(returncode=0, stdout=b"")
    return _make_run_result(returncode=0)


def _dirty_tree_side_effect(cmd, **kwargs):
    """subprocess.run side_effect for a dirty working tree (unstaged changes)."""
    if cmd[:2] == ["git", "diff"] and "--cached" not in cmd:
        return _make_run_result(returncode=1)
    if cmd[:3] == ["git", "diff", "--cached"]:
        return _make_run_result(returncode=0)
    if cmd[:2] == ["git", "ls-files"]:
        return _make_run_result(returncode=0, stdout=b"")
    if cmd[:3] == ["git", "stash", "push"]:
        return _make_run_result(returncode=0)
    return _make_run_result(returncode=0)


def _dirty_tree_stash_fails_side_effect(cmd, **kwargs):
    """subprocess.run side_effect: dirty tree but stash push fails."""
    if cmd[:2] == ["git", "diff"] and "--cached" not in cmd:
        return _make_run_result(returncode=1)
    if cmd[:3] == ["git", "diff", "--cached"]:
        return _make_run_result(returncode=0)
    if cmd[:2] == ["git", "ls-files"]:
        return _make_run_result(returncode=0, stdout=b"")
    if cmd[:3] == ["git", "stash", "push"]:
        return _make_run_result(returncode=1, stderr=b"stash push error")
    return _make_run_result(returncode=0)


def test_git_stash_working_changes_clean_tree():
    """Returns False and does not call stash push when tree is clean."""
    with unittest.mock.patch("subprocess.run", side_effect=_clean_tree_side_effect) as mock_run:
        result = git_stash_working_changes()

    assert result is False

    stash_push_calls = [
        call for call in mock_run.call_args_list
        if call.args[0][:3] == ["git", "stash", "push"]
    ]
    assert len(stash_push_calls) == 0


def test_git_stash_working_changes_dirty_tree():
    """Returns True and calls stash push with correct args when tree is dirty."""
    with unittest.mock.patch("subprocess.run", side_effect=_dirty_tree_side_effect) as mock_run:
        result = git_stash_working_changes()

    assert result is True

    stash_push_calls = [
        call for call in mock_run.call_args_list
        if call.args[0][:3] == ["git", "stash", "push"]
    ]
    assert len(stash_push_calls) == 1
    stash_cmd = stash_push_calls[0].args[0]
    assert "--include-untracked" in stash_cmd
    assert "-m" in stash_cmd
    assert ORCHESTRATOR_STASH_MESSAGE in stash_cmd
    assert "--" in stash_cmd
    assert "." in stash_cmd
    assert STASH_EXCLUDE_PLANS_PATHSPEC in stash_cmd


def test_git_stash_working_changes_stash_fails():
    """Returns False when tree is dirty but stash push command fails."""
    with unittest.mock.patch("subprocess.run", side_effect=_dirty_tree_stash_fails_side_effect):
        result = git_stash_working_changes()

    assert result is False


def test_git_stash_pop_success():
    """Returns True when git stash pop succeeds."""
    with unittest.mock.patch("subprocess.run", return_value=_make_run_result(returncode=0)):
        result = git_stash_pop()

    assert result is True


def test_git_stash_pop_conflict():
    """Returns False when git stash pop fails; recovery calls reset --merge before checkout."""
    with unittest.mock.patch("subprocess.run", return_value=_make_run_result(returncode=1, stderr=b"conflict")) as mock_run:
        result = git_stash_pop()

    assert result is False

    all_cmds = [call.args[0] for call in mock_run.call_args_list]
    assert ["git", "reset", "--merge"] in all_cmds
    reset_idx = all_cmds.index(["git", "reset", "--merge"])
    checkout_idx = next(i for i, c in enumerate(all_cmds) if c == ["git", "checkout", "."])
    assert reset_idx < checkout_idx


def test_git_stash_pop_conflict_calls_reset_merge():
    """Recovery sequence after pop failure is exactly: reset --merge, checkout ., stash drop."""
    def _pop_fails_side_effect(cmd, **kwargs):
        if cmd[:3] == ["git", "stash", "pop"]:
            return _make_run_result(returncode=1, stderr=b"conflict")
        return _make_run_result(returncode=0)

    with unittest.mock.patch("subprocess.run", side_effect=_pop_fails_side_effect) as mock_run:
        git_stash_pop()

    recovery_cmds = [
        call.args[0] for call in mock_run.call_args_list
        if call.args[0] == ["git", "reset", "--merge"]
        or call.args[0] == ["git", "checkout", "."]
        or call.args[0] == ["git", "stash", "drop"]
    ]
    assert recovery_cmds[0] == ["git", "reset", "--merge"]
    assert recovery_cmds[1] == ["git", "checkout", "."]
    assert recovery_cmds[2] == ["git", "stash", "drop"]


# --- get_type_channel_id tests ---


def test_get_type_channel_id_feature_returns_features_channel():
    """Verify 'feature' maps to the orchestrator-features channel."""
    notifier = SlackNotifier()
    notifier._channel_prefix = "orchestrator-"
    notifier._discovered_channels = {
        "orchestrator-features": "C_FEATURES_ID",
        "orchestrator-defects": "C_DEFECTS_ID",
        "orchestrator-notifications": "C_NOTIFY_ID",
    }
    notifier._channels_discovered_at = float("inf")  # prevent re-discovery

    result = notifier.get_type_channel_id("feature")

    assert result == "C_FEATURES_ID"


def test_get_type_channel_id_defect_returns_defects_channel():
    """Verify 'defect' maps to the orchestrator-defects channel."""
    notifier = SlackNotifier()
    notifier._channel_prefix = "orchestrator-"
    notifier._discovered_channels = {
        "orchestrator-features": "C_FEATURES_ID",
        "orchestrator-defects": "C_DEFECTS_ID",
        "orchestrator-notifications": "C_NOTIFY_ID",
    }
    notifier._channels_discovered_at = float("inf")

    result = notifier.get_type_channel_id("defect")

    assert result == "C_DEFECTS_ID"


def test_get_type_channel_id_unknown_type_returns_empty():
    """Verify an unrecognized item_type returns empty string."""
    notifier = SlackNotifier()

    result = notifier.get_type_channel_id("unknown")

    assert result == ""


def test_get_type_channel_id_channel_not_in_discovered_returns_empty():
    """Verify empty string returned when channel is not in discovered channels."""
    notifier = SlackNotifier()
    notifier._channel_prefix = "orchestrator-"

    # Mock _discover_channels to return an empty dict so no real API call is made.
    # An empty dict is falsy, so the cache guard wouldn't prevent the API call
    # without this mock.
    with unittest.mock.patch.object(notifier, '_discover_channels', return_value={}):
        result = notifier.get_type_channel_id("feature")

    assert result == ""


def test_get_type_channel_id_custom_prefix():
    """Verify custom channel prefix is used when building the channel name."""
    notifier = SlackNotifier()
    notifier._channel_prefix = "myteam-"
    notifier._discovered_channels = {
        "myteam-features": "C_CUSTOM_FEATURES",
    }
    notifier._channels_discovered_at = float("inf")

    result = notifier.get_type_channel_id("feature")

    assert result == "C_CUSTOM_FEATURES"


def test_slack_channel_role_suffixes_includes_reports():
    """Verify 'reports' key maps to 'analysis' in SLACK_CHANNEL_ROLE_SUFFIXES."""
    assert "reports" in SLACK_CHANNEL_ROLE_SUFFIXES
    assert SLACK_CHANNEL_ROLE_SUFFIXES["reports"] == "analysis"


def test_get_type_channel_id_analysis():
    """Verify 'analysis' item type resolves to the orchestrator-reports channel ID."""
    notifier = SlackNotifier()
    notifier._channel_prefix = "orchestrator-"

    with unittest.mock.patch.object(
        notifier,
        '_discover_channels',
        return_value={"orchestrator-reports": "C_REPORTS_ID"},
    ):
        result = notifier.get_type_channel_id("analysis")

    assert result == "C_REPORTS_ID"


def test_get_type_channel_id_unknown_type():
    """Verify an unrecognized item type returns empty string without making an API call."""
    notifier = SlackNotifier()

    result = notifier.get_type_channel_id("unknown")

    assert result == ""


def test_stash_pop_discards_task_status_json(tmp_path, monkeypatch):
    """Regression: git_stash_pop() succeeds when task-status.json is present in working tree.

    Reproduces the defect where stash pop failed with a merge conflict because
    task-status.json was written by the orchestrator after the stash push, leaving
    an uncommitted copy in the working tree when git stash pop ran.
    """
    # 1. Create a temporary git repository
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True)

    # 2. Create the .claude/plans/ directory inside the tmp repo
    plans_dir = tmp_path / ".claude" / "plans"
    plans_dir.mkdir(parents=True)

    # 3. Create an initial commit with a sentinel file so the repo is not empty
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("initial")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), check=True)

    # 4. Create a file that will be stashed (simulates user work-in-progress)
    wip = tmp_path / "work.txt"
    wip.write_text("wip")
    subprocess.run(["git", "add", "work.txt"], cwd=str(tmp_path), check=True)

    # 5. Create the stash (with the wip file)
    subprocess.run(
        ["git", "stash", "push", "--include-untracked", "-m", ORCHESTRATOR_STASH_MESSAGE],
        cwd=str(tmp_path), check=True
    )

    # 6. Write task-status.json to simulate the orchestrator writing it after task completion.
    #    The stash may have removed the plans directory, so recreate it before writing.
    #    This is the file that triggers the merge conflict bug.
    status_file = tmp_path / ".claude" / "plans" / "task-status.json"
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text('{"status": "completed"}')

    # 7. Monkeypatch mod.STATUS_FILE_PATH so git_stash_pop() uses the correct path
    monkeypatch.setattr(mod, "STATUS_FILE_PATH", str(status_file))

    # 8. Change the working directory to tmp_path for git operations
    monkeypatch.chdir(tmp_path)

    # 9. Call git_stash_pop() and assert it returns True (success)
    result = mod.git_stash_pop()
    assert result is True, "git_stash_pop() should succeed even with task-status.json present"

    # 10. Assert the wip file was restored (confirming the stash pop applied correctly)
    assert (tmp_path / "work.txt").exists(), "Stashed WIP file should be restored"


# --- ensure_directories tests ---


def test_ensure_directories_creates_missing_dirs(tmp_path, monkeypatch):
    """Verify ensure_directories() creates all directories listed in REQUIRED_DIRS."""
    test_dirs = [
        str(tmp_path / "dir-a"),
        str(tmp_path / "nested" / "dir-b"),
        str(tmp_path / "dir-c"),
    ]
    monkeypatch.setattr(mod, "REQUIRED_DIRS", test_dirs)

    ensure_directories()

    for d in test_dirs:
        assert os.path.isdir(d), f"Expected directory to be created: {d}"


def test_ensure_directories_logs_created_dirs(tmp_path, monkeypatch, capsys):
    """Verify ensure_directories() prints an [INIT] message for each created directory."""
    test_dirs = [
        str(tmp_path / "log-dir-a"),
        str(tmp_path / "log-dir-b"),
    ]
    monkeypatch.setattr(mod, "REQUIRED_DIRS", test_dirs)

    ensure_directories()

    captured = capsys.readouterr()
    assert "[INIT] Created missing directory:" in captured.out
    for d in test_dirs:
        assert d in captured.out


def test_ensure_directories_silent_when_dirs_exist(tmp_path, monkeypatch, capsys):
    """Verify ensure_directories() produces no output when all directories already exist."""
    test_dirs = [
        str(tmp_path / "pre-existing-a"),
        str(tmp_path / "pre-existing-b"),
    ]
    for d in test_dirs:
        os.makedirs(d, exist_ok=True)

    monkeypatch.setattr(mod, "REQUIRED_DIRS", test_dirs)

    ensure_directories()

    captured = capsys.readouterr()
    assert "[INIT]" not in captured.out


# --- parse_verification_blocks tests ---

_SINGLE_TESTABLE_SPEC = """
## Feature

Some feature description.

### Verification

**Type:** Testable
**Test file(s):** tests/DG01-test.spec.ts
**Status:** Pass

**Scenario:** some description
- Route: /admin/diagnostics
- Steps: Sign in as admin
"""

_TWO_BLOCK_SPEC = """
### Verification

**Type:** Testable
**Test file(s):** tests/DG01-test.spec.ts
**Status:** Pass

**Scenario:** First testable block

### Verification

**Type:** Non-E2E
**Test file(s):** N/A
**Status:** Pass

**Scenario:** Second non-e2e block
"""

_MULTI_FILE_SPEC = """
### Verification

**Type:** Testable
**Test file(s):** tests/a.spec.ts, tests/b.spec.ts
**Status:** Pass

**Scenario:** Multi file scenario
"""

_BLOCKED_SPEC = """
### Verification

**Type:** Blocked
**Test file(s):** N/A
**Status:** Missing

**Scenario:** No UI exists yet
"""

_MISSING_FIELDS_SPEC = """
### Verification

**Type:** Testable
"""


def test_parse_verification_blocks_single_testable():
    """Single Testable block is parsed into one dict with correct fields."""
    result = parse_verification_blocks(_SINGLE_TESTABLE_SPEC)

    assert len(result) == 1
    block = result[0]
    assert block["type"] == "Testable"
    assert block["test_files"] == ["tests/DG01-test.spec.ts"]
    assert block["status"] == "Pass"
    assert "some description" in block["scenario"]


def test_parse_verification_blocks_multiple_blocks():
    """Two ### Verification blocks produce two dicts with correct types."""
    result = parse_verification_blocks(_TWO_BLOCK_SPEC)

    assert len(result) == 2
    assert result[0]["type"] == "Testable"
    assert result[1]["type"] == "Non-E2E"


def test_parse_verification_blocks_no_blocks():
    """Spec with no ### Verification heading returns an empty list."""
    content = "## Overview\n\nNo verification blocks here.\n"
    result = parse_verification_blocks(content)

    assert result == []


def test_parse_verification_blocks_multiple_test_files():
    """Test file(s) field with comma-separated values is split into a list."""
    result = parse_verification_blocks(_MULTI_FILE_SPEC)

    assert len(result) == 1
    assert result[0]["test_files"] == ["tests/a.spec.ts", "tests/b.spec.ts"]


def test_parse_verification_blocks_blocked_type():
    """Block with Type: Blocked is returned with type='Blocked'."""
    result = parse_verification_blocks(_BLOCKED_SPEC)

    assert len(result) == 1
    assert result[0]["type"] == "Blocked"


def test_parse_verification_blocks_missing_fields():
    """Block with only Type field (missing others) is silently skipped."""
    result = parse_verification_blocks(_MISSING_FIELDS_SPEC)

    assert result == []


# --- build_validation_prompt tests ---


def _make_minimal_task_result() -> "TaskResult":
    """Return a minimal TaskResult for use in build_validation_prompt tests."""
    return TaskResult(success=True, message="Task completed", duration_seconds=5.0)


def test_build_validation_prompt_includes_e2e_command(monkeypatch):
    """E2E command appears in the Commands section of the prompt."""
    monkeypatch.setattr(mod, "E2E_COMMAND", "npx playwright test")

    task = {"id": "1.1", "name": "Test task", "description": "A task"}
    section = {"id": "phase-1", "name": "Phase 1"}
    task_result = _make_minimal_task_result()

    result = build_validation_prompt(task, section, task_result, "validator")

    assert "npx playwright test" in result


def test_build_validation_prompt_includes_source_item_when_plan_provided(monkeypatch):
    """Work item path is included in the prompt when a plan dict with meta.source_item is supplied."""
    task = {"id": "1.1", "name": "Test task", "description": "A task"}
    section = {"id": "phase-1", "name": "Phase 1"}
    task_result = _make_minimal_task_result()
    plan = {"meta": {"source_item": "docs/feature-backlog/42-my-feature.md"}}

    result = build_validation_prompt(task, section, task_result, "validator", plan=plan)

    assert "docs/feature-backlog/42-my-feature.md" in result


def test_build_validation_prompt_still_has_standard_checks(monkeypatch):
    """Standard build/test checks and verdict format remain when spec context is added."""
    monkeypatch.setattr(mod, "BUILD_COMMAND", "pnpm run build")
    monkeypatch.setattr(mod, "TEST_COMMAND", "pnpm test")

    task = {"id": "1.1", "name": "Test task", "description": "A task"}
    section = {"id": "phase-1", "name": "Phase 1"}
    task_result = _make_minimal_task_result()

    result = build_validation_prompt(task, section, task_result, "validator")

    assert "pnpm run build" in result
    assert "pnpm test" in result
    assert "Verdict: PASS" in result


# --- suspension marker tests ---

_SUSPENSION_SLUG = "test-item-slug"
_SUSPENSION_ITEM_TYPE = "defect"
_SUSPENSION_ITEM_PATH = "docs/defect-backlog/1-test.md"
_SUSPENSION_PLAN_PATH = ".claude/plans/1-test.yaml"
_SUSPENSION_TASK_ID = "2.1"
_SUSPENSION_QUESTION = "Which approach should we use?"
_SUSPENSION_QUESTION_CONTEXT = "Context about the question"


def _make_suspension_marker_dict(suspended_at: str, answer: str = "") -> dict:
    """Build a minimal suspension marker dict for test setup."""
    return {
        "slug": _SUSPENSION_SLUG,
        "item_type": _SUSPENSION_ITEM_TYPE,
        "item_path": _SUSPENSION_ITEM_PATH,
        "plan_path": _SUSPENSION_PLAN_PATH,
        "task_id": _SUSPENSION_TASK_ID,
        "question": _SUSPENSION_QUESTION,
        "question_context": _SUSPENSION_QUESTION_CONTEXT,
        "suspended_at": suspended_at,
        "timeout_minutes": 1440,
        "slack_thread_ts": "",
        "slack_channel_id": "",
        "answer": answer,
    }


def test_create_suspension_marker(tmp_path, monkeypatch):
    """Marker file is created with all required fields and a valid ISO timestamp."""
    import json as json_mod
    from datetime import datetime

    monkeypatch.setattr(mod, "SUSPENDED_DIR", str(tmp_path))

    marker_path = create_suspension_marker(
        slug=_SUSPENSION_SLUG,
        item_type=_SUSPENSION_ITEM_TYPE,
        item_path=_SUSPENSION_ITEM_PATH,
        plan_path=_SUSPENSION_PLAN_PATH,
        task_id=_SUSPENSION_TASK_ID,
        question=_SUSPENSION_QUESTION,
        question_context=_SUSPENSION_QUESTION_CONTEXT,
    )

    expected_path = tmp_path / f"{_SUSPENSION_SLUG}.json"
    assert expected_path.exists(), "Marker file should be created"
    assert marker_path == str(expected_path)

    data = json_mod.loads(expected_path.read_text())
    assert data["slug"] == _SUSPENSION_SLUG
    assert data["item_type"] == _SUSPENSION_ITEM_TYPE
    assert data["item_path"] == _SUSPENSION_ITEM_PATH
    assert data["plan_path"] == _SUSPENSION_PLAN_PATH
    assert data["task_id"] == _SUSPENSION_TASK_ID
    assert data["question"] == _SUSPENSION_QUESTION
    assert data["question_context"] == _SUSPENSION_QUESTION_CONTEXT
    assert data["answer"] == ""

    # suspended_at must be a valid ISO timestamp
    parsed = datetime.fromisoformat(data["suspended_at"])
    assert parsed is not None


def test_read_suspension_marker_exists(tmp_path, monkeypatch):
    """Returns the marker dict when the marker file is present."""
    import json as json_mod
    from datetime import datetime, timezone

    monkeypatch.setattr(mod, "SUSPENDED_DIR", str(tmp_path))

    suspended_at = datetime.now(tz=timezone.utc).isoformat()
    marker = _make_suspension_marker_dict(suspended_at=suspended_at)
    marker_path = tmp_path / f"{_SUSPENSION_SLUG}.json"
    marker_path.write_text(json_mod.dumps(marker))

    result = read_suspension_marker(_SUSPENSION_SLUG)

    assert result is not None
    assert result["slug"] == _SUSPENSION_SLUG
    assert result["item_type"] == _SUSPENSION_ITEM_TYPE
    assert result["suspended_at"] == suspended_at


def test_read_suspension_marker_not_found(tmp_path, monkeypatch):
    """Returns None when no marker file exists for the given slug."""
    monkeypatch.setattr(mod, "SUSPENDED_DIR", str(tmp_path))

    result = read_suspension_marker("nonexistent-slug")

    assert result is None


def test_clear_suspension_marker(tmp_path, monkeypatch):
    """Returns True and removes the marker file."""
    import json as json_mod
    from datetime import datetime, timezone

    monkeypatch.setattr(mod, "SUSPENDED_DIR", str(tmp_path))

    suspended_at = datetime.now(tz=timezone.utc).isoformat()
    marker = _make_suspension_marker_dict(suspended_at=suspended_at)
    marker_path = tmp_path / f"{_SUSPENSION_SLUG}.json"
    marker_path.write_text(json_mod.dumps(marker))

    result = clear_suspension_marker(_SUSPENSION_SLUG)

    assert result is True
    assert not marker_path.exists(), "Marker file should be removed"


def test_is_item_suspended_active(tmp_path, monkeypatch):
    """Returns True when a marker exists and has not timed out."""
    import json as json_mod
    from datetime import datetime, timezone

    monkeypatch.setattr(mod, "SUSPENDED_DIR", str(tmp_path))

    suspended_at = datetime.now(tz=timezone.utc).isoformat()
    marker = _make_suspension_marker_dict(suspended_at=suspended_at)
    marker_path = tmp_path / f"{_SUSPENSION_SLUG}.json"
    marker_path.write_text(json_mod.dumps(marker))

    result = is_item_suspended(_SUSPENSION_SLUG)

    assert result is True
    assert marker_path.exists(), "Marker file should not be removed for active suspension"


def test_is_item_suspended_timed_out(tmp_path, monkeypatch):
    """Returns False and cleans up the marker when the suspension has timed out."""
    import json as json_mod
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr(mod, "SUSPENDED_DIR", str(tmp_path))

    past_time = (datetime.now(tz=timezone.utc) - timedelta(hours=25)).isoformat()
    marker = _make_suspension_marker_dict(suspended_at=past_time)
    marker["timeout_minutes"] = 1
    marker_path = tmp_path / f"{_SUSPENSION_SLUG}.json"
    marker_path.write_text(json_mod.dumps(marker))

    result = is_item_suspended(_SUSPENSION_SLUG)

    assert result is False
    assert not marker_path.exists(), "Timed-out marker file should be cleaned up"


def test_get_suspension_answer_present(tmp_path, monkeypatch):
    """Returns the answer string when the marker contains a non-empty answer."""
    import json as json_mod
    from datetime import datetime, timezone

    monkeypatch.setattr(mod, "SUSPENDED_DIR", str(tmp_path))

    suspended_at = datetime.now(tz=timezone.utc).isoformat()
    answer_text = "Use approach B, it is simpler."
    marker = _make_suspension_marker_dict(suspended_at=suspended_at, answer=answer_text)
    marker_path = tmp_path / f"{_SUSPENSION_SLUG}.json"
    marker_path.write_text(json_mod.dumps(marker))

    result = get_suspension_answer(_SUSPENSION_SLUG)

    assert result == answer_text


def test_get_suspension_answer_absent(tmp_path, monkeypatch):
    """Returns None when the marker's answer field is empty."""
    import json as json_mod
    from datetime import datetime, timezone

    monkeypatch.setattr(mod, "SUSPENDED_DIR", str(tmp_path))

    suspended_at = datetime.now(tz=timezone.utc).isoformat()
    marker = _make_suspension_marker_dict(suspended_at=suspended_at, answer="")
    marker_path = tmp_path / f"{_SUSPENSION_SLUG}.json"
    marker_path.write_text(json_mod.dumps(marker))

    result = get_suspension_answer(_SUSPENSION_SLUG)

    assert result is None


# --- find_next_task suspended status tests ---


def _make_plan_with_tasks(task_dicts: list) -> dict:
    """Build a minimal plan dict with a single section containing the given tasks."""
    return {
        "sections": [
            {
                "id": "phase-1",
                "name": "Phase 1",
                "status": "in_progress",
                "tasks": task_dicts,
            }
        ]
    }


def test_find_next_task_skips_suspended():
    """find_next_task() skips suspended tasks and returns the next pending task."""
    tasks = [
        {"id": "1.1", "name": "Suspended task", "status": "suspended"},
        {"id": "1.2", "name": "Pending task", "status": "pending"},
    ]
    plan = _make_plan_with_tasks(tasks)

    result = find_next_task(plan)

    assert result is not None, "Should find the pending task"
    section, task = result
    assert task["id"] == "1.2", "Should skip the suspended task and return the pending one"
    assert task["status"] == "pending"


def test_find_next_task_all_suspended():
    """find_next_task() returns None when all tasks are suspended."""
    tasks = [
        {"id": "1.1", "name": "First suspended", "status": "suspended"},
        {"id": "1.2", "name": "Second suspended", "status": "suspended"},
    ]
    plan = _make_plan_with_tasks(tasks)

    result = find_next_task(plan)

    assert result is None, "Should return None when no actionable tasks remain"


def test_section_status_with_suspended_task():
    """update_section_status() sets in_progress when a completed and suspended task coexist."""
    section = {
        "id": "phase-1",
        "name": "Phase 1",
        "status": "in_progress",
        "tasks": [
            {"id": "1.1", "name": "Done task", "status": "completed"},
            {"id": "1.2", "name": "Suspended task", "status": "suspended"},
        ],
    }

    update_section_status(section)

    assert section["status"] == "in_progress", (
        "Section should be in_progress when a suspended task is present, not completed"
    )


# --- permission profile tests ---

EXPECTED_PROFILE_COUNT = 4
EXPECTED_AGENT_COUNT = 15


def test_permission_profiles_exist():
    """AGENT_PERMISSION_PROFILES has exactly 4 profiles, each with required keys."""
    assert len(AGENT_PERMISSION_PROFILES) == EXPECTED_PROFILE_COUNT
    for profile_name in ("READ_ONLY", "WRITE", "VERIFICATION", "DESIGN"):
        assert profile_name in AGENT_PERMISSION_PROFILES
        profile = AGENT_PERMISSION_PROFILES[profile_name]
        assert "tools" in profile
        assert "description" in profile


def test_agent_to_profile_mapping():
    """AGENT_TO_PROFILE maps exactly 15 agents with correct profile assignments."""
    assert len(AGENT_TO_PROFILE) == EXPECTED_AGENT_COUNT
    assert AGENT_TO_PROFILE["code-reviewer"] == "READ_ONLY"
    assert AGENT_TO_PROFILE["coder"] == "WRITE"
    assert AGENT_TO_PROFILE["validator"] == "VERIFICATION"
    assert AGENT_TO_PROFILE["planner"] == "DESIGN"


def test_build_permission_flags_read_only_agent():
    """READ_ONLY agent gets --allowedTools with Read but not Write or Edit."""
    result = build_permission_flags("code-reviewer")

    assert "--allowedTools" in result
    assert "Read" in result
    assert "--add-dir" in result
    assert "--dangerously-skip-permissions" not in result
    assert "Write" not in result
    assert "Edit" not in result


def test_build_permission_flags_write_agent():
    """WRITE agent gets --allowedTools including Write and Edit."""
    result = build_permission_flags("coder")

    assert "--allowedTools" in result
    assert "Write" in result
    assert "Edit" in result


def test_build_permission_flags_unknown_agent():
    """Unknown agent falls back to the WRITE profile (most permissive)."""
    result = build_permission_flags("unknown-agent")

    assert "Write" in result
    assert "--allowedTools" in result


def test_build_permission_flags_sandbox_disabled(monkeypatch):
    """When SANDBOX_ENABLED is False, only --dangerously-skip-permissions is returned."""
    monkeypatch.setattr(mod, "SANDBOX_ENABLED", False)

    result = build_permission_flags("code-reviewer")

    assert result == ["--dangerously-skip-permissions"]


def test_build_permission_flags_project_scoping():
    """--add-dir is followed by the current working directory."""
    result = build_permission_flags("coder")

    assert "--add-dir" in result
    idx = result.index("--add-dir")
    assert result[idx + 1] == os.getcwd()


# --- should_send_step_notifications() tests ---


def _make_plan_with_task_count(task_count: int, override: "bool | None" = None) -> dict:
    """Build a minimal plan dict with the given total task count across one section."""
    meta: dict = {}
    if override is not None:
        meta["step_notifications"] = override
    tasks = [{"id": str(i), "name": f"Task {i}", "status": "pending"} for i in range(task_count)]
    return {
        "meta": meta,
        "sections": [
            {"id": "phase-1", "name": "Phase 1", "status": "pending", "tasks": tasks}
        ],
    }


def test_should_send_step_notifications_small_plan():
    """Plan with 5 tasks (below threshold) returns False."""
    plan = _make_plan_with_task_count(5)
    assert should_send_step_notifications(plan) is False


def test_should_send_step_notifications_large_plan():
    """Plan with 8 tasks (above threshold) returns True."""
    plan = _make_plan_with_task_count(8)
    assert should_send_step_notifications(plan) is True


def test_should_send_step_notifications_threshold_boundary():
    """Plan with exactly 6 tasks returns False; 7 tasks returns True."""
    plan_at_threshold = _make_plan_with_task_count(STEP_NOTIFICATION_THRESHOLD)
    plan_one_above = _make_plan_with_task_count(STEP_NOTIFICATION_THRESHOLD + 1)
    assert should_send_step_notifications(plan_at_threshold) is False
    assert should_send_step_notifications(plan_one_above) is True


def test_should_send_step_notifications_override_true():
    """Plan with 3 tasks but meta.step_notifications=True returns True."""
    plan = _make_plan_with_task_count(3, override=True)
    assert should_send_step_notifications(plan) is True


def test_should_send_step_notifications_override_false():
    """Plan with 10 tasks but meta.step_notifications=False returns False."""
    plan = _make_plan_with_task_count(10, override=False)
    assert should_send_step_notifications(plan) is False


def test_step_notification_threshold_constant():
    """STEP_NOTIFICATION_THRESHOLD equals 6."""
    assert STEP_NOTIFICATION_THRESHOLD == 6
