# tests/test_plan_orchestrator.py
# Unit tests for plan-orchestrator.py functions
# Design ref: docs/plans/2026-02-17-5-slack-bot-provides-truncated-unhelpful-responses-when-defect-submission-fails-validation-design.md
# Design ref: docs/plans/2026-02-17-7-pipeline-agent-commits-unrelated-working-tree-changes-design.md

import importlib.util
import os
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
IntakeState = mod.IntakeState
REQUIRED_FIVE_WHYS_COUNT = mod.REQUIRED_FIVE_WHYS_COUNT
git_stash_working_changes = mod.git_stash_working_changes
git_stash_pop = mod.git_stash_pop
ORCHESTRATOR_STASH_MESSAGE = mod.ORCHESTRATOR_STASH_MESSAGE


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
    """Returns False when git stash pop fails (e.g. merge conflict)."""
    with unittest.mock.patch("subprocess.run", return_value=_make_run_result(returncode=1, stderr=b"conflict")):
        result = git_stash_pop()

    assert result is False
