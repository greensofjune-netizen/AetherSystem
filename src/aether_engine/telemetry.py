from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from importlib import import_module
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class OperationalTelemetryFrame:
    """A timestamped snapshot of operational engine metrics."""

    anchor_id: str
    context_reasoning_effort: str
    daemon_pid: int
    engine_state_signature: str
    history_resonance_score: float
    input_sanitization_status: str
    sync_cycle_count: int
    timestamp: float = field(default_factory=time.time)

    def serialize_to_matrix(self) -> str:
        """Serialize this frame as a compact JSON object."""
        return json.dumps(asdict(self), separators=(",", ":"), ensure_ascii=False)


class TelemetryLogRecorder:
    def __init__(self, output_path: str | Path = "aether_metrics.json") -> None:
        self.output_path = Path(output_path).expanduser()

    def record_heartbeat_snapshot(
        self, frame: OperationalTelemetryFrame
    ) -> None:
        """Append a telemetry frame as one JSON line in a private local file."""
        self._append_json_line(frame.serialize_to_matrix())

    def record_execution_event(
        self,
        event_name: str,
        status: str,
        details: dict[str, object],
    ) -> dict[str, object]:
        """Append one execution event as JSONL and return its recorded payload."""
        payload: dict[str, object] = {
            "event": event_name,
            "status": status,
            "telemetry_data": details,
        }
        serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        self._append_json_line(serialized)
        return payload

    def _append_json_line(self, serialized: str) -> None:
        """Append a JSON line while keeping the local telemetry file private."""
        flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        descriptor: int | None = None
        try:
            descriptor = os.open(self.output_path, flags, 0o600)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "a", encoding="utf-8") as log_file:
                descriptor = None
                log_file.write(serialized + "\n")
        except OSError:
            _LOGGER.exception("Failed to append telemetry to %s.", self.output_path)
            raise
        finally:
            if descriptor is not None:
                os.close(descriptor)


class SystemTelemetryLogger:
    """Record execution events and ask a local Ollama model about anomalies."""

    def __init__(
        self,
        core_model: str = "aethersystem-core",
        recorder: TelemetryLogRecorder | None = None,
    ) -> None:
        self.model = core_model
        self.recorder = recorder or TelemetryLogRecorder("aether_events.jsonl")
        _LOGGER.info("System logger bound to local model %r.", self.model)

    def log_execution_event(
        self,
        event_name: str,
        status: str,
        details: dict[str, object],
    ) -> None:
        """Persist an event and request local analysis when it signals an anomaly."""
        payload = self.recorder.record_execution_event(event_name, status, details)
        _LOGGER.info("Processing event %s -> [%s].", event_name, status)
        if status != "EXCEPTION" and "error" not in details:
            return

        analysis_prompt = (
            "Analyze this operational anomaly using our system protocols: "
            f"{json.dumps(payload, ensure_ascii=False)}. Outline how this "
            "calibration data step builds future validation resilience."
        )
        try:
            ollama = import_module("ollama")
            client = ollama.Client(host="http://127.0.0.1:11434")
            response = client.generate(
                model=self.model,
                prompt=analysis_prompt,
                options={"temperature": 0.2},
            )
            _LOGGER.info(
                "Historian remediation insights:\n%s",
                response.response.strip(),
            )
        except Exception as error:
            _LOGGER.warning(
                "Local Ollama unavailable; event remains recorded at %s: %s",
                self.recorder.output_path,
                error,
            )


if __name__ == "__main__":
    recorder = TelemetryLogRecorder()
    sample_frame = OperationalTelemetryFrame(
        anchor_id="a7d2f4b1",
        context_reasoning_effort="high",
        daemon_pid=os.getpid(),
        engine_state_signature="PRISTINE",
        history_resonance_score=12.606,
        input_sanitization_status="CLEANED",
        sync_cycle_count=78,
    )
    recorder.record_heartbeat_snapshot(sample_frame)
