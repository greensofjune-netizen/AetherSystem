import json
from pathlib import Path
from types import SimpleNamespace

from aether_engine.telemetry import (
    OperationalTelemetryFrame,
    SystemTelemetryLogger,
    TelemetryLogRecorder,
)


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


def test_system_logger_records_events_and_analyzes_anomalies(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    event_file = tmp_path / "events.jsonl"
    recorder = TelemetryLogRecorder(event_file)
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *, host: str) -> None:
            captured["host"] = host

        def generate(self, **options: object) -> SimpleNamespace:
            captured["options"] = options
            return SimpleNamespace(response="Check the configured path.")

    monkeypatch.setattr(
        "aether_engine.telemetry.import_module",
        lambda name: SimpleNamespace(Client=FakeClient),
    )
    logger = SystemTelemetryLogger(recorder=recorder)

    with caplog.at_level("INFO", logger="aether_engine.telemetry"):
        logger.log_execution_event(
            "Pipeline calibration",
            "EXCEPTION",
            {"error": "Path mismatch"},
        )

    event = json.loads(event_file.read_text(encoding="utf-8").splitlines()[0])
    assert event == {
        "event": "Pipeline calibration",
        "status": "EXCEPTION",
        "telemetry_data": {"error": "Path mismatch"},
    }
    assert event_file.stat().st_mode & 0o777 == 0o600
    assert captured["host"] == "http://127.0.0.1:11434"
    options = captured["options"]
    assert isinstance(options, dict)
    assert options["model"] == "aethersystem-core"
    assert "Path mismatch" in options["prompt"]
    assert "Check the configured path." in caplog.text


def test_system_logger_keeps_recorded_event_when_ollama_is_offline(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    event_file = tmp_path / "events.jsonl"

    def missing_ollama(_name: str) -> object:
        raise ConnectionError("Ollama is offline")

    monkeypatch.setattr(
        "aether_engine.telemetry.import_module",
        missing_ollama,
    )
    logger = SystemTelemetryLogger(recorder=TelemetryLogRecorder(event_file))

    with caplog.at_level("WARNING", logger="aether_engine.telemetry"):
        logger.log_execution_event("Job", "EXCEPTION", {})

    assert json.loads(event_file.read_text(encoding="utf-8"))["event"] == "Job"
    assert "event remains recorded" in caplog.text


def test_system_logger_does_not_query_ollama_for_normal_events(
    tmp_path: Path, monkeypatch
) -> None:
    event_file = tmp_path / "events.jsonl"

    def unexpected_ollama_import(_name: str) -> object:
        raise AssertionError("Normal events must not query Ollama.")

    monkeypatch.setattr(
        "aether_engine.telemetry.import_module",
        unexpected_ollama_import,
    )
    logger = SystemTelemetryLogger(recorder=TelemetryLogRecorder(event_file))

    logger.log_execution_event("Job", "SUCCESS", {"completed": True})

    assert json.loads(event_file.read_text(encoding="utf-8"))["status"] == "SUCCESS"
