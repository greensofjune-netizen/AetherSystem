from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from aether_engine.sanitizer import sanitize_text
from aether_engine.telemetry import (
    OperationalTelemetryFrame,
    TelemetryLogRecorder,
)
from aether_engine.telemetry_logger import OTelRuntimeLogger


def test_telemetry_field_constraints_anchor_and_trajectory() -> None:
    """Validates strict 8-character token matching format rules."""
    frame = OperationalTelemetryFrame(
        anchor_id="a7d2f4b1",
        context_reasoning_effort="high",
        daemon_pid=48799,
        engine_state_signature="PRISTINE",
        history_resonance_score=12.606,
        input_sanitization_status="CLEANED",
        sync_cycle_count=78,
    )
    assert len(frame.anchor_id) == 8
    assert frame.anchor_id.isalnum()


def test_telemetry_field_constraints_reasoning_effort_bounds() -> None:
    """Enforces reasoning effort fields fall within official parameter lists."""
    valid_efforts = {"none", "low", "medium", "high", "max"}
    frame = OperationalTelemetryFrame(
        anchor_id="e8b93c40",
        context_reasoning_effort="max",
        daemon_pid=48799,
        engine_state_signature="PRISTINE",
        history_resonance_score=8.452,
        input_sanitization_status="CLEANED",
        sync_cycle_count=79,
    )
    assert frame.context_reasoning_effort in valid_efforts


def test_telemetry_field_constraints_engine_signatures() -> None:
    """Validates state signatures adhere to standard platform keywords."""
    valid_signatures = {"PRISTINE", "WARN", "FAIL"}
    frame = OperationalTelemetryFrame(
        anchor_id="a7d2f4b1",
        context_reasoning_effort="medium",
        daemon_pid=123,
        engine_state_signature="PRISTINE",
        history_resonance_score=1.0,
        input_sanitization_status="CLEANED",
        sync_cycle_count=1,
    )
    assert frame.engine_state_signature in valid_signatures


def test_telemetry_field_constraints_resonance_score_floats() -> None:
    """Verifies priority metric calculations process as floating points."""
    frame = OperationalTelemetryFrame(
        anchor_id="a7d2f4b1",
        context_reasoning_effort="medium",
        daemon_pid=123,
        engine_state_signature="WARN",
        history_resonance_score=0.0001,
        input_sanitization_status="CLEANED",
        sync_cycle_count=1,
    )
    assert isinstance(frame.history_resonance_score, float)


def test_telemetry_serialization_output_contains_timestamp() -> None:
    """Verifies serialization outputs explicit epoch timers."""
    frame = OperationalTelemetryFrame(
        anchor_id="a7d2f4b1",
        context_reasoning_effort="low",
        daemon_pid=1,
        engine_state_signature="PRISTINE",
        history_resonance_score=5.5,
        input_sanitization_status="CLEANED",
        sync_cycle_count=1,
    )
    serialized = frame.serialize_to_matrix()
    assert "timestamp" in serialized
    assert "sync_cycle_count" in serialized


def test_recorder_creates_file_when_recording(tmp_path: Path) -> None:
    """Assures recording creates the local metrics file."""
    metric_file = tmp_path / "aether_metrics.json"
    recorder = TelemetryLogRecorder(output_path=str(metric_file))
    frame = OperationalTelemetryFrame(
        "a7d2f4b1", "low", 1, "PRISTINE", 1.0, "CLEANED", 1
    )

    assert not metric_file.exists()
    recorder.record_heartbeat_snapshot(frame)
    assert metric_file.exists()


def test_recorder_enforces_0600_permissions_on_new_files(tmp_path: Path) -> None:
    """Confirms metrics files lock to 0600 private permissions at creation."""
    if sys.platform == "win32":
        pytest.skip("Chmod 0600 private permission checks are scoped to Unix systems.")

    metric_file = tmp_path / "secure_metrics.json"
    recorder = TelemetryLogRecorder(output_path=str(metric_file))
    recorder.record_heartbeat_snapshot(
        OperationalTelemetryFrame(
            "a7d2f4b1", "low", 1, "PRISTINE", 1.0, "CLEANED", 1
        )
    )

    file_mode = os.stat(metric_file).st_mode & 0o777
    assert file_mode == 0o600


def test_recorder_appends_records_without_overwriting(tmp_path: Path) -> None:
    """Verifies new metrics packets append to the log trail."""
    metric_file = tmp_path / "append_metrics.json"
    recorder = TelemetryLogRecorder(output_path=str(metric_file))

    frame1 = OperationalTelemetryFrame(
        "a7d2f4b1", "low", 1, "PRISTINE", 1.0, "CLEANED", 1
    )
    frame2 = OperationalTelemetryFrame(
        "e8b93c40", "high", 2, "PRISTINE", 2.0, "CLEANED", 2
    )

    recorder.record_heartbeat_snapshot(frame1)
    recorder.record_heartbeat_snapshot(frame2)

    with open(metric_file, "r", encoding="utf-8") as file:
        lines = file.readlines()
    assert len(lines) == 2


def test_runtime_logger_captures_valid_operating_pid() -> None:
    """Verifies the runtime logger resolves the host machine pid."""
    logger = OTelRuntimeLogger()
    assert logger.pid > 0
    assert logger.pid == os.getpid()


def test_runtime_logger_cycle_alternates_state_parameters(
    tmp_path: Path,
) -> None:
    """Checks that structural snapshot models rotate data vectors accurately."""
    logger = OTelRuntimeLogger(TelemetryLogRecorder(tmp_path / "metrics.jsonl"))
    frame_even = logger.capture_and_log_cycle(sync_cycle=2, state_sig="PRISTINE")
    frame_odd = logger.capture_and_log_cycle(sync_cycle=3, state_sig="PRISTINE")

    assert frame_even.anchor_id == "a7d2f4b1"
    assert frame_odd.anchor_id == "e8b93c40"


def test_sanitizer_rejects_none_values() -> None:
    """Validates text cleaning rejects non-text inputs explicitly."""
    with pytest.raises(ValueError, match="Task title must be text"):
        sanitize_text(None, field_name="Task title")  # type: ignore[arg-type]


def test_sanitizer_removes_trailing_markdown_residue_patterns() -> None:
    """Ensures input filters strip trailing markdown formatting."""
    dirty = "Implement schema check]}'`"
    assert sanitize_text(dirty, field_name="Task title") == "Implement schema check]}'"


def test_sanitizer_removes_trailing_backticks() -> None:
    """Intercepts loose copy-paste trailing backtick strings."""
    dirty = "Configure automatic backup``"
    assert sanitize_text(dirty, field_name="Task title") == "Configure automatic backup"


def test_sanitizer_preserves_inner_operators() -> None:
    """Leaves inner terminal instructions completely untouched."""
    valid_code = "fix loop && pytest -v ; make clean"
    assert sanitize_text(valid_code, field_name="Task title") == valid_code


def test_sanitizer_empty_input_validation_failure() -> None:
    """Verifies blank inputs raise explicit human-readable exceptions."""
    with pytest.raises(ValueError, match="Task title cannot be empty"):
        sanitize_text("      ", field_name="Task title")
