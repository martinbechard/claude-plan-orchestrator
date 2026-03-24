# tests/langgraph/slack/test_poller.py
# Unit tests for langgraph_pipeline.slack.poller module.
# Design: docs/plans/2026-02-26-03-extract-slack-modules-design.md

"""Unit tests for SlackPoller: polling, dedup, and safety layers A1-A4.

All Slack API calls and filesystem operations are mocked.
Tests cover:
  - poll_messages: channel discovery, last-read tracking, HTTP polling
  - _handle_polled_messages: all four safety filters and routing
  - create_backlog_item: throttle, file creation, intake history recording
  - _route_message_via_llm: LLM callback delegation
  - start/stop_background_polling: thread lifecycle
  - _prune_message_tracking: TTL expiry
  - handle_control_command: stop semaphore and skip stub
  - A1: _is_chain_loop_artifact, _load/_save_intake_history
  - A4: _check_intake_rate_limit, _check_backlog_throttle
"""

import json
import threading
import time
from io import BytesIO
from unittest.mock import MagicMock, mock_open, patch

import pytest

from langgraph_pipeline.slack.identity import AgentIdentity
from langgraph_pipeline.slack.poller import (
    BOT_NOTIFICATION_PATTERN,
    INTAKE_HISTORY_MAX_ENTRIES,
    INTAKE_HISTORY_PATH,
    LOOP_DETECTION_WINDOW_SECONDS,
    MAX_INTAKES_PER_WINDOW,
    MAX_SELF_REPLIES_PER_WINDOW,
    MESSAGE_TRACKING_TTL_SECONDS,
    PollerCallbacks,
    SlackPoller,
    _safe_float_ts,
)
from langgraph_pipeline.slack.suspension import IntakeState


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_poller(
    bot_token: str = "xoxb-test",
    channel_id: str = "C123",
    channel_prefix: str = "orchestrator-",
    enabled: bool = True,
    callbacks: PollerCallbacks | None = None,
    agent_identity: AgentIdentity | None = None,
) -> SlackPoller:
    """Return a SlackPoller ready for testing."""
    return SlackPoller(
        bot_token=bot_token,
        channel_id=channel_id,
        channel_prefix=channel_prefix,
        enabled=enabled,
        callbacks=callbacks,
        agent_identity=agent_identity,
    )


def _api_response(ok: bool = True, **extra) -> BytesIO:
    """Fake urllib response body."""
    return BytesIO(json.dumps({"ok": ok, **extra}).encode())


# ── _safe_float_ts ────────────────────────────────────────────────────────────


class TestSafeFloatTs:
    def test_valid_ts(self):
        assert _safe_float_ts("1700000000.123456") == pytest.approx(1700000000.123456)

    def test_integer_string(self):
        assert _safe_float_ts("1700000000") == pytest.approx(1700000000.0)

    def test_empty_string(self):
        assert _safe_float_ts("") == 0.0

    def test_non_numeric(self):
        assert _safe_float_ts("abc") == 0.0

    def test_none_like(self):
        assert _safe_float_ts(None) == 0.0  # type: ignore[arg-type]


# ── BOT_NOTIFICATION_PATTERN ──────────────────────────────────────────────────


class TestBotNotificationPattern:
    def test_matches_defect_received(self):
        assert BOT_NOTIFICATION_PATTERN.search(":white_check_mark: *Defect received*")

    def test_matches_feature_created(self):
        assert BOT_NOTIFICATION_PATTERN.search(":large_blue_circle: *Feature created*")

    def test_matches_received_your_defect(self):
        assert BOT_NOTIFICATION_PATTERN.search("Received your defect request")

    def test_matches_pipeline_completed(self):
        assert BOT_NOTIFICATION_PATTERN.search(":white_check_mark: *Completed: foo*")

    def test_no_match_plain_text(self):
        assert not BOT_NOTIFICATION_PATTERN.search("please fix the login bug")

    def test_no_match_unrelated_emoji(self):
        assert not BOT_NOTIFICATION_PATTERN.search(":rocket: Deployed v1.2")


# ── SlackPoller init ──────────────────────────────────────────────────────────


class TestSlackPollerInit:
    def test_enabled_false_when_disabled(self):
        p = _make_poller(enabled=False)
        assert not p._enabled

    def test_stores_bot_token(self):
        p = _make_poller(bot_token="xoxb-abc")
        assert p._bot_token == "xoxb-abc"

    def test_default_callbacks_are_noop(self):
        p = _make_poller()
        assert p._callbacks.call_claude is None
        assert p._callbacks.post_message is None

    def test_poll_messages_returns_empty_when_disabled(self):
        p = _make_poller(enabled=False)
        assert p.poll_messages() == []


# ── _discover_channels ────────────────────────────────────────────────────────


class TestDiscoverChannels:
    def test_returns_prefixed_channels(self):
        p = _make_poller(channel_prefix="orchestrator-")
        channels_payload = {
            "ok": True,
            "channels": [
                {"name": "orchestrator-features", "id": "C1"},
                {"name": "orchestrator-defects", "id": "C2"},
                {"name": "other-channel", "id": "C3"},
            ],
        }
        resp = BytesIO(json.dumps(channels_payload).encode())
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__ = lambda s: resp
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            result = p._discover_channels()

        assert "orchestrator-features" in result
        assert "orchestrator-defects" in result
        assert "other-channel" not in result

    def test_uses_cache_within_ttl(self):
        p = _make_poller()
        p._discovered_channels = {"orchestrator-features": "C1"}
        p._channels_discovered_at = time.time()  # fresh

        with patch("urllib.request.urlopen") as mock_open:
            result = p._discover_channels()
            mock_open.assert_not_called()

        assert result == {"orchestrator-features": "C1"}

    def test_returns_existing_cache_on_api_error(self):
        p = _make_poller()
        p._discovered_channels = {"orchestrator-features": "C1"}
        p._channels_discovered_at = 0.0  # expired

        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            result = p._discover_channels()

        assert result == {"orchestrator-features": "C1"}


# ── _get_channel_role ─────────────────────────────────────────────────────────


class TestGetChannelRole:
    def test_features_suffix(self):
        p = _make_poller(channel_prefix="orchestrator-")
        assert p._get_channel_role("orchestrator-features") == "feature"

    def test_defects_suffix(self):
        p = _make_poller(channel_prefix="orchestrator-")
        assert p._get_channel_role("orchestrator-defects") == "defect"

    def test_questions_suffix(self):
        p = _make_poller(channel_prefix="orchestrator-")
        assert p._get_channel_role("orchestrator-questions") == "question"

    def test_notifications_suffix(self):
        p = _make_poller(channel_prefix="orchestrator-")
        assert p._get_channel_role("orchestrator-notifications") == "control"

    def test_unknown_suffix_returns_empty(self):
        p = _make_poller(channel_prefix="orchestrator-")
        assert p._get_channel_role("orchestrator-unknown") == ""

    def test_wrong_prefix_returns_empty(self):
        p = _make_poller(channel_prefix="orchestrator-")
        assert p._get_channel_role("other-features") == ""


# ── _load_last_read_all / _save_last_read_all ─────────────────────────────────


class TestLastReadPersistence:
    def test_load_multi_channel_format(self):
        p = _make_poller()
        data = {"channels": {"C1": "1234.0", "C2": "5678.0"}}
        with patch("builtins.open", mock_open(read_data=json.dumps(data))):
            result = p._load_last_read_all()
        assert result == {"C1": "1234.0", "C2": "5678.0"}

    def test_load_legacy_single_channel_format(self):
        p = _make_poller()
        data = {"channel_id": "C1", "last_ts": "1234.0"}
        with patch("builtins.open", mock_open(read_data=json.dumps(data))):
            result = p._load_last_read_all()
        assert result == {"C1": "1234.0"}

    def test_load_returns_empty_on_missing_file(self):
        p = _make_poller()
        with patch("builtins.open", side_effect=IOError):
            result = p._load_last_read_all()
        assert result == {}

    def test_save_writes_channels_key(self):
        p = _make_poller()
        mock_file = mock_open()
        with patch("builtins.open", mock_file):
            p._save_last_read_all({"C1": "1234.0"})
        written = "".join(c.args[0] for c in mock_file().write.call_args_list)
        saved = json.loads(written)
        assert saved == {"channels": {"C1": "1234.0"}}


# ── poll_messages ─────────────────────────────────────────────────────────────


class TestPollMessages:
    def _setup_poller_with_channels(self) -> SlackPoller:
        p = _make_poller()
        p._discovered_channels = {"orchestrator-features": "C1"}
        p._channels_discovered_at = time.time()
        return p

    def test_returns_tagged_messages(self):
        p = self._setup_poller_with_channels()
        history_resp = {
            "ok": True,
            "messages": [{"ts": "1700.001", "text": "hi", "user": "U1"}],
        }

        def _urlopen(req, timeout=10):
            mock = MagicMock()
            mock.__enter__ = lambda s: BytesIO(json.dumps(history_resp).encode())
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            with patch.object(p, "_load_last_read_all", return_value={"C1": "1699.0"}):
                with patch.object(p, "_save_last_read_all"):
                    msgs = p.poll_messages()

        assert len(msgs) == 1
        assert msgs[0]["_channel_name"] == "orchestrator-features"
        assert msgs[0]["_channel_id"] == "C1"

    def test_skips_subtype_messages(self):
        p = self._setup_poller_with_channels()
        history_resp = {
            "ok": True,
            "messages": [
                {"ts": "1700.001", "text": "joined", "subtype": "channel_join"},
                {"ts": "1700.002", "text": "real msg", "user": "U1"},
            ],
        }

        def _urlopen(req, timeout=10):
            mock = MagicMock()
            mock.__enter__ = lambda s: BytesIO(json.dumps(history_resp).encode())
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            with patch.object(p, "_load_last_read_all", return_value={}):
                with patch.object(p, "_save_last_read_all"):
                    msgs = p.poll_messages()

        assert len(msgs) == 1
        assert msgs[0]["text"] == "real msg"

    def test_falls_back_to_single_channel_when_no_prefix_channels(self):
        p = _make_poller(channel_id="C999")
        p._discovered_channels = {}
        p._channels_discovered_at = time.time()
        history_resp = {
            "ok": True,
            "messages": [{"ts": "1700.001", "text": "hi", "user": "U1"}],
        }

        def _urlopen(req, timeout=10):
            mock = MagicMock()
            mock.__enter__ = lambda s: BytesIO(json.dumps(history_resp).encode())
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            with patch.object(p, "_load_last_read_all", return_value={}):
                with patch.object(p, "_save_last_read_all"):
                    msgs = p.poll_messages()

        assert len(msgs) == 1


# ── A3: BOT_NOTIFICATION_PATTERN filter ──────────────────────────────────────


class TestA3BotNotificationFilter:
    def test_bot_notification_is_skipped(self):
        p = _make_poller()
        msg = {
            "ts": "1700.001",
            "text": ":white_check_mark: *Defect received*",
            "_channel_name": "orchestrator-features",
            "_channel_id": "C1",
        }
        p._handle_polled_messages([msg])
        assert "1700.001" in p._processed_message_ts

    def test_normal_message_passes_a3(self):
        """A message that doesn't match the pattern is not filtered by A3."""
        run_intake = MagicMock()
        callbacks = PollerCallbacks(run_intake=run_intake)
        p = _make_poller(channel_prefix="orchestrator-", callbacks=callbacks)
        # Put channel in cache
        p._discovered_channels = {"orchestrator-defects": "C1"}
        msg = {
            "ts": "1700.002",
            "text": "The login page crashes on submit, steps: go to /login, click submit",
            "_channel_name": "orchestrator-defects",
            "_channel_id": "C1",
        }
        p._handle_polled_messages([msg])
        run_intake.assert_called_once()


# ── A1: Chain-loop artifact detection ────────────────────────────────────────


class TestA1ChainDetection:
    def test_skips_message_referencing_recent_item_number(self):
        p = _make_poller()
        p._intake_history = [
            {"item_number": 42, "slug": "login-bug", "timestamp": time.time()}
        ]
        msg = {
            "ts": "1700.001",
            "text": "Item #42 has been created in defect-backlog",
            "_channel_name": "orchestrator-notifications",
            "_channel_id": "C1",
        }
        p._handle_polled_messages([msg])
        assert "1700.001" in p._processed_message_ts

    def test_skips_message_with_slug_match(self):
        p = _make_poller()
        p._intake_history = [
            {"item_number": 10, "slug": "login-page-crashes-on-submit", "timestamp": time.time()}
        ]
        msg = {
            "ts": "1700.002",
            "text": "The login-page-crashes-on-submit item was created.",
            "_channel_name": "orchestrator-notifications",
            "_channel_id": "C1",
        }
        p._handle_polled_messages([msg])
        assert "1700.002" in p._processed_message_ts

    def test_passes_unrelated_message(self):
        p = _make_poller()
        p._intake_history = [
            {"item_number": 42, "slug": "login-bug", "timestamp": time.time()}
        ]
        assert not p._is_chain_loop_artifact("please add a dark mode option")


# ── A2: Self-reply window ─────────────────────────────────────────────────────


class TestA2SelfReplyWindow:
    def test_skips_message_when_window_exceeded(self):
        p = _make_poller()
        # Seed the reply window with a recent timestamp
        now = time.monotonic()
        p._self_reply_window["C1"] = [now - 1]  # 1 second ago, within window
        p._own_sent_ts.add("1700.001")

        msg = {
            "ts": "1700.001",
            "text": "bot echo back",
            "_channel_name": "orchestrator-notifications",
            "_channel_id": "C1",
        }
        p._handle_polled_messages([msg])
        # Should be filtered by A2 (not added to processed_message_ts since we skip early)
        assert "1700.001" not in p._processed_message_ts

    def test_accepts_self_origin_below_threshold(self):
        """First self-reply within window is accepted (below MAX_SELF_REPLIES_PER_WINDOW=1)."""
        run_intake = MagicMock()
        callbacks = PollerCallbacks(run_intake=run_intake)
        p = _make_poller(callbacks=callbacks)
        # No prior self-replies in window
        p._self_reply_window["C1"] = []
        p._own_sent_ts.add("1700.001")

        # Put it in a defect channel so it hits intake processing
        p._discovered_channels = {"orchestrator-defects": "C1"}
        msg = {
            "ts": "1700.001",
            "text": "The login form crashes when empty fields are submitted on production",
            "_channel_name": "orchestrator-defects",
            "_channel_id": "C1",
        }
        p._handle_polled_messages([msg])
        run_intake.assert_called_once()


# ── Deduplication ─────────────────────────────────────────────────────────────


class TestDeduplication:
    def test_already_processed_ts_is_skipped(self):
        run_intake = MagicMock()
        p = _make_poller(callbacks=PollerCallbacks(run_intake=run_intake))
        p._processed_message_ts.add("1700.001")

        msg = {
            "ts": "1700.001",
            "text": "some feature request that should be ignored",
            "_channel_name": "orchestrator-features",
            "_channel_id": "C1",
        }
        p._handle_polled_messages([msg])
        run_intake.assert_not_called()


# ── create_backlog_item ───────────────────────────────────────────────────────


class TestCreateBacklogItem:
    def test_creates_feature_file(self, tmp_path):
        p = _make_poller()
        feature_dir = tmp_path / "docs" / "feature-backlog"
        feature_dir.mkdir(parents=True)

        with patch("langgraph_pipeline.slack.poller.os.listdir", return_value=[]):
            with patch("langgraph_pipeline.slack.poller.os.makedirs"):
                with patch("langgraph_pipeline.slack.poller.open", mock_open()) as mo:
                    with patch.object(p, "_check_backlog_throttle", return_value=False):
                        with patch.object(p, "_record_intake_history") as mock_record:
                            with patch.object(p, "_record_backlog_creation"):
                                result = p.create_backlog_item(
                                    "feature", "Dark mode support", "Add dark mode", user="U1"
                                )

        assert result["item_number"] == 1
        assert "dark-mode-support" in result["filename"]
        mock_record.assert_called_once()

    def test_returns_empty_on_invalid_type(self):
        p = _make_poller()
        result = p.create_backlog_item("other", "title", "body")
        assert result == {}

    def test_returns_empty_when_throttled(self):
        p = _make_poller()
        with patch.object(p, "_check_backlog_throttle", return_value=True):
            result = p.create_backlog_item("defect", "crash", "body")
        assert result == {}


# ── A4: Intake rate limiter ───────────────────────────────────────────────────


class TestA4IntakeRateLimiter:
    def test_allows_intake_below_limit(self):
        p = _make_poller()
        p._intake_timestamps = [time.time() - 10] * (MAX_INTAKES_PER_WINDOW - 1)
        assert not p._check_intake_rate_limit()

    def test_blocks_intake_at_limit(self):
        p = _make_poller()
        p._intake_timestamps = [time.time() - 10] * MAX_INTAKES_PER_WINDOW
        assert p._check_intake_rate_limit()

    def test_prunes_old_timestamps(self):
        p = _make_poller()
        # All timestamps older than the window
        old_time = time.time() - 400
        p._intake_timestamps = [old_time] * MAX_INTAKES_PER_WINDOW
        # Should not block because old entries are pruned
        assert not p._check_intake_rate_limit()

    def test_record_intake_timestamp_appends(self):
        p = _make_poller()
        before = len(p._intake_timestamps)
        p._record_intake_timestamp()
        assert len(p._intake_timestamps) == before + 1


# ── A1: intake history persistence ───────────────────────────────────────────


class TestA1IntakeHistoryPersistence:
    def test_load_intake_history_prunes_stale(self):
        p = _make_poller()
        old_entry = {"item_number": 1, "slug": "old", "timestamp": time.time() - 7200}
        new_entry = {"item_number": 2, "slug": "new", "timestamp": time.time() - 10}
        data = json.dumps([old_entry, new_entry])

        with patch("builtins.open", mock_open(read_data=data)):
            p._load_intake_history()

        assert len(p._intake_history) == 1
        assert p._intake_history[0]["slug"] == "new"

    def test_load_intake_history_handles_missing_file(self):
        p = _make_poller()
        with patch("builtins.open", side_effect=IOError):
            p._load_intake_history()
        assert p._intake_history == []

    def test_record_intake_history_appends_and_prunes(self):
        p = _make_poller()
        p._intake_history = [
            {"item_number": i, "slug": f"slug-{i}", "timestamp": time.time()}
            for i in range(INTAKE_HISTORY_MAX_ENTRIES + 5)
        ]
        with patch.object(p, "_save_intake_history"):
            p._record_intake_history(999, "new-slug", "New Title")

        assert len(p._intake_history) <= INTAKE_HISTORY_MAX_ENTRIES
        assert any(e["slug"] == "new-slug" for e in p._intake_history)


# ── _prune_message_tracking ───────────────────────────────────────────────────


class TestPruneMessageTracking:
    def test_prunes_old_processed_ts(self):
        p = _make_poller()
        old_ts = str(time.time() - MESSAGE_TRACKING_TTL_SECONDS - 100)
        fresh_ts = str(time.time() - 60)
        p._processed_message_ts = {old_ts, fresh_ts}
        p._prune_message_tracking()
        assert old_ts not in p._processed_message_ts
        assert fresh_ts in p._processed_message_ts

    def test_prunes_old_own_sent_ts(self):
        p = _make_poller()
        old_ts = str(time.time() - MESSAGE_TRACKING_TTL_SECONDS - 100)
        p._own_sent_ts = {old_ts}
        p._prune_message_tracking()
        assert old_ts not in p._own_sent_ts

    def test_prunes_stale_self_reply_window(self):
        p = _make_poller()
        old_time = time.monotonic() - LOOP_DETECTION_WINDOW_SECONDS - 10
        fresh_time = time.monotonic() - 10
        p._self_reply_window["C1"] = [old_time, fresh_time]
        p._prune_message_tracking()
        assert "C1" in p._self_reply_window
        assert len(p._self_reply_window["C1"]) == 1

    def test_removes_empty_self_reply_channel(self):
        p = _make_poller()
        old_time = time.monotonic() - LOOP_DETECTION_WINDOW_SECONDS - 10
        p._self_reply_window["C1"] = [old_time]
        p._prune_message_tracking()
        assert "C1" not in p._self_reply_window


# ── handle_control_command ────────────────────────────────────────────────────


class TestHandleControlCommand:
    def test_stop_writes_semaphore(self, tmp_path):
        send_status = MagicMock()
        callbacks = PollerCallbacks(send_status=send_status)
        p = _make_poller(callbacks=callbacks)
        semaphore = tmp_path / "stop"

        with patch("langgraph_pipeline.slack.poller.STOP_SEMAPHORE_PATH", str(semaphore)):
            p.handle_control_command("stop now", "control_stop", channel_id="C1")

        assert semaphore.exists()
        send_status.assert_called_once()
        assert "Stop requested" in send_status.call_args[0][0]

    def test_skip_sends_status(self):
        send_status = MagicMock()
        callbacks = PollerCallbacks(send_status=send_status)
        p = _make_poller(callbacks=callbacks)
        p.handle_control_command("skip", "control_skip", channel_id="C1")
        send_status.assert_called_once()
        assert "Skip requested" in send_status.call_args[0][0]

    def test_info_request_calls_answer_question(self):
        answer_q = MagicMock()
        callbacks = PollerCallbacks(answer_question=answer_q)
        p = _make_poller(callbacks=callbacks)
        p.handle_control_command("status", "info_request", channel_id="C1")
        answer_q.assert_called_once_with("status", channel_id="C1")


# ── _route_message_via_llm ────────────────────────────────────────────────────


class TestRouteMessageViaLlm:
    def test_delegates_to_call_claude(self):
        call_claude = MagicMock(return_value='{"action": "create_defect", "title": "crash"}')
        callbacks = PollerCallbacks(call_claude=call_claude)
        p = _make_poller(callbacks=callbacks)
        result = p._route_message_via_llm("the app crashes on startup")
        assert result["action"] == "create_defect"
        call_claude.assert_called_once()

    def test_returns_none_when_no_callback(self):
        p = _make_poller()
        result = p._route_message_via_llm("the app crashes on startup")
        assert result == {"action": "none"}

    def test_falls_back_on_invalid_json(self):
        call_claude = MagicMock(return_value="not json")
        callbacks = PollerCallbacks(call_claude=call_claude)
        p = _make_poller(callbacks=callbacks)
        result = p._route_message_via_llm("some text")
        assert result == {"action": "none"}

    def test_returns_none_for_empty_text(self):
        call_claude = MagicMock()
        callbacks = PollerCallbacks(call_claude=call_claude)
        p = _make_poller(callbacks=callbacks)
        result = p._route_message_via_llm("")
        assert result == {"action": "none"}
        call_claude.assert_not_called()


# ── start/stop background polling ────────────────────────────────────────────


class TestBackgroundPolling:
    def test_starts_and_stops_thread(self):
        p = _make_poller()
        with patch.object(p, "poll_messages", return_value=[]):
            p.start_background_polling()
            assert p._poll_thread is not None
            assert p._poll_thread.is_alive()
            p.stop_background_polling()
            assert p._poll_thread is None

    def test_does_not_start_when_disabled(self):
        p = _make_poller(enabled=False)
        p.start_background_polling()
        assert p._poll_thread is None

    def test_does_not_start_second_thread_if_alive(self):
        p = _make_poller()
        with patch.object(p, "poll_messages", return_value=[]):
            p.start_background_polling()
            first_thread = p._poll_thread
            p.start_background_polling()
            assert p._poll_thread is first_thread
            p.stop_background_polling()


# ── _execute_routed_action ────────────────────────────────────────────────────


class TestExecuteRoutedAction:
    def test_stop_pipeline_calls_control_command(self):
        p = _make_poller()
        with patch.object(p, "handle_control_command") as mock_handle:
            p._execute_routed_action(
                {"action": "stop_pipeline", "title": "stop"},
                user="U1",
                ts="1700.001",
                channel_id="C1",
            )
            mock_handle.assert_called_once_with(
                "stop", "control_stop", channel_id="C1"
            )

    def test_none_action_logs_no_action(self, capsys):
        p = _make_poller()
        p._execute_routed_action(
            {"action": "none"}, user="U1", ts="1700.001", channel_id="C1"
        )
        captured = capsys.readouterr()
        assert "No action" in captured.out

    def test_create_feature_starts_intake_thread(self):
        lock = threading.Lock()
        pending: dict = {}
        run_intake = MagicMock()
        callbacks = PollerCallbacks(
            run_intake=run_intake, intake_lock=lock, pending_intakes=pending
        )
        p = _make_poller(callbacks=callbacks)

        p._execute_routed_action(
            {"action": "create_feature", "title": "Dark mode", "body": "desc"},
            user="U1",
            ts="1700.001",
            channel_id="C1",
        )
        # Give the thread a moment to start
        time.sleep(0.05)
        run_intake.assert_called_once()
        assert isinstance(run_intake.call_args[0][0], IntakeState)


# ── A0: Bot user ID self-skip ─────────────────────────────────────────────────


class TestBotUserIdSelfSkip:
    """Tests for A0 identity-based bot user ID self-skip in SlackPoller."""

    def test_own_user_id_message_is_skipped(self):
        """Message whose user field equals _bot_user_id is skipped and ts recorded."""
        p = _make_poller(bot_token="")
        p._bot_user_id = "UBOT123"

        msg = {
            "ts": "1800.001",
            "text": "The login button is broken on mobile",
            "user": "UBOT123",
            "_channel_name": "orchestrator-defects",
            "_channel_id": "C1",
        }
        p._handle_polled_messages([msg])

        assert "1800.001" in p._processed_message_ts

    def test_different_user_id_passes_filter(self):
        """Message from a different user is not filtered by A0 and reaches intake."""
        run_intake = MagicMock()
        callbacks = PollerCallbacks(run_intake=run_intake)
        p = _make_poller(
            bot_token="", channel_prefix="orchestrator-", callbacks=callbacks
        )
        p._bot_user_id = "UBOT123"
        p._discovered_channels = {"orchestrator-defects": "C1"}

        msg = {
            "ts": "1801.001",
            "text": "The login button is broken on mobile",
            "user": "UHUMAN",
            "_channel_name": "orchestrator-defects",
            "_channel_id": "C1",
        }
        p._handle_polled_messages([msg])

        run_intake.assert_called_once()

    def test_no_bot_user_id_passes_filter(self):
        """When _bot_user_id is None, A0 is skipped and message reaches intake."""
        run_intake = MagicMock()
        callbacks = PollerCallbacks(run_intake=run_intake)
        p = _make_poller(
            bot_token="", channel_prefix="orchestrator-", callbacks=callbacks
        )
        assert p._bot_user_id is None
        p._discovered_channels = {"orchestrator-defects": "C1"}

        msg = {
            "ts": "1802.001",
            "text": "The login button is broken on mobile",
            "user": "UANYUSER",
            "_channel_name": "orchestrator-defects",
            "_channel_id": "C1",
        }
        p._handle_polled_messages([msg])

        run_intake.assert_called_once()

    def test_resolve_own_bot_id_sets_user_id(self):
        """_resolve_own_bot_id stores user_id from a successful auth.test response."""
        p = _make_poller(bot_token="")
        p._bot_token = "xoxb-test"
        p._bot_user_id = None

        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(
            {"ok": True, "user_id": "UBOT456"}
        ).encode()
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=fake_response):
            p._resolve_own_bot_id()

        assert p._bot_user_id == "UBOT456"

    def test_resolve_own_bot_id_graceful_on_failure(self):
        """_resolve_own_bot_id leaves _bot_user_id as None when auth.test raises."""
        p = _make_poller(bot_token="")
        p._bot_token = "xoxb-test"
        p._bot_user_id = None

        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            p._resolve_own_bot_id()

        assert p._bot_user_id is None
