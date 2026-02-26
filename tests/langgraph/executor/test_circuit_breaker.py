# tests/langgraph/executor/test_circuit_breaker.py
# Unit tests for the circuit breaker module.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Tests for langgraph_pipeline.executor.circuit_breaker."""

import pytest

from langgraph_pipeline.executor.circuit_breaker import (
    DEFAULT_FAILURE_THRESHOLD,
    is_circuit_open,
    record_failure,
    reset_failures,
)


class TestDefaultThreshold:
    """The default failure threshold constant has the correct value."""

    def test_default_threshold_is_three(self):
        assert DEFAULT_FAILURE_THRESHOLD == 3


class TestIsCircuitOpen:
    """is_circuit_open returns True only when threshold is reached or exceeded."""

    def test_zero_failures_circuit_closed(self):
        assert is_circuit_open(0) is False

    def test_one_failure_circuit_closed(self):
        assert is_circuit_open(1) is False

    def test_two_failures_circuit_closed(self):
        assert is_circuit_open(2) is False

    def test_at_threshold_circuit_open(self):
        assert is_circuit_open(DEFAULT_FAILURE_THRESHOLD) is True

    def test_above_threshold_circuit_open(self):
        assert is_circuit_open(DEFAULT_FAILURE_THRESHOLD + 1) is True

    def test_custom_threshold_respected(self):
        assert is_circuit_open(2, threshold=2) is True
        assert is_circuit_open(1, threshold=2) is False

    def test_threshold_of_one_opens_on_first_failure(self):
        assert is_circuit_open(1, threshold=1) is True
        assert is_circuit_open(0, threshold=1) is False


class TestRecordFailure:
    """record_failure increments the consecutive failure counter."""

    def test_increments_from_zero(self):
        assert record_failure(0) == 1

    def test_increments_from_one(self):
        assert record_failure(1) == 2

    def test_increments_beyond_threshold(self):
        assert record_failure(DEFAULT_FAILURE_THRESHOLD) == DEFAULT_FAILURE_THRESHOLD + 1

    def test_does_not_mutate_input(self):
        initial = 2
        result = record_failure(initial)
        assert initial == 2
        assert result == 3


class TestResetFailures:
    """reset_failures returns zero regardless of the current count."""

    def test_reset_from_nonzero(self):
        assert reset_failures() == 0

    def test_reset_is_idempotent(self):
        assert reset_failures() == reset_failures()
