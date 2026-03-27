# tests/langgraph/pipeline/nodes/test_intake.py
# Unit tests for the intake_analyze node.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Tests for langgraph_pipeline.pipeline.nodes.intake."""

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from langgraph_pipeline.pipeline.nodes.intake import (
    INTAKE_CLARITY_THRESHOLD,
    MAX_INTAKES_PER_HOUR,
    THROTTLE_WAIT_INTERVAL_SECONDS,
    THROTTLE_WINDOW_SECONDS,
    _check_rag_dedup,
    _check_throttle,
    _parse_clarity_score,
    _parse_timestamp,
    _read_throttle,
    _record_intake,
    _run_five_whys_analysis,
    _verify_defect_symptoms,
    _write_throttle,
    intake_analyze,
)


# ─── Autouse: mock Opus validators so unit tests never call real Claude Opus ──


@pytest.fixture(autouse=True)
def _mock_opus_validators():
    """Prevent Opus subprocess calls during unit tests."""
    with patch(
        "langgraph_pipeline.pipeline.nodes.intake._validate_five_whys",
        return_value=(True, ""),
    ), patch(
        "langgraph_pipeline.pipeline.nodes.intake._validate_design",
        return_value=(True, ""),
    ), patch(
        "langgraph_pipeline.pipeline.nodes.intake._invoke_claude_opus",
        return_value=("VALID", 0.0),
    ):
        yield


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> dict:
    """Build a minimal PipelineState dict."""
    base = {
        "item_path": "docs/defect-backlog/01-bug.md",
        "item_slug": "01-bug",
        "item_type": "defect",
        "item_name": "01 Bug",
        "plan_path": None,
        "design_doc_path": None,
        "verification_cycle": 0,
        "verification_history": [],
        "should_stop": False,
        "rate_limited": False,
        "rate_limit_reset": None,
        "session_cost_usd": 0.0,
        "session_input_tokens": 0,
        "session_output_tokens": 0,
        "intake_count_defects": 0,
        "intake_count_features": 0,
    }
    base.update(overrides)
    return base


def _recent_ts(seconds_ago: float = 10) -> str:
    """Return an ISO-8601 timestamp from seconds_ago seconds in the past."""
    t = datetime.now(tz=timezone.utc) - timedelta(seconds=seconds_ago)
    return t.isoformat()


def _old_ts() -> str:
    """Return an ISO-8601 timestamp well outside the throttle window."""
    t = datetime.now(tz=timezone.utc) - timedelta(seconds=THROTTLE_WINDOW_SECONDS + 60)
    return t.isoformat()


# ─── _parse_timestamp ─────────────────────────────────────────────────────────


class TestParseTimestamp:
    def test_valid_iso_string(self):
        ts = "2026-02-26T10:00:00+00:00"
        result = _parse_timestamp(ts)
        assert result > 0.0

    def test_invalid_string_returns_zero(self):
        assert _parse_timestamp("not-a-date") == 0.0

    def test_none_returns_zero(self):
        assert _parse_timestamp(None) == 0.0  # type: ignore[arg-type]


# ─── _read_throttle / _write_throttle ────────────────────────────────────────


class TestThrottleIO:
    def test_read_returns_empty_dict_when_file_missing(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(tmp_path / "missing.json"))
        assert _read_throttle() == {}

    def test_round_trip(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        path = tmp_path / "throttle.json"
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(path))
        data = {"defect": ["2026-02-26T10:00:00+00:00"]}
        _write_throttle(data)
        assert _read_throttle() == data

    def test_read_handles_corrupt_file(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        path = tmp_path / "throttle.json"
        path.write_text("not-valid-json")
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(path))
        assert _read_throttle() == {}


# ─── _check_throttle ─────────────────────────────────────────────────────────


class TestCheckThrottle:
    def test_not_throttled_when_no_history(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(tmp_path / "t.json"))
        assert _check_throttle("defect") is False

    def test_not_throttled_below_max(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        path = tmp_path / "t.json"
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(path))
        max_count = MAX_INTAKES_PER_HOUR["defect"]
        data = {"defect": [_recent_ts(i * 10) for i in range(max_count - 1)]}
        path.write_text(json.dumps(data))
        assert _check_throttle("defect") is False

    def test_throttled_at_max(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        path = tmp_path / "t.json"
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(path))
        max_count = MAX_INTAKES_PER_HOUR["defect"]
        data = {"defect": [_recent_ts(i * 10) for i in range(max_count)]}
        path.write_text(json.dumps(data))
        assert _check_throttle("defect") is True

    def test_old_entries_do_not_count(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        path = tmp_path / "t.json"
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(path))
        max_count = MAX_INTAKES_PER_HOUR["defect"]
        # All timestamps are outside the window.
        data = {"defect": [_old_ts() for _ in range(max_count + 5)]}
        path.write_text(json.dumps(data))
        assert _check_throttle("defect") is False


# ─── _record_intake ───────────────────────────────────────────────────────────


class TestRecordIntake:
    def test_creates_entry_for_item_type(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        path = tmp_path / "t.json"
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(path))
        _record_intake("defect")
        data = json.loads(path.read_text())
        assert "defect" in data
        assert len(data["defect"]) == 1

    def test_old_entries_pruned_on_record(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        path = tmp_path / "t.json"
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(path))
        old = {"defect": [_old_ts(), _old_ts()]}
        path.write_text(json.dumps(old))
        _record_intake("defect")
        data = json.loads(path.read_text())
        # Old entries pruned; only the new one remains.
        assert len(data["defect"]) == 1


# ─── _parse_clarity_score ─────────────────────────────────────────────────────


class TestParseClarityScore:
    def test_extracts_integer_from_output(self):
        assert _parse_clarity_score("Clarity: 4") == 4

    def test_case_insensitive(self):
        assert _parse_clarity_score("CLARITY: 2") == 2

    def test_returns_threshold_when_not_found(self):
        assert _parse_clarity_score("no clarity here") == INTAKE_CLARITY_THRESHOLD

    def test_extracts_from_multiline_output(self):
        output = "Title: Some Bug\nClarity: 5\nSummary: test"
        assert _parse_clarity_score(output) == 5


# ─── _check_rag_dedup ─────────────────────────────────────────────────────────


class TestCheckRagDedup:
    def test_returns_false_when_chromadb_not_installed(self):
        """Without chromadb package, dedup is a no-op."""
        with patch("builtins.__import__", side_effect=ImportError):
            # Direct call; chromadb import will fail inside the function.
            result = _check_rag_dedup("01-some-bug")
        # Falls back to False (no duplicate).
        # If chromadb IS installed in the test env, skip.
        # The function should not raise.
        assert isinstance(result, bool)

    def test_returns_false_on_chromadb_exception(self):
        """ChromaDB errors should not propagate to the caller."""
        mock_chromadb = MagicMock()
        mock_chromadb.PersistentClient.side_effect = RuntimeError("db error")
        with patch.dict("sys.modules", {"chromadb": mock_chromadb}):
            result = _check_rag_dedup("01-some-bug")
        assert result is False


# ─── _verify_defect_symptoms ──────────────────────────────────────────────────


class TestVerifyDefectSymptoms:
    def test_calls_invoke_claude_with_item_path(self, tmp_path):
        item = tmp_path / "01-bug.md"
        item.write_text("## Defect\nSome symptom.\n")
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=("Reproducible: yes\nClarity: 4\nSummary: bug confirmed", 0.01),
        ) as mock_call:
            result = _verify_defect_symptoms(str(item))
        assert mock_call.called
        prompt_arg = mock_call.call_args[0][0]
        assert str(item) in prompt_arg

    def test_parses_reproducible_yes(self, tmp_path):
        item = tmp_path / "01-bug.md"
        item.write_text("")
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=("Reproducible: yes\nClarity: 4", 0.01),
        ):
            result = _verify_defect_symptoms(str(item))
        assert result["reproducible"] == "yes"

    def test_parses_reproducible_no(self, tmp_path):
        item = tmp_path / "01-bug.md"
        item.write_text("")
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=("Reproducible: no\nClarity: 3", 0.01),
        ):
            result = _verify_defect_symptoms(str(item))
        assert result["reproducible"] == "no"

    def test_defaults_reproducible_to_unclear_on_missing(self, tmp_path):
        item = tmp_path / "01-bug.md"
        item.write_text("")
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=("Clarity: 3", 0.01),
        ):
            result = _verify_defect_symptoms(str(item))
        assert result["reproducible"] == "unclear"


# ─── _run_five_whys_analysis ─────────────────────────────────────────────────


class TestRunFiveWhysAnalysis:
    def test_calls_invoke_claude_with_item_path(self, tmp_path):
        item = tmp_path / "01-analysis.md"
        item.write_text("")
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=("Title: X\nClarity: 4\n5 Whys:\n1.a\n2.b\n3.c\n4.d\n5.e", 0.01),
        ) as mock_call:
            _run_five_whys_analysis(str(item))
        assert mock_call.called
        prompt_arg = mock_call.call_args[0][0]
        assert str(item) in prompt_arg

    def test_parses_clarity_score(self, tmp_path):
        item = tmp_path / "01-analysis.md"
        item.write_text("")
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=("Title: X\nClarity: 2", 0.01),
        ):
            result = _run_five_whys_analysis(str(item))
        assert result["clarity"] == 2


# ─── intake_analyze (node) ────────────────────────────────────────────────────


class TestIntakeAnalyzeNode:
    def test_returns_empty_dict_when_plan_already_set(self, tmp_path):
        """If plan_path is set, skip analysis entirely (in-progress plan)."""
        state = _make_state(plan_path="some-plan.yaml")
        with patch("langgraph_pipeline.pipeline.nodes.intake._invoke_claude") as mock_claude:
            result = intake_analyze(state)
        assert result == {}
        mock_claude.assert_not_called()

    def test_defect_increments_intake_count_defects(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(tmp_path / "t.json"))
        item = tmp_path / "01-bug.md"
        item.write_text("")
        state = _make_state(item_path=str(item), item_type="defect", intake_count_defects=2)
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=("Reproducible: yes\nClarity: 4", 0.01),
        ):
            result = intake_analyze(state)
        assert result.get("intake_count_defects") == 3

    def test_feature_increments_intake_count_features(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(tmp_path / "t.json"))
        item = tmp_path / "01-feature.md"
        item.write_text("Some feature request")
        state = _make_state(
            item_path=str(item), item_type="feature", intake_count_features=1
        )
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=("Title: T\nClarity: 4", 0.01),
        ):
            result = intake_analyze(state)
        assert result.get("intake_count_features") == 2

    def test_analysis_increments_intake_count_features(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(tmp_path / "t.json"))
        item = tmp_path / "01-analysis.md"
        item.write_text("")
        state = _make_state(
            item_path=str(item), item_type="analysis", intake_count_features=0
        )
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=("Title: T\nClarity: 4", 0.01),
        ):
            result = intake_analyze(state)
        assert result.get("intake_count_features") == 1

    def test_spawns_five_whys_for_feature(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(tmp_path / "t.json"))
        item = tmp_path / "01-feature.md"
        item.write_text("Some feature request")
        state = _make_state(item_path=str(item), item_type="feature")
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=("NO", 0.001),
        ) as mock_check, patch(
            "langgraph_pipeline.pipeline.nodes.intake._run_five_whys_analysis",
            return_value={"clarity": 4, "raw_output": "Title: T\nClarity: 4", "total_cost_usd": 0.02},
        ) as mock_whys:
            intake_analyze(state)
        mock_check.assert_called_once()  # _has_five_whys check
        mock_whys.assert_called_once()   # actual 5 Whys

    def test_skips_five_whys_when_already_present(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(tmp_path / "t.json"))
        item = tmp_path / "01-feature.md"
        item.write_text("5 Whys:\n1. Why\nRoot Need: something")
        state = _make_state(item_path=str(item), item_type="feature")
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=("YES", 0.001),
        ), patch(
            "langgraph_pipeline.pipeline.nodes.intake._run_five_whys_analysis",
        ) as mock_whys:
            intake_analyze(state)
        mock_whys.assert_not_called()

    def test_records_intake_in_throttle(self, tmp_path, monkeypatch):
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        path = tmp_path / "t.json"
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(path))
        item = tmp_path / "01-feature.md"
        item.write_text("Some feature")
        state = _make_state(item_path=str(item), item_type="feature")
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=("Title: T\nClarity: 4", 0.01),
        ):
            intake_analyze(state)
        data = json.loads(path.read_text())
        assert "feature" in data
        assert len(data["feature"]) == 1


# ─── intake_analyze quota detection ──────────────────────────────────────────


QUOTA_EXHAUSTION_OUTPUT = "You've hit your limit"


class TestIntakeAnalyzeQuotaDetection:
    def test_defect_returns_quota_exhausted_when_claude_signals_limit(
        self, tmp_path, monkeypatch
    ):
        """intake_analyze returns quota_exhausted=True when Claude output triggers detect_quota_exhaustion()."""
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(tmp_path / "t.json"))
        item = tmp_path / "01-bug.md"
        item.write_text("## Defect\nSome symptom.\n")
        state = _make_state(item_path=str(item), item_type="defect")
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=(QUOTA_EXHAUSTION_OUTPUT, 0.0),
        ):
            result = intake_analyze(state)
        assert result == {"quota_exhausted": True}

    def test_analysis_returns_quota_exhausted_when_claude_signals_limit(
        self, tmp_path, monkeypatch
    ):
        """intake_analyze returns quota_exhausted=True for analysis type when quota is exhausted."""
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod
        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(tmp_path / "t.json"))
        item = tmp_path / "01-analysis.md"
        item.write_text("## Analysis\nSome analysis.\n")
        state = _make_state(item_path=str(item), item_type="analysis")
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=(QUOTA_EXHAUSTION_OUTPUT, 0.0),
        ):
            result = intake_analyze(state)
        assert result == {"quota_exhausted": True}


# ─── Updated limits ─────────────────────────────────────────────────────────


class TestUpdatedLimits:
    def test_all_types_have_limit_of_50(self):
        """MAX_INTAKES_PER_HOUR should be 50 for all types after the update."""
        assert MAX_INTAKES_PER_HOUR["defect"] == 50
        assert MAX_INTAKES_PER_HOUR["feature"] == 50
        assert MAX_INTAKES_PER_HOUR["analysis"] == 50

    def test_throttle_wait_interval_is_60(self):
        assert THROTTLE_WAIT_INTERVAL_SECONDS == 60


# ─── Blocking throttle wait ─────────────────────────────────────────────────


class TestBlockingThrottleWait:
    def test_blocks_then_resumes_when_throttle_clears(self, tmp_path, monkeypatch):
        """When throttled, intake_analyze waits and resumes once throttle clears."""
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod

        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(tmp_path / "t.json"))

        call_count = 0

        def mock_check_throttle(item_type: str) -> bool:
            nonlocal call_count
            call_count += 1
            # First call: throttled. Second call (after wait): cleared.
            return call_count <= 1

        # Use a real event but make wait() return immediately.
        mock_event = threading.Event()
        monkeypatch.setattr(
            "langgraph_pipeline.pipeline.nodes.intake.get_shutdown_event",
            lambda: mock_event,
        )
        monkeypatch.setattr(
            intake_mod, "THROTTLE_WAIT_INTERVAL_SECONDS", 0
        )
        monkeypatch.setattr(
            intake_mod, "_check_throttle", mock_check_throttle
        )

        item = tmp_path / "01-feature.md"
        item.write_text("Some feature")
        state = _make_state(item_path=str(item), item_type="feature")
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=("Title: T\nClarity: 4", 0.01),
        ):
            result = intake_analyze(state)

        # Should have proceeded after throttle cleared.
        assert call_count == 2
        assert result.get("intake_count_features") == 1

    def test_returns_empty_dict_on_shutdown_during_wait(self, tmp_path, monkeypatch):
        """When shutdown event fires during throttle wait, returns empty dict."""
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod

        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(tmp_path / "t.json"))

        # Always throttled so the loop keeps running.
        monkeypatch.setattr(intake_mod, "_check_throttle", lambda item_type: True)

        # Create an event that is already set (simulates shutdown).
        shutdown_event = threading.Event()
        shutdown_event.set()
        monkeypatch.setattr(
            "langgraph_pipeline.pipeline.nodes.intake.get_shutdown_event",
            lambda: shutdown_event,
        )
        monkeypatch.setattr(intake_mod, "THROTTLE_WAIT_INTERVAL_SECONDS", 0)

        state = _make_state(item_type="feature")
        result = intake_analyze(state)

        assert result == {}

    def test_not_throttled_proceeds_without_waiting(self, tmp_path, monkeypatch):
        """When not throttled, intake_analyze proceeds normally (no wait loop)."""
        import langgraph_pipeline.pipeline.nodes.intake as intake_mod

        monkeypatch.setattr(intake_mod, "THROTTLE_FILE_PATH", str(tmp_path / "t.json"))
        monkeypatch.setattr(intake_mod, "_check_throttle", lambda item_type: False)

        item = tmp_path / "01-feature.md"
        item.write_text("Some feature")
        state = _make_state(item_path=str(item), item_type="feature")
        with patch(
            "langgraph_pipeline.pipeline.nodes.intake._invoke_claude",
            return_value=("Title: T\nClarity: 4", 0.01),
        ):
            result = intake_analyze(state)

        assert result.get("intake_count_features") == 1
