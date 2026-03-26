# tests/langgraph/slack/test_suspension.py
# Unit tests for langgraph_pipeline.slack.suspension module.
# Design: docs/plans/2026-02-26-03-extract-slack-modules-design.md

"""Unit tests for SlackSuspension: question flows, suspension reply polling,
intake analysis, and _parse_intake_response. All Slack API calls and
filesystem operations are mocked."""

import json
import os
import threading
from io import BytesIO
from unittest.mock import MagicMock, call, mock_open, patch

import pytest

from langgraph_pipeline.shared.claude_cli import ClaudeResult
from langgraph_pipeline.slack.suspension import (
    INTAKE_ACK_TEMPLATE,
    INTAKE_ANALYSIS_TIMEOUT_SECONDS,
    INTAKE_CLARIFICATION_TEMPLATE,
    INTAKE_CLARITY_THRESHOLD,
    QA_HISTORY_DEFAULT_MAX_TURNS,
    REQUIRED_FIVE_WHYS_COUNT,
    SLACK_ANSWER_PATH,
    SLACK_LLM_MODEL,
    SLACK_QUESTION_PATH,
    SLACK_THREAD_REPLIES_LIMIT,
    SUSPENDED_DIR,
    IntakeState,
    SlackSuspension,
    SuspensionCallbacks,
    _format_item_ref,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_suspension(
    bot_token: str = "xoxb-test",
    question_config: dict | None = None,
    callbacks: SuspensionCallbacks | None = None,
    qa_history_enabled: bool = True,
    qa_history_max_turns: int = QA_HISTORY_DEFAULT_MAX_TURNS,
) -> SlackSuspension:
    """Return a SlackSuspension ready for testing."""
    return SlackSuspension(
        bot_token=bot_token,
        question_config=question_config or {},
        callbacks=callbacks,
        qa_history_enabled=qa_history_enabled,
        qa_history_max_turns=qa_history_max_turns,
    )


def _make_callbacks(**kwargs) -> SuspensionCallbacks:
    """Build a SuspensionCallbacks with sensible MagicMock defaults."""
    defaults: dict = {
        "post_message": MagicMock(return_value=True),
        "post_message_ts": MagicMock(return_value="1700000000.000001"),
        "build_block": MagicMock(return_value={"blocks": []}),
        "truncate": MagicMock(side_effect=lambda text, max_length=2900: text),
        "send_status": MagicMock(),
        "get_type_channel": MagicMock(return_value="C999"),
        "sign_text": MagicMock(side_effect=lambda t: t),
        "as_role": None,
        "ensure_socket_mode": MagicMock(return_value=False),
        "should_notify": MagicMock(return_value=True),
        "call_claude": MagicMock(return_value=ClaudeResult(text="", failure_reason=None)),
        "probe_quota": MagicMock(return_value=True),
        "gather_state": MagicMock(return_value={}),
        "format_state": MagicMock(return_value="state_context"),
        "create_backlog": MagicMock(return_value={"item_number": 1, "filename": "01-item.md", "filepath": "/tmp/01-item.md"}),
        "check_intake_rate": MagicMock(return_value=False),
        "record_intake": MagicMock(),
        "intake_lock": threading.Lock(),
        "pending_intakes": {},
        "rag": None,
    }
    defaults.update(kwargs)
    return SuspensionCallbacks(**defaults)


def _api_response(ok: bool = True, **extra) -> BytesIO:
    """Fake urllib response body."""
    return BytesIO(json.dumps({"ok": ok, **extra}).encode())


def _make_intake(
    item_type: str = "feature",
    original_text: str = "Add dark mode support",
    ts: str = "1700000000.000001",
    channel_id: str = "C123",
    channel_name: str = "orchestrator-features",
) -> IntakeState:
    """Return a minimal IntakeState for testing."""
    return IntakeState(
        channel_id=channel_id,
        channel_name=channel_name,
        original_text=original_text,
        user="U001",
        ts=ts,
        item_type=item_type,
    )


# ── IntakeState ───────────────────────────────────────────────────────────────


class TestIntakeState:
    def test_default_status(self):
        intake = _make_intake()
        assert intake.status == "analyzing"

    def test_default_analysis(self):
        intake = _make_intake()
        assert intake.analysis == ""

    def test_fields(self):
        intake = _make_intake(item_type="defect", ts="1700000001.000000")
        assert intake.item_type == "defect"
        assert intake.ts == "1700000001.000000"

    def test_status_mutation(self):
        intake = _make_intake()
        intake.status = "done"
        assert intake.status == "done"


# ── SuspensionCallbacks ───────────────────────────────────────────────────────


class TestSuspensionCallbacks:
    def test_all_fields_default_none(self):
        cb = SuspensionCallbacks()
        assert cb.post_message is None
        assert cb.call_claude is None
        assert cb.probe_quota is None
        assert cb.intake_lock is None
        assert cb.pending_intakes is None
        assert cb.rag is None

    def test_fields_set(self):
        fn = MagicMock()
        cb = SuspensionCallbacks(post_message=fn)
        assert cb.post_message is fn


# ── _format_item_ref ──────────────────────────────────────────────────────────


class TestFormatItemRef:
    def test_none(self):
        assert _format_item_ref(None) == ""

    def test_with_item_info(self):
        result = _format_item_ref({"item_number": 5, "filename": "05-my-feature.md"})
        assert result == " (#5 - `05-my-feature.md`)"


# ── _parse_intake_response ────────────────────────────────────────────────────


SAMPLE_RESPONSE = """\
Title: Add dark mode toggle

Classification: feature - User wants a visual preference option

Clarity: 4

5 Whys:
1. Why is dark mode needed? Users work at night.
2. Why at night? Bright screens cause eye strain.
3. Why eye strain matters? Reduces productivity.
4. Why productivity matters? Affects project timelines.
5. Why timelines? Business goals require on-time delivery.

Root Need: Reduce eye strain during extended use

Description:
Users need a dark mode toggle in settings to reduce eye strain.
This will improve usability during low-light conditions.
"""


class TestParseIntakeResponse:
    def test_title(self):
        result = SlackSuspension._parse_intake_response(SAMPLE_RESPONSE)
        assert result["title"] == "Add dark mode toggle"

    def test_classification(self):
        result = SlackSuspension._parse_intake_response(SAMPLE_RESPONSE)
        assert "feature" in result["classification"]

    def test_clarity(self):
        result = SlackSuspension._parse_intake_response(SAMPLE_RESPONSE)
        assert result["clarity"] == 4

    def test_five_whys_count(self):
        result = SlackSuspension._parse_intake_response(SAMPLE_RESPONSE)
        assert len(result["five_whys"]) == 5

    def test_root_need(self):
        result = SlackSuspension._parse_intake_response(SAMPLE_RESPONSE)
        assert "eye strain" in result["root_need"]

    def test_description(self):
        result = SlackSuspension._parse_intake_response(SAMPLE_RESPONSE)
        assert "dark mode" in result["description"]

    def test_empty_text(self):
        result = SlackSuspension._parse_intake_response("")
        assert result["title"] == ""
        assert result["five_whys"] == []
        assert result["clarity"] == 0

    def test_partial_text_no_whys(self):
        result = SlackSuspension._parse_intake_response("Title: Only a title\n")
        assert result["title"] == "Only a title"
        assert result["five_whys"] == []

    def test_clarity_zero_when_missing(self):
        result = SlackSuspension._parse_intake_response("Title: X\n")
        assert result["clarity"] == 0


# ── check_suspension_reply ────────────────────────────────────────────────────


class TestCheckSuspensionReply:
    def test_returns_none_without_token(self):
        s = _make_suspension(bot_token="")
        assert s.check_suspension_reply("C123", "1700.0") is None

    def test_returns_none_without_channel(self):
        s = _make_suspension()
        assert s.check_suspension_reply("", "1700.0") is None

    def test_returns_none_without_ts(self):
        s = _make_suspension()
        assert s.check_suspension_reply("C123", "") is None

    @patch("urllib.request.urlopen")
    def test_returns_human_reply(self, mock_urlopen):
        messages = [
            {"ts": "1700.0", "text": "original"},
            {"ts": "1700.1", "text": "Human reply here"},
        ]
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value.read = lambda: json.dumps(
            {"ok": True, "messages": messages}
        ).encode()

        s = _make_suspension()
        result = s.check_suspension_reply("C123", "1700.0")
        assert result == "Human reply here"

    @patch("urllib.request.urlopen")
    def test_skips_root_message(self, mock_urlopen):
        messages = [{"ts": "1700.0", "text": "original"}]
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value.read = lambda: json.dumps(
            {"ok": True, "messages": messages}
        ).encode()

        s = _make_suspension()
        assert s.check_suspension_reply("C123", "1700.0") is None

    @patch("urllib.request.urlopen")
    def test_skips_bot_messages(self, mock_urlopen):
        messages = [
            {"ts": "1700.1", "bot_id": "B001", "text": "bot msg"},
            {"ts": "1700.2", "text": "human msg"},
        ]
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value.read = lambda: json.dumps(
            {"ok": True, "messages": messages}
        ).encode()

        s = _make_suspension()
        assert s.check_suspension_reply("C123", "1700.0") == "human msg"

    @patch("urllib.request.urlopen")
    def test_api_error_returns_none(self, mock_urlopen):
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value.read = lambda: json.dumps(
            {"ok": False, "error": "channel_not_found"}
        ).encode()

        s = _make_suspension()
        assert s.check_suspension_reply("C123", "1700.0") is None

    @patch("urllib.request.urlopen", side_effect=OSError("network error"))
    def test_exception_returns_none(self, _mock_urlopen):
        s = _make_suspension()
        assert s.check_suspension_reply("C123", "1700.0") is None

    @patch("urllib.request.urlopen")
    def test_request_includes_limit(self, mock_urlopen):
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value.read = lambda: json.dumps(
            {"ok": True, "messages": []}
        ).encode()

        s = _make_suspension()
        s.check_suspension_reply("C123", "1700.0")
        url = mock_urlopen.call_args[0][0].full_url
        assert f"limit={SLACK_THREAD_REPLIES_LIMIT}" in url


# ── _check_all_suspensions ────────────────────────────────────────────────────


class TestCheckAllSuspensions:
    def test_no_suspended_dir(self):
        s = _make_suspension(callbacks=_make_callbacks())
        with patch("glob.glob", return_value=[]):
            s._check_all_suspensions()  # should not raise

    def test_skips_marker_without_thread_ts(self, tmp_path):
        marker_path = tmp_path / "item.json"
        marker_path.write_text(json.dumps({"slug": "item"}))
        cb = _make_callbacks()
        s = _make_suspension(callbacks=cb)

        with patch("glob.glob", return_value=[str(marker_path)]):
            s._check_all_suspensions()

        cb.post_message.assert_not_called()

    def test_skips_marker_already_answered(self, tmp_path):
        marker_path = tmp_path / "item.json"
        marker_path.write_text(json.dumps({
            "slug": "item",
            "slack_thread_ts": "1700.0",
            "slack_channel_id": "C123",
            "answer": "yes",
        }))
        cb = _make_callbacks()
        s = _make_suspension(callbacks=cb)

        with patch("glob.glob", return_value=[str(marker_path)]):
            s._check_all_suspensions()

        cb.post_message.assert_not_called()

    def test_writes_answer_and_posts_confirmation(self, tmp_path):
        marker_path = tmp_path / "item.json"
        marker_path.write_text(json.dumps({
            "slug": "9-dark-mode",
            "slack_thread_ts": "1700.0",
            "slack_channel_id": "C123",
        }))
        cb = _make_callbacks()
        s = _make_suspension(callbacks=cb)

        with patch("glob.glob", return_value=[str(marker_path)]):
            with patch.object(s, "check_suspension_reply", return_value="Yes, do it"):
                s._check_all_suspensions()

        updated = json.loads(marker_path.read_text())
        assert updated["answer"] == "Yes, do it"
        cb.post_message.assert_called_once()
        call_payload = cb.post_message.call_args[0][0]
        assert "9-dark-mode" in call_payload["text"]

    def test_does_nothing_when_no_reply(self, tmp_path):
        marker_path = tmp_path / "item.json"
        marker_path.write_text(json.dumps({
            "slug": "item",
            "slack_thread_ts": "1700.0",
            "slack_channel_id": "C123",
        }))
        cb = _make_callbacks()
        s = _make_suspension(callbacks=cb)

        with patch("glob.glob", return_value=[str(marker_path)]):
            with patch.object(s, "check_suspension_reply", return_value=None):
                s._check_all_suspensions()

        updated = json.loads(marker_path.read_text())
        assert "answer" not in updated


# ── post_suspension_question ──────────────────────────────────────────────────


class TestPostSuspensionQuestion:
    def test_returns_none_when_no_channel(self):
        cb = _make_callbacks(get_type_channel=MagicMock(return_value=""))
        s = _make_suspension(callbacks=cb)
        result = s.post_suspension_question("9-feature", "feature", "Q?", "Ctx")
        assert result is None
        cb.post_message_ts.assert_not_called()

    def test_posts_and_returns_ts(self):
        cb = _make_callbacks()
        s = _make_suspension(callbacks=cb)
        result = s.post_suspension_question("9-feature", "feature", "Q?", "Ctx")
        assert result == "1700000000.000001"
        cb.post_message_ts.assert_called_once()

    def test_payload_contains_slug(self):
        cb = _make_callbacks()
        s = _make_suspension(callbacks=cb)
        s.post_suspension_question("my-slug", "feature", "Q?", "Ctx")
        payload = cb.post_message_ts.call_args[0][0]
        header_text = payload["blocks"][0]["text"]["text"]
        assert "my-slug" in header_text

    def test_payload_contains_question_and_context(self):
        cb = _make_callbacks()
        s = _make_suspension(callbacks=cb)
        s.post_suspension_question("slug", "defect", "Why broken?", "It affects prod")
        payload = cb.post_message_ts.call_args[0][0]
        texts = [b["text"]["text"] for b in payload["blocks"] if b["type"] == "section"]
        all_text = " ".join(texts)
        assert "Why broken?" in all_text
        assert "It affects prod" in all_text

    def test_calls_get_type_channel_with_item_type(self):
        cb = _make_callbacks()
        s = _make_suspension(callbacks=cb)
        s.post_suspension_question("slug", "defect", "Q?", "Ctx")
        cb.get_type_channel.assert_called_once_with("defect")


# ── send_question ─────────────────────────────────────────────────────────────


class TestSendQuestion:
    def test_returns_none_when_not_enabled(self):
        s = _make_suspension(question_config={"enabled": False})
        assert s.send_question("Q?", ["yes", "no"]) is None

    def test_returns_none_when_should_notify_false(self):
        cb = _make_callbacks(should_notify=MagicMock(return_value=False))
        s = _make_suspension(
            question_config={"enabled": True}, callbacks=cb
        )
        assert s.send_question("Q?", ["yes", "no"]) is None

    def test_file_based_timeout_returns_fallback(self, tmp_path):
        cb = _make_callbacks(ensure_socket_mode=MagicMock(return_value=False))
        s = _make_suspension(
            question_config={"enabled": True, "timeout_minutes": 1, "fallback": "skip"},
            callbacks=cb,
        )
        question_file = tmp_path / "q.json"
        with (
            patch("langgraph_pipeline.slack.suspension.SLACK_QUESTION_PATH", str(question_file)),
            patch("langgraph_pipeline.slack.suspension.SLACK_ANSWER_PATH", str(tmp_path / "a.json")),
            patch("langgraph_pipeline.slack.suspension.SLACK_POLL_INTERVAL_SECONDS", 999),
            patch("time.time", side_effect=[0, 61]),
        ):
            result = s.send_question("Q?", ["yes", "no"], timeout_minutes=1)

        assert result == "skip"

    def test_file_based_reads_answer_file(self, tmp_path):
        cb = _make_callbacks(ensure_socket_mode=MagicMock(return_value=False))
        s = _make_suspension(
            question_config={"enabled": True, "timeout_minutes": 60, "fallback": "skip"},
            callbacks=cb,
        )
        answer_path = tmp_path / "answer.json"
        question_path = tmp_path / "question.json"
        answer_path.write_text(json.dumps({"answer": "yes"}))

        with (
            patch("langgraph_pipeline.slack.suspension.SLACK_QUESTION_PATH", str(question_path)),
            patch("langgraph_pipeline.slack.suspension.SLACK_ANSWER_PATH", str(answer_path)),
        ):
            result = s.send_question("Q?", ["yes", "no"])

        assert result == "yes"
        assert not answer_path.exists()

    def test_socket_mode_returns_answer(self):
        cb = _make_callbacks(ensure_socket_mode=MagicMock(return_value=True))
        s = _make_suspension(
            question_config={"enabled": True, "timeout_minutes": 1, "fallback": "skip"},
            callbacks=cb,
        )

        def set_answer():
            import time as _time
            _time.sleep(0.05)
            s.receive_answer("yes")

        t = threading.Thread(target=set_answer)
        t.start()
        result = s.send_question("Q?", ["yes", "no"], timeout_minutes=1)
        t.join()

        assert result == "yes"

    def test_socket_mode_timeout_returns_fallback(self):
        cb = _make_callbacks(ensure_socket_mode=MagicMock(return_value=True))
        s = _make_suspension(
            question_config={"enabled": True, "timeout_minutes": 0, "fallback": "skip"},
            callbacks=cb,
        )

        with patch.object(threading.Event, "wait", return_value=False):
            result = s.send_question("Q?", ["yes", "no"], timeout_minutes=0)

        assert result == "skip"


# ── receive_answer ────────────────────────────────────────────────────────────


class TestReceiveAnswer:
    def test_sets_last_answer_and_signals_event(self):
        s = _make_suspension()
        event = threading.Event()
        s._pending_answer = event
        s.receive_answer("yes")
        assert s._last_answer == "yes"
        assert event.is_set()

    def test_no_error_when_no_pending_answer(self):
        s = _make_suspension()
        s._pending_answer = None
        s.receive_answer("yes")  # should not raise
        assert s._last_answer == "yes"


# ── answer_question ───────────────────────────────────────────────────────────


class TestAnswerQuestion:
    def test_calls_send_status_with_answer(self):
        cb = _make_callbacks(call_claude=MagicMock(return_value=ClaudeResult(text="The answer is 42.", failure_reason=None)))
        s = _make_suspension(callbacks=cb)
        s.answer_question("What is the status?", "C123")
        cb.send_status.assert_called_once()
        args = cb.send_status.call_args[0]
        assert "42" in args[0]
        assert args[1] == "info"
        assert args[2] == "C123"

    def test_uses_state_context_when_llm_empty(self):
        cb = _make_callbacks(
            call_claude=MagicMock(return_value=ClaudeResult(text="", failure_reason=None)),
            format_state=MagicMock(return_value="pipeline is idle"),
        )
        s = _make_suspension(callbacks=cb)
        s.answer_question("status?")
        args = cb.send_status.call_args[0]
        assert "pipeline is idle" in args[0]

    def test_records_qa_history(self):
        cb = _make_callbacks(call_claude=MagicMock(return_value=ClaudeResult(text="My answer", failure_reason=None)))
        s = _make_suspension(callbacks=cb, qa_history_max_turns=3)
        s.answer_question("question one")
        assert len(s._qa_history) == 1
        assert s._qa_history[0] == ("question one", "My answer")

    def test_qa_history_injected_into_prompt(self):
        cb = _make_callbacks(call_claude=MagicMock(return_value=ClaudeResult(text="response", failure_reason=None)))
        s = _make_suspension(callbacks=cb, qa_history_max_turns=3)
        s._qa_history = [("prev Q", "prev A")]
        s.answer_question("new Q")
        prompt = cb.call_claude.call_args[0][0]
        assert "prev Q" in prompt
        assert "prev A" in prompt

    def test_qa_history_trimmed_to_max_turns(self):
        cb = _make_callbacks(call_claude=MagicMock(return_value=ClaudeResult(text="A", failure_reason=None)))
        s = _make_suspension(callbacks=cb, qa_history_max_turns=2)
        for i in range(5):
            s.answer_question(f"Q{i}")
        assert len(s._qa_history) == 2

    def test_qa_history_disabled(self):
        cb = _make_callbacks(call_claude=MagicMock(return_value=ClaudeResult(text="A", failure_reason=None)))
        s = _make_suspension(callbacks=cb, qa_history_enabled=False)
        s.answer_question("Q")
        assert s._qa_history == []


# ── _run_intake_analysis ──────────────────────────────────────────────────────


def _full_llm_response(
    title: str = "Add feature",
    classification: str = "feature - user needs this",
    clarity: int = 4,
    root_need: str = "Reduce friction",
    desc: str = "A useful feature.",
    n_whys: int = REQUIRED_FIVE_WHYS_COUNT,
) -> str:
    whys = "\n".join(f"{i+1}. Why {i+1}" for i in range(n_whys))
    return (
        f"Title: {title}\n\n"
        f"Classification: {classification}\n\n"
        f"Clarity: {clarity}\n\n"
        f"5 Whys:\n{whys}\n\n"
        f"Root Need: {root_need}\n\n"
        f"Description:\n{desc}\n"
    )


class TestRunIntakeAnalysis:
    def test_rate_limited_skips_analysis(self):
        cb = _make_callbacks(check_intake_rate=MagicMock(return_value=True))
        s = _make_suspension(callbacks=cb)
        intake = _make_intake()
        s._run_intake_analysis(intake)
        assert intake.status == "done"
        cb.call_claude.assert_not_called()

    def test_creates_backlog_item_on_success(self):
        llm_response = _full_llm_response()
        cb = _make_callbacks(call_claude=MagicMock(return_value=ClaudeResult(text=llm_response, failure_reason=None)))
        s = _make_suspension(callbacks=cb)
        intake = _make_intake()
        s._run_intake_analysis(intake)
        assert intake.status == "done"
        cb.create_backlog.assert_called_once()

    def test_fallback_on_empty_llm_response(self):
        cb = _make_callbacks(call_claude=MagicMock(return_value=ClaudeResult(text="", failure_reason=None)))
        s = _make_suspension(callbacks=cb)
        intake = _make_intake()
        s._run_intake_analysis(intake)
        assert intake.status == "done"
        cb.create_backlog.assert_called_once()
        args = cb.send_status.call_args_list
        success_call = next(
            (c for c in args if c[0][1] == "success"), None
        )
        assert success_call is not None
        assert "Analysis unavailable" in success_call[0][0]

    def test_sends_acknowledgment_before_creating_item(self):
        send_status_calls = []

        def capture_send_status(msg, level, channel_id):
            send_status_calls.append((msg, level))

        llm_response = _full_llm_response()
        cb = _make_callbacks(
            call_claude=MagicMock(return_value=ClaudeResult(text=llm_response, failure_reason=None)),
            send_status=capture_send_status,
        )
        s = _make_suspension(callbacks=cb)
        intake = _make_intake()
        s._run_intake_analysis(intake)

        # First call is "Analyzing..." acknowledgment
        assert "Analyzing" in send_status_calls[0][0]

    def test_low_clarity_sends_clarification(self):
        llm_response = _full_llm_response(clarity=INTAKE_CLARITY_THRESHOLD - 1)
        cb = _make_callbacks(call_claude=MagicMock(return_value=ClaudeResult(text=llm_response, failure_reason=None)))
        s = _make_suspension(callbacks=cb)
        intake = _make_intake()
        s._run_intake_analysis(intake)
        assert intake.status == "done"
        cb.create_backlog.assert_not_called()
        cb.build_block.assert_called()
        call_args = cb.build_block.call_args[0]
        assert INTAKE_CLARIFICATION_TEMPLATE in call_args

    def test_retries_when_few_whys(self):
        first_response = _full_llm_response(n_whys=2)
        retry_response = _full_llm_response(n_whys=REQUIRED_FIVE_WHYS_COUNT)
        cb = _make_callbacks(
            call_claude=MagicMock(side_effect=[
                ClaudeResult(text=first_response, failure_reason=None),
                ClaudeResult(text=retry_response, failure_reason=None),
            ])
        )
        s = _make_suspension(callbacks=cb)
        intake = _make_intake()
        s._run_intake_analysis(intake)
        assert cb.call_claude.call_count == 2
        assert intake.status == "done"

    def test_cleans_up_pending_intakes_on_success(self):
        lock = threading.Lock()
        pending: dict = {}
        intake = _make_intake()
        intake_key = f"{intake.channel_name}:{intake.ts}"
        pending[intake_key] = intake

        llm_response = _full_llm_response()
        cb = _make_callbacks(
            call_claude=MagicMock(return_value=ClaudeResult(text=llm_response, failure_reason=None)),
            intake_lock=lock,
            pending_intakes=pending,
        )
        s = _make_suspension(callbacks=cb)
        s._run_intake_analysis(intake)
        assert intake_key not in pending

    def test_cleans_up_pending_intakes_on_error(self):
        lock = threading.Lock()
        pending: dict = {}
        intake = _make_intake()
        intake_key = f"{intake.channel_name}:{intake.ts}"
        pending[intake_key] = intake

        cb = _make_callbacks(
            call_claude=MagicMock(side_effect=RuntimeError("fail")),
            intake_lock=lock,
            pending_intakes=pending,
        )
        s = _make_suspension(callbacks=cb)
        s._run_intake_analysis(intake)
        assert intake_key not in pending

    def test_notifies_success_with_item_ref(self):
        llm_response = _full_llm_response()
        item_info = {"item_number": 7, "filename": "07-add-feature.md", "filepath": "/tmp/07.md"}
        cb = _make_callbacks(
            call_claude=MagicMock(return_value=ClaudeResult(text=llm_response, failure_reason=None)),
            create_backlog=MagicMock(return_value=item_info),
        )
        s = _make_suspension(callbacks=cb)
        intake = _make_intake()
        s._run_intake_analysis(intake)

        success_calls = [
            c for c in cb.send_status.call_args_list if c[0][1] == "success"
        ]
        assert success_calls
        success_msg = success_calls[-1][0][0]
        assert "#7" in success_msg
        assert "07-add-feature.md" in success_msg


# ── _run_dedup_check ──────────────────────────────────────────────────────────


class TestRunDedupCheck:
    def _make_high_sim(self) -> list[dict]:
        return [
            {
                "title": "Add dark mode",
                "similarity": 0.95,
                "filename": "01-dark-mode.md",
                "filepath": "/tmp/01-dark-mode.md",
            }
        ]

    def test_returns_false_when_no_duplicate(self):
        cb = _make_callbacks(
            call_claude=MagicMock(return_value=ClaudeResult(text=json.dumps({"duplicate": False}), failure_reason=None))
        )
        s = _make_suspension(callbacks=cb)
        intake = _make_intake()
        rag = MagicMock()
        rag.available = True
        result = s._run_dedup_check(intake, "New Feature", "desc", self._make_high_sim(), rag)
        assert result is False

    def test_returns_true_and_notifies_when_duplicate(self, tmp_path):
        existing = tmp_path / "01-dark-mode.md"
        existing.write_text("# Existing\n")
        high_sim = [{
            "title": "Add dark mode",
            "similarity": 0.95,
            "filename": "01-dark-mode.md",
            "filepath": str(existing),
        }]
        cb = _make_callbacks(
            call_claude=MagicMock(
                return_value=ClaudeResult(
                    text=json.dumps({"duplicate": True, "match_filename": "01-dark-mode.md"}),
                    failure_reason=None,
                )
            )
        )
        s = _make_suspension(callbacks=cb)
        intake = _make_intake()
        rag = MagicMock()
        rag.available = True
        result = s._run_dedup_check(intake, "Same Feature", "desc", high_sim, rag)
        assert result is True
        cb.send_status.assert_called()
        status_msg = cb.send_status.call_args[0][0]
        assert "Consolidated" in status_msg

    def test_returns_false_on_json_decode_error(self):
        cb = _make_callbacks(call_claude=MagicMock(return_value=ClaudeResult(text="not json", failure_reason=None)))
        s = _make_suspension(callbacks=cb)
        intake = _make_intake()
        rag = MagicMock()
        result = s._run_dedup_check(intake, "T", "D", self._make_high_sim(), rag)
        assert result is False
