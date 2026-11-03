import logging
import os
import subprocess

import pytest

from aether_engine.supervisor import (
    FluidHistorianCore,
    SystemSupervisor,
    configure_logging,
)


def test_core_orders_resonance_by_matching_weight() -> None:
    logger = logging.getLogger("test.supervisor.core")
    core = FluidHistorianCore(logger)

    core.imprint_state_vector("Telemetry", ["telemetry"], weight=2.0)
    core.imprint_state_vector("Backup", ["backup"], weight=1.0)

    matrix = core.compute_fluid_resonance(["telemetry"])

    assert matrix[0]["topic"] == "Telemetry"
    assert matrix[0]["resonance"] > matrix[1]["resonance"]
    assert len({item["token"] for item in matrix}) == 2


def test_core_validates_state_vectors_and_active_tags() -> None:
    core = FluidHistorianCore(logging.getLogger("test.supervisor.validation"))

    with pytest.raises(ValueError, match="Topic cannot be empty"):
        core.imprint_state_vector("  ", ["tag"])
    with pytest.raises(ValueError, match="finite, non-negative"):
        core.imprint_state_vector("topic", ["tag"], weight=float("inf"))
    with pytest.raises(ValueError, match="finite, non-negative"):
        core.imprint_state_vector("topic", ["tag"], weight="heavy")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="list of non-empty strings"):
        core.imprint_state_vector("topic", None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty strings"):
        core.imprint_state_vector("topic", [" "])
    with pytest.raises(ValueError, match="non-empty strings"):
        core.compute_fluid_resonance([""])


def test_configure_logging_adds_file_and_stream_handlers(tmp_path) -> None:
    logger = logging.getLogger("aether_engine.supervisor")
    for handler in logger.handlers:
        logger.removeHandler(handler)
        handler.close()

    log_path = tmp_path / "runtime.log"
    configured = configure_logging(log_path)

    assert configured is logger
    assert log_path.exists()
    assert len(logger.handlers) == 2
    if os.name != "nt":
        assert log_path.stat().st_mode & 0o777 == 0o600

    for handler in logger.handlers:
        logger.removeHandler(handler)
        handler.close()


def test_configure_logging_refuses_symlink_destination(tmp_path) -> None:
    logger = logging.getLogger("aether_engine.supervisor")
    for handler in logger.handlers:
        logger.removeHandler(handler)
        handler.close()

    target = tmp_path / "target.log"
    target.write_text("preserve", encoding="utf-8")
    log_path = tmp_path / "runtime.log"
    log_path.symlink_to(target)

    with pytest.raises(ValueError, match="cannot be a symlink"):
        configure_logging(log_path)
    assert target.read_text(encoding="utf-8") == "preserve"


def test_maintenance_sweep_runs_ruff_without_mutation(
    tmp_path, monkeypatch
) -> None:
    logger = logging.getLogger("test.supervisor.maintenance")
    core = FluidHistorianCore(logger)
    supervisor = SystemSupervisor(
        core, workspace_root=tmp_path, logger=logger
    )
    commands: list[list[str]] = []

    monkeypatch.setattr("aether_engine.supervisor.shutil.which", lambda _: "/ruff")

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        assert kwargs["cwd"] == tmp_path
        assert kwargs["check"] is False
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("aether_engine.supervisor.subprocess.run", fake_run)

    assert supervisor.execute_maintenance_sweep() == 0
    assert commands == [["/ruff", "check", "--output-format", "concise", "."]]


def test_supervisor_stops_after_requested_cycle(tmp_path, monkeypatch) -> None:
    logger = logging.getLogger("test.supervisor.loop")
    core = FluidHistorianCore(logger)
    supervisor = SystemSupervisor(
        core,
        workspace_root=tmp_path,
        heartbeat_seconds=0.01,
        logger=logger,
    )
    cycles = 0

    def stop_after_first_cycle() -> int:
        nonlocal cycles
        cycles += 1
        supervisor.stop()
        return 0

    monkeypatch.setattr(supervisor, "execute_maintenance_sweep", stop_after_first_cycle)
    supervisor.run_forever()

    assert cycles == 1
    assert not supervisor.is_running


def test_supervisor_runs_maintenance_only_at_configured_interval(
    tmp_path, monkeypatch
) -> None:
    logger = logging.getLogger("test.supervisor.maintenance-interval")
    core = FluidHistorianCore(logger)
    supervisor = SystemSupervisor(
        core,
        workspace_root=tmp_path,
        heartbeat_seconds=0.01,
        maintenance_interval_seconds=100,
        logger=logger,
    )
    cycles = 0
    maintenance_runs = 0

    def maintenance() -> int:
        nonlocal maintenance_runs
        maintenance_runs += 1
        return 0

    def stop_after_three_cycles(_seconds: float) -> bool:
        nonlocal cycles
        cycles += 1
        if cycles == 3:
            supervisor.stop()
        return supervisor.is_running

    monkeypatch.setattr(supervisor, "execute_maintenance_sweep", maintenance)
    monkeypatch.setattr(supervisor._stop_event, "wait", stop_after_three_cycles)
    supervisor.run_forever()

    assert cycles == 3
    assert maintenance_runs == 1


def test_unexpected_loop_failure_is_logged_and_reraised(
    tmp_path, monkeypatch, caplog
) -> None:
    logger = logging.getLogger("test.supervisor.failure")
    core = FluidHistorianCore(logger)
    supervisor = SystemSupervisor(
        core,
        workspace_root=tmp_path,
        logger=logger,
    )

    def fail(_tags: list[str]) -> list[dict[str, object]]:
        raise RuntimeError("test supervisor fault")

    monkeypatch.setattr(core, "compute_fluid_resonance", fail)
    with caplog.at_level(logging.ERROR, logger=logger.name):
        with pytest.raises(RuntimeError, match="test supervisor fault"):
            supervisor.run_forever()

    assert "Unexpected supervisor failure" in caplog.text
    assert not supervisor.is_running
