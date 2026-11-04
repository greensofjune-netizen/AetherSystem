from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
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
        flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        descriptor: int | None = None
        try:
            descriptor = os.open(self.output_path, flags, 0o600)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "a", encoding="utf-8") as log_file:
                descriptor = None
                log_file.write(frame.serialize_to_matrix() + "\n")
        except OSError:
            _LOGGER.exception("Failed to append telemetry to %s.", self.output_path)
            raise
        finally:
            if descriptor is not None:
                os.close(descriptor)


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
