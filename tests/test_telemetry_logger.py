import json
from pathlib import Path

import pytest

from aether_engine.telemetry import TelemetryLogRecorder
from aether_engine.telemetry_logger import OTelRuntimeLogger


def test_runtime_logger_records_sample_frame(tmp_path: Path) -> None:
    metrics_file = tmp_path / "runtime-metrics.jsonl"
    logger = OTelRuntimeLogger(TelemetryLogRecorder(metrics_file))

    frame = logger.capture_and_log_cycle(2, " READY ")
    recorded = json.loads(metrics_file.read_text(encoding="utf-8").splitlines()[0])

    assert frame.daemon_pid == logger.pid
    assert frame.sync_cycle_count == 2
    assert frame.anchor_id == "a7d2f4b1"
    assert frame.history_resonance_score == 12.606
    assert frame.engine_state_signature == "READY"
    assert recorded["daemon_pid"] == logger.pid
    assert recorded["timestamp"] == frame.timestamp


@pytest.mark.parametrize("cycle", [0, -1, True, 1.5])
def test_runtime_logger_rejects_invalid_cycle(cycle: object, tmp_path: Path) -> None:
    metrics_file = tmp_path / "runtime-metrics.jsonl"
    logger = OTelRuntimeLogger(TelemetryLogRecorder(metrics_file))

    with pytest.raises(ValueError, match="positive integer"):
        logger.capture_and_log_cycle(cycle)  # type: ignore[arg-type]

    assert not metrics_file.exists()


def test_runtime_logger_rejects_empty_state_signature(tmp_path: Path) -> None:
    metrics_file = tmp_path / "runtime-metrics.jsonl"
    logger = OTelRuntimeLogger(TelemetryLogRecorder(metrics_file))

    with pytest.raises(ValueError, match="State signature cannot be empty"):
        logger.capture_and_log_cycle(1, " ")

    assert not metrics_file.exists()
