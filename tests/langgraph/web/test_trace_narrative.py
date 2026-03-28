# tests/langgraph/web/test_trace_narrative.py
# Unit tests for the trace_narrative helper module.
# Design: docs/plans/2026-03-27-66-redesign-traces-page-for-usability-design.md

"""Tests for langgraph_pipeline.web.helpers.trace_narrative."""

import json

import pytest

from langgraph_pipeline.web.helpers.trace_narrative import (
    ExecutionView,
    PhaseArtifact,
    PhaseView,
    _artifact_label,
    _classify_phase,
    _extract_file_details,
    _extract_status,
    _format_activity_summary,
    _format_duration,
    build_execution_view,
)

# ─── Constants ────────────────────────────────────────────────────────────────

FIXTURE_RUN_ID = "aaaa-1111-bbbb-2222"
FIXTURE_CHILD_ID = "cccc-3333-dddd-4444"
FIXTURE_GRAND_ID = "eeee-5555-ffff-6666"
FIXTURE_SLUG = "test-feature-abc123"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_run(
    run_id: str = FIXTURE_RUN_ID,
    name: str = "pipeline",
    parent_run_id: str | None = None,
    start_time: str = "2026-03-27T10:00:00",
    end_time: str = "2026-03-27T10:01:30",
    error: str | None = None,
    metadata: dict | None = None,
    inputs: dict | None = None,
    outputs: dict | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "name": name,
        "parent_run_id": parent_run_id,
        "start_time": start_time,
        "end_time": end_time,
        "error": error,
        "metadata_json": json.dumps(metadata or {}),
        "inputs_json": json.dumps(inputs or {}),
        "outputs_json": json.dumps(outputs or {}),
        "model": "",
    }


# ─── Phase classification ─────────────────────────────────────────────────────


class TestClassifyPhase:
    def test_intake(self) -> None:
        assert _classify_phase("intake_task") == "Intake"

    def test_plan_creation(self) -> None:
        assert _classify_phase("plan_creation_node") == "Planning"

    def test_execute_plan(self) -> None:
        assert _classify_phase("execute_plan") == "Execution"

    def test_validate(self) -> None:
        assert _classify_phase("validate_output") == "Validation"

    def test_verification(self) -> None:
        assert _classify_phase("verification_step") == "Validation"

    def test_archive(self) -> None:
        assert _classify_phase("archive_item") == "Archival"

    def test_unknown_returns_unknown(self) -> None:
        assert _classify_phase("random_node") == "Unknown"

    def test_case_insensitive(self) -> None:
        assert _classify_phase("INTAKE") == "Intake"

    def test_execute_before_plan(self) -> None:
        # "execute_plan" pattern should hit "execute_plan" first, not "plan"
        assert _classify_phase("execute_plan") == "Execution"


# ─── Status extraction ────────────────────────────────────────────────────────


class TestExtractStatus:
    def test_error(self) -> None:
        run = _make_run(error="Something failed")
        assert _extract_status(run) == "error"

    def test_success(self) -> None:
        run = _make_run(end_time="2026-03-27T10:05:00")
        assert _extract_status(run) == "success"

    def test_running(self) -> None:
        run = _make_run(end_time=None)
        run["end_time"] = None
        assert _extract_status(run) == "running"

    def test_unknown(self) -> None:
        run = _make_run(start_time=None, end_time=None)
        run["start_time"] = None
        run["end_time"] = None
        assert _extract_status(run) == "unknown"


# ─── Duration formatting ──────────────────────────────────────────────────────


class TestFormatDuration:
    def test_seconds(self) -> None:
        result = _format_duration("2026-03-27T10:00:00", "2026-03-27T10:00:12.50")
        assert result == "12.50s"

    def test_minutes(self) -> None:
        result = _format_duration("2026-03-27T10:00:00", "2026-03-27T10:02:05")
        assert result == "2m 05s"

    def test_missing_timestamps(self) -> None:
        assert _format_duration(None, None) == "—"

    def test_negative_delta(self) -> None:
        assert _format_duration("2026-03-27T10:01:00", "2026-03-27T10:00:00") == "—"


# ─── Activity summary ─────────────────────────────────────────────────────────


class TestFormatActivitySummary:
    def test_empty(self) -> None:
        assert _format_activity_summary({}) == ""

    def test_single_read(self) -> None:
        result = _format_activity_summary({"Read": 1})
        assert result == "Read 1 file"

    def test_plural_reads(self) -> None:
        result = _format_activity_summary({"Read": 5})
        assert result == "Read 5 files"

    def test_mixed_tools(self) -> None:
        result = _format_activity_summary({"Read": 3, "Edit": 2, "Bash": 4})
        assert "Read 3 files" in result
        assert "edited 2" in result
        assert "ran 4 bash commands" in result

    def test_unknown_tool(self) -> None:
        result = _format_activity_summary({"NewTool": 7})
        assert "NewTool x7" in result


# ─── Artifact label ───────────────────────────────────────────────────────────


class TestArtifactLabel:
    def test_design_doc(self) -> None:
        assert _artifact_label("docs/plans/2026-03-27-foo-design.md") == "Design doc"

    def test_plan_yaml(self) -> None:
        assert _artifact_label("tmp/plans/66-foo.yaml") == "Plan YAML"

    def test_log_file(self) -> None:
        assert _artifact_label("logs/worker-output.txt") == "Log file"

    def test_fallback(self) -> None:
        assert _artifact_label("some/path/result.json") == "result.json"

    def test_no_slash(self) -> None:
        assert _artifact_label("result.json") == "result.json"


# ─── build_execution_view ─────────────────────────────────────────────────────


class TestBuildExecutionView:
    def test_basic_structure(self) -> None:
        root = _make_run(
            run_id=FIXTURE_RUN_ID,
            name="pipeline",
            metadata={"slug": FIXTURE_SLUG},
        )
        child = _make_run(
            run_id=FIXTURE_CHILD_ID,
            name="intake_task",
            parent_run_id=FIXTURE_RUN_ID,
        )
        view = build_execution_view(root, [child], {})

        assert isinstance(view, ExecutionView)
        assert view.item_slug == FIXTURE_SLUG
        assert len(view.phases) == 1
        assert view.phases[0].phase_name == "Intake"

    def test_slug_fallback_to_run_name(self) -> None:
        root = _make_run(run_id=FIXTURE_RUN_ID, name="my-pipeline", metadata={})
        view = build_execution_view(root, [], {})
        assert view.item_slug == "my-pipeline"

    def test_phase_ordering(self) -> None:
        root = _make_run(run_id=FIXTURE_RUN_ID, metadata={"slug": FIXTURE_SLUG})
        children = [
            _make_run(run_id="c1", name="validate_step", parent_run_id=FIXTURE_RUN_ID),
            _make_run(run_id="c2", name="intake_task", parent_run_id=FIXTURE_RUN_ID),
            _make_run(run_id="c3", name="execute_plan", parent_run_id=FIXTURE_RUN_ID),
        ]
        view = build_execution_view(root, children, {})
        phase_names = [p.phase_name for p in view.phases]
        assert phase_names == ["Intake", "Execution", "Validation"]

    def test_total_duration(self) -> None:
        root = _make_run(
            run_id=FIXTURE_RUN_ID,
            start_time="2026-03-27T10:00:00",
            end_time="2026-03-27T10:00:45",
            metadata={},
        )
        view = build_execution_view(root, [], {})
        assert view.total_duration == "45.00s"

    def test_total_cost_from_metadata(self) -> None:
        root = _make_run(
            run_id=FIXTURE_RUN_ID,
            metadata={"total_cost": 0.0237},
        )
        view = build_execution_view(root, [], {})
        assert view.total_cost == "$0.0237"

    def test_empty_cost_when_absent(self) -> None:
        root = _make_run(run_id=FIXTURE_RUN_ID, metadata={})
        view = build_execution_view(root, [], {})
        assert view.total_cost == ""

    def test_grandchildren_tool_counts(self) -> None:
        root = _make_run(run_id=FIXTURE_RUN_ID, metadata={})
        child = _make_run(
            run_id=FIXTURE_CHILD_ID,
            name="execute_plan",
            parent_run_id=FIXTURE_RUN_ID,
        )
        tool_use_block = {
            "type": "tool_use",
            "name": "Read",
            "input": {"file_path": "some/file.py"},
        }
        grandchild = _make_run(
            run_id=FIXTURE_GRAND_ID,
            parent_run_id=FIXTURE_CHILD_ID,
            outputs={
                "messages": [{"content": [tool_use_block]}]
            },
        )
        view = build_execution_view(root, [child], {FIXTURE_CHILD_ID: [grandchild]})
        assert len(view.phases) == 1
        assert "Read 1 file" in view.phases[0].activity_summary

    def test_error_status(self) -> None:
        root = _make_run(run_id=FIXTURE_RUN_ID, metadata={})
        child = _make_run(
            run_id=FIXTURE_CHILD_ID,
            name="validate_step",
            parent_run_id=FIXTURE_RUN_ID,
            error="Validation failed",
        )
        view = build_execution_view(root, [child], {})
        assert view.phases[0].status == "error"

    def test_phase_view_has_file_detail_fields(self) -> None:
        root = _make_run(run_id=FIXTURE_RUN_ID, metadata={})
        child = _make_run(run_id=FIXTURE_CHILD_ID, name="intake_task", parent_run_id=FIXTURE_RUN_ID)
        view = build_execution_view(root, [child], {})
        phase = view.phases[0]
        assert hasattr(phase, "files_read")
        assert hasattr(phase, "files_written")
        assert hasattr(phase, "bash_commands")
        assert isinstance(phase.files_read, list)
        assert isinstance(phase.files_written, list)
        assert isinstance(phase.bash_commands, list)


# ─── _extract_file_details ────────────────────────────────────────────────────


class TestExtractFileDetails:
    def _make_tool_use_run(self, tool_name: str, **inp_kwargs: str) -> dict:
        tool_use_block = {"type": "tool_use", "name": tool_name, "input": inp_kwargs}
        return _make_run(
            outputs={"messages": [{"content": [tool_use_block]}]}
        )

    def test_extracts_files_read(self) -> None:
        run = self._make_tool_use_run("Read", file_path="src/foo.py")
        files_read, files_written, bash_commands = _extract_file_details([run])
        assert files_read == ["src/foo.py"]
        assert files_written == []
        assert bash_commands == []

    def test_extracts_files_written_from_write(self) -> None:
        run = self._make_tool_use_run("Write", file_path="src/bar.py")
        files_read, files_written, _ = _extract_file_details([run])
        assert files_written == ["src/bar.py"]

    def test_extracts_files_written_from_edit(self) -> None:
        run = self._make_tool_use_run("Edit", file_path="src/baz.py")
        _, files_written, _ = _extract_file_details([run])
        assert files_written == ["src/baz.py"]

    def test_extracts_bash_commands(self) -> None:
        run = self._make_tool_use_run("Bash", command="pytest tests/ -v")
        _, _, bash_commands = _extract_file_details([run])
        assert bash_commands == ["pytest tests/ -v"]

    def test_deduplicates_across_runs(self) -> None:
        run1 = self._make_tool_use_run("Read", file_path="src/foo.py")
        run2 = self._make_tool_use_run("Read", file_path="src/foo.py")
        files_read, _, _ = _extract_file_details([run1, run2])
        assert files_read == ["src/foo.py"]

    def test_empty_runs(self) -> None:
        files_read, files_written, bash_commands = _extract_file_details([])
        assert files_read == []
        assert files_written == []
        assert bash_commands == []

    def test_ignores_non_tool_use_messages(self) -> None:
        run = _make_run(outputs={"messages": [{"content": [{"type": "text", "text": "hello"}]}]})
        files_read, files_written, bash_commands = _extract_file_details([run])
        assert files_read == []
        assert bash_commands == []


# ─── Duration computation (P11, P12 fixes) ────────────────────────────────────


class TestDurationFromGrandchildren:
    """Verify that near-zero and NULL-end_time spans are replaced with grandchild spans."""

    def test_phase_uses_grandchildren_when_child_near_zero(self) -> None:
        """P12: phase duration comes from grandchildren when child span is 0s."""
        root = _make_run(run_id=FIXTURE_RUN_ID, metadata={})
        child = _make_run(
            run_id=FIXTURE_CHILD_ID,
            name="execute_plan",
            parent_run_id=FIXTURE_RUN_ID,
            start_time="2026-03-27T10:00:00",
            end_time="2026-03-27T10:00:00",  # 0s — recording artifact
        )
        grandchild = _make_run(
            run_id=FIXTURE_GRAND_ID,
            parent_run_id=FIXTURE_CHILD_ID,
            start_time="2026-03-27T10:00:00",
            end_time="2026-03-27T10:07:30",  # real: 7m 30s
        )
        view = build_execution_view(root, [child], {FIXTURE_CHILD_ID: [grandchild]})
        assert view.phases[0].duration == "7m 30s"

    def test_phase_falls_back_to_child_when_grandchildren_have_null_end(self) -> None:
        """Phase falls back to child timestamps when all grandchildren have NULL end_time."""
        root = _make_run(run_id=FIXTURE_RUN_ID, metadata={})
        child = _make_run(
            run_id=FIXTURE_CHILD_ID,
            name="execute_plan",
            parent_run_id=FIXTURE_RUN_ID,
            start_time="2026-03-27T10:00:00",
            end_time="2026-03-27T10:05:00",  # 5 minutes
        )
        grandchild = _make_run(
            run_id=FIXTURE_GRAND_ID,
            parent_run_id=FIXTURE_CHILD_ID,
            start_time="2026-03-27T10:00:00",
            end_time=None,  # still running — no span available
        )
        view = build_execution_view(root, [child], {FIXTURE_CHILD_ID: [grandchild]})
        assert view.phases[0].duration == "5m 00s"

    def test_phase_falls_back_to_child_when_no_grandchildren(self) -> None:
        """Phase uses child timestamps when the phase has no grandchildren."""
        root = _make_run(run_id=FIXTURE_RUN_ID, metadata={})
        child = _make_run(
            run_id=FIXTURE_CHILD_ID,
            name="intake_task",
            parent_run_id=FIXTURE_RUN_ID,
            start_time="2026-03-27T10:00:00",
            end_time="2026-03-27T10:02:00",  # 2 minutes
        )
        view = build_execution_view(root, [child], {})
        assert view.phases[0].duration == "2m 00s"

    def test_total_uses_grandchildren_when_children_have_null_end(self) -> None:
        """P11: total duration falls back to grandchildren when child end_time is NULL."""
        root = _make_run(
            run_id=FIXTURE_RUN_ID,
            start_time="2026-03-27T10:00:00",
            end_time="2026-03-27T10:00:00",  # near-zero root
            metadata={},
        )
        child = _make_run(
            run_id=FIXTURE_CHILD_ID,
            name="execute_plan",
            parent_run_id=FIXTURE_RUN_ID,
            start_time="2026-03-27T10:00:00",
            end_time=None,  # NULL — child never recorded end
        )
        grandchild = _make_run(
            run_id=FIXTURE_GRAND_ID,
            parent_run_id=FIXTURE_CHILD_ID,
            start_time="2026-03-27T10:00:00",
            end_time="2026-03-27T10:05:00",  # real: 5 minutes
        )
        view = build_execution_view(root, [child], {FIXTURE_CHILD_ID: [grandchild]})
        assert view.total_duration == "5m 00s"

    def test_total_uses_grandchildren_when_children_near_zero(self) -> None:
        """P11: total duration falls back to grandchildren when child span is near-zero."""
        root = _make_run(
            run_id=FIXTURE_RUN_ID,
            start_time="2026-03-27T10:00:00",
            end_time="2026-03-27T10:00:00",
            metadata={},
        )
        child = _make_run(
            run_id=FIXTURE_CHILD_ID,
            name="execute_plan",
            parent_run_id=FIXTURE_RUN_ID,
            start_time="2026-03-27T10:00:00",
            end_time="2026-03-27T10:00:00",  # 0s — recording artifact
        )
        grandchild = _make_run(
            run_id=FIXTURE_GRAND_ID,
            parent_run_id=FIXTURE_CHILD_ID,
            start_time="2026-03-27T10:00:00",
            end_time="2026-03-27T10:08:00",  # real: 8 minutes
        )
        view = build_execution_view(root, [child], {FIXTURE_CHILD_ID: [grandchild]})
        assert view.total_duration == "8m 00s"

    def test_total_uses_children_when_span_is_real(self) -> None:
        """Total duration stays with children when the children span is >= 1s."""
        root = _make_run(run_id=FIXTURE_RUN_ID, metadata={})
        child = _make_run(
            run_id=FIXTURE_CHILD_ID,
            name="execute_plan",
            parent_run_id=FIXTURE_RUN_ID,
            start_time="2026-03-27T10:00:00",
            end_time="2026-03-27T10:03:00",  # 3 minutes
        )
        view = build_execution_view(root, [child], {})
        assert view.total_duration == "3m 00s"
