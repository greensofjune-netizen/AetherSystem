from __future__ import annotations

import logging
import math
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any


def configure_logging(log_path: str | Path = "aether_runtime.log") -> logging.Logger:
    logger = logging.getLogger("aether_engine.supervisor")
    if logger.handlers:
        return logger

    log_file = Path(log_path).expanduser()
    if log_file.is_symlink():
        raise ValueError(f"Runtime log path cannot be a symlink: {log_file}")
    flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(log_file, flags, 0o600)
    try:
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] AETHER-CORE: %(message)s"
    )
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    stream_handler = logging.StreamHandler(sys.stdout)
    for handler in (file_handler, stream_handler):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


class FluidHistorianCore:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.registry: dict[str, dict[str, Any]] = {}
        self.logger = logger or logging.getLogger("aether_engine.supervisor")
        self.logger.info("Seamless Co-Pilot Historian Production Axis Online.")

    def imprint_state_vector(
        self, topic: str, tags: list[str], weight: float = 1.0
    ) -> str:
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError("Topic cannot be empty.")
        if (
            isinstance(weight, bool)
            or not isinstance(weight, (int, float))
            or not math.isfinite(weight)
            or weight < 0
        ):
            raise ValueError("Weight must be a finite, non-negative number.")
        normalized_tags = self._normalize_tags(tags, "Tags")

        normalized_topic = topic.strip()
        token = uuid.uuid4().hex
        self.registry[token] = {
            "topic": normalized_topic,
            "tags": normalized_tags,
            "weight": float(weight),
            "timestamp": time.time(),
        }
        self.logger.info(
            "Topological anchor imprinted -> token: %s | field: %s",
            token,
            normalized_topic,
        )
        return token

    def compute_fluid_resonance(
        self, active_stream_tags: list[str]
    ) -> list[dict[str, Any]]:
        active_tags = self._normalize_tags(active_stream_tags, "Active stream tags")

        now = time.time()
        resonance_matrix = []

        for token, data in self.registry.items():
            elapsed = max(0.0, now - data["timestamp"])
            matches = len(data["tags"].intersection(active_tags))
            score = (
                data["weight"] * matches * 2.5
                + 0.5 / (1.0 + math.log1p(elapsed))
            )
            resonance_matrix.append(
                {
                    "token": token,
                    "topic": data["topic"],
                    "resonance": round(score, 4),
                }
            )

        resonance_matrix.sort(key=lambda item: item["resonance"], reverse=True)
        return resonance_matrix

    @staticmethod
    def _normalize_tags(values: object, label: str) -> set[str]:
        if not isinstance(values, (list, tuple)):
            raise ValueError(f"{label} must be a list of non-empty strings.")
        if any(not isinstance(tag, str) or not tag.strip() for tag in values):
            raise ValueError(f"{label} must be a list of non-empty strings.")
        return {tag.strip() for tag in values}


class SystemSupervisor:
    def __init__(
        self,
        engine: FluidHistorianCore,
        *,
        workspace_root: str | Path | None = None,
        heartbeat_seconds: float = 10.0,
        maintenance_interval_seconds: float = 300.0,
        logger: logging.Logger | None = None,
    ) -> None:
        if not math.isfinite(heartbeat_seconds) or heartbeat_seconds <= 0:
            raise ValueError("Heartbeat interval must be a finite, positive number.")
        if (
            not math.isfinite(maintenance_interval_seconds)
            or maintenance_interval_seconds <= 0
        ):
            raise ValueError(
                "Maintenance interval must be a finite, positive number."
            )
        self.engine = engine
        self.workspace_root = Path(
            workspace_root or Path.cwd()
        ).expanduser().resolve()
        self.heartbeat_seconds = heartbeat_seconds
        self.maintenance_interval_seconds = maintenance_interval_seconds
        self.logger = logger or engine.logger
        self._stop_event = threading.Event()

    @property
    def is_running(self) -> bool:
        return not self._stop_event.is_set()

    def stop(self) -> None:
        self._stop_event.set()

    def execute_maintenance_sweep(self) -> int:
        """Run a read-only Ruff lint check without modifying project files."""
        ruff = shutil.which("ruff")
        if ruff is None:
            self.logger.warning("Maintenance lint check skipped: Ruff is not installed.")
            return 127

        try:
            result = subprocess.run(
                [ruff, "check", "--output-format", "concise", "."],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            self.logger.error("Maintenance lint check timed out.")
            return 124
        except OSError as error:
            self.logger.error("Could not run Ruff lint check: %s", error)
            return 127

        if result.returncode:
            detail = (result.stdout + result.stderr).strip()
            self.logger.warning(
                "Maintenance lint check found issues (exit %s): %s",
                result.returncode,
                detail or "no diagnostic output",
            )
        else:
            self.logger.info("Read-only maintenance lint check passed.")
        return result.returncode

    def run_forever(self) -> None:
        self.logger.info("=" * 66)
        self.logger.info("AETHER CORE: SYSTEM SUPERVISOR PROFILER ACTIVE")
        self.logger.info("=" * 66)

        try:
            self.engine.imprint_state_vector(
                "Master Telemetry Equilibrium Array",
                ["telemetry", "equilibrium"],
                3.0,
            )
            self.engine.imprint_state_vector(
                "Hardened Off-Machine Storage Mirror",
                ["backup", "infrastructure"],
                2.5,
            )

            cycle = 1
            last_maintenance = 0.0
            simulated_streams = [
                ["telemetry"],
                ["backup", "infrastructure"],
                ["equilibrium"],
            ]

            while not self._stop_event.is_set():
                active_tags = simulated_streams[(cycle - 1) % len(simulated_streams)]
                self.logger.info(
                    "[CYCLE #%s] Intercepting active telemetry tags: %s",
                    cycle,
                    active_tags,
                )
                matrix = self.engine.compute_fluid_resonance(active_tags)
                if matrix:
                    top_vector = matrix[0]
                    self.logger.info(
                        "Resonant node: %s (score: %s)",
                        top_vector["topic"],
                        top_vector["resonance"],
                    )

                now = time.monotonic()
                if now - last_maintenance >= self.maintenance_interval_seconds:
                    self.execute_maintenance_sweep()
                    last_maintenance = now
                cycle += 1
                self._stop_event.wait(self.heartbeat_seconds)
        except KeyboardInterrupt:
            self.logger.info("Shutdown signal captured; stopping supervisor.")
        except Exception:
            self.logger.exception("Unexpected supervisor failure.")
            raise
        finally:
            self.stop()


def main() -> int:
    logger = configure_logging()
    if sys.base_prefix == sys.prefix:
        logger.error(
            "Run this module inside the project virtual environment. "
            "A virtual environment is not a security sandbox."
        )
        return 1

    core_engine = FluidHistorianCore(logger)
    supervisor = SystemSupervisor(core_engine, logger=logger)
    previous_handlers = {}

    def request_shutdown(_signum: int, _frame: Any) -> None:
        supervisor.stop()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.signal(signum, request_shutdown)
    try:
        supervisor.run_forever()
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())