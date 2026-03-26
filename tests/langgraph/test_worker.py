# tests/langgraph/test_worker.py
# Unit tests for langgraph_pipeline/worker.py: initial state construction and thread_config building.
# Design: docs/plans/2026-03-26-02-traces-runs-named-langgraph-design.md

"""Unit tests for the worker subprocess (langgraph_pipeline.worker)."""

from unittest.mock import MagicMock, patch

from langgraph_pipeline.worker import _build_initial_state


# ─── _build_initial_state ─────────────────────────────────────────────────────


def test_build_initial_state_fields():
    """_build_initial_state populates all expected PipelineState fields."""
    state = _build_initial_state(
        item_path="docs/feature-backlog/01-my-feature.md",
        item_type="feature",
        item_slug="01-my-feature",
    )

    assert state["item_path"] == "docs/feature-backlog/01-my-feature.md"
    assert state["item_slug"] == "01-my-feature"
    assert state["item_type"] == "feature"
    assert state["item_name"] == "01 My Feature"
    assert state["plan_path"] is None
    assert state["design_doc_path"] is None
    assert state["verification_cycle"] == 0
    assert state["verification_history"] == []
    assert state["should_stop"] is False
    assert state["rate_limited"] is False
    assert state["rate_limit_reset"] is None
    assert state["quota_exhausted"] is False
    assert state["budget_cap_usd"] is None
    assert state["session_cost_usd"] == 0.0
    assert state["session_input_tokens"] == 0
    assert state["session_output_tokens"] == 0
    assert state["intake_count_defects"] == 0
    assert state["intake_count_features"] == 0


# ─── thread_config with run_name ──────────────────────────────────────────────


def _invoke_main_and_capture_thread_config(item_slug: str) -> dict:
    """Run worker.main() with a given item_slug and return the thread_config passed to graph.invoke."""
    captured = {}

    mock_graph = MagicMock()

    def fake_invoke(state, config):
        captured["thread_config"] = config
        return {
            "session_cost_usd": 0.0,
            "session_input_tokens": 0,
            "session_output_tokens": 0,
            "quota_exhausted": False,
            "should_stop": False,
        }

    mock_graph.invoke = fake_invoke

    mock_context = MagicMock()
    mock_context.__enter__ = MagicMock(return_value=mock_graph)
    mock_context.__exit__ = MagicMock(return_value=False)

    cli_args = [
        "--item-path", "docs/feature-backlog/01-test.md",
        "--result-file", "/tmp/worker-test-result.json",
        "--item-slug", item_slug,
    ]

    with (
        patch("langgraph_pipeline.worker.pipeline_graph", return_value=mock_context),
        patch("langgraph_pipeline.worker.load_dotenv_files"),
        patch("langgraph_pipeline.worker._write_result"),
        patch("langgraph_pipeline.worker._cleanup_worker_db"),
        patch("sys.argv", ["worker"] + cli_args),
    ):
        import langgraph_pipeline.worker as worker_mod
        worker_mod.main()

    return captured.get("thread_config", {})


def test_thread_config_includes_run_name_when_slug_non_empty():
    """thread_config includes run_name when item_slug is non-empty."""
    thread_config = _invoke_main_and_capture_thread_config("01-my-feature")

    assert "run_name" in thread_config
    assert thread_config["run_name"] == "01-my-feature"


def test_thread_config_omits_run_name_when_slug_empty():
    """thread_config omits run_name when item_slug is empty."""
    thread_config = _invoke_main_and_capture_thread_config("")

    assert "run_name" not in thread_config


def test_thread_config_always_has_configurable_thread_id():
    """thread_config always contains configurable.thread_id regardless of slug."""
    thread_config = _invoke_main_and_capture_thread_config("any-slug")

    assert "configurable" in thread_config
    assert "thread_id" in thread_config["configurable"]
