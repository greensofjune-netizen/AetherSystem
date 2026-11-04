import json
from pathlib import Path

from aether_engine.telemetry import OperationalTelemetryFrame, TelemetryLogRecorder


def test_telemetry_frame_serialization_and_permissions(tmp_path: Path) -> None:
    """Verify telemetry is serialized as JSONL and stored with private permissions."""
    metric_file = tmp_path / "test_metrics.json"
    recorder = TelemetryLogRecorder(output_path=metric_file)

    frame = OperationalTelemetryFrame(
        anchor_id="e8b93c40",
        context_reasoning_effort="max",
        daemon_pid=12345,
        engine_state_signature="PRISTINE",
        history_resonance_score=8.452,
        input_sanitization_status="CLEANED",
        sync_cycle_count=1,
    )

    recorder.record_heartbeat_snapshot(frame)

    assert metric_file.exists()
    data = json.loads(metric_file.read_text(encoding="utf-8").splitlines()[0])
    assert data["anchor_id"] == "e8b93c40"
    assert data["context_reasoning_effort"] == "max"
    assert data["timestamp"] == frame.timestamp
    assert metric_file.stat().st_mode & 0o777 == 0o600
