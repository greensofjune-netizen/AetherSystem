from __future__ import annotations

import logging
import os
import time

from .telemetry import OperationalTelemetryFrame, TelemetryLogRecorder

_LOGGER = logging.getLogger(__name__)


class OTelRuntimeLogger:
    """Write local runtime snapshots using the operational telemetry schema.

    The resource values emitted here are deterministic sample values, not
    measurements collected through the OpenTelemetry SDK.
    """

    def __init__(
        self,
        recorder: TelemetryLogRecorder | None = None,
    ) -> None:
        self.recorder = recorder or TelemetryLogRecorder()
        self.pid = os.getpid()
        _LOGGER.info("Runtime metrics tracking active under PID %s.", self.pid)

    def capture_and_log_cycle(
        self,
        sync_cycle: int,
        state_sig: str = "PRISTINE",
    ) -> OperationalTelemetryFrame:
        """Create and record one local telemetry frame."""
        if type(sync_cycle) is not int or sync_cycle < 1:
            raise ValueError("Sync cycle must be a positive integer.")
        if not isinstance(state_sig, str) or not state_sig.strip():
            raise ValueError("State signature cannot be empty.")

        is_even_cycle = sync_cycle % 2 == 0
        frame = OperationalTelemetryFrame(
            anchor_id="a7d2f4b1" if is_even_cycle else "e8b93c40",
            context_reasoning_effort="high",
            daemon_pid=self.pid,
            engine_state_signature=state_sig.strip(),
            history_resonance_score=12.606 if is_even_cycle else 8.452,
            input_sanitization_status="CLEANED",
            sync_cycle_count=sync_cycle,
            timestamp=time.time(),
        )
        self.recorder.record_heartbeat_snapshot(frame)
        return frame


if __name__ == "__main__":
    OTelRuntimeLogger().capture_and_log_cycle(sync_cycle=1)
