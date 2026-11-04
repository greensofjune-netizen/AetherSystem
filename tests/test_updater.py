import subprocess
import sys
from pathlib import Path

from aether_engine.updater import EngineCoreUpdater


def test_updater_refuses_mutating_actions_outside_virtual_environment(
    monkeypatch,
) -> None:
    updater = EngineCoreUpdater()
    commands: list[list[str]] = []
    monkeypatch.setattr(sys, "prefix", sys.base_prefix)
    monkeypatch.setattr(
        "aether_engine.updater.subprocess.run",
        lambda command, **_kwargs: commands.append(command),
    )

    assert updater.execute_complete_core_maintenance_cycle() == "VULNERABLE"
    assert updater.scan_and_upgrade_software_packages() is False
    assert updater.trigger_binary_recompilation() is False
    assert commands == []


def test_updater_runs_upgrade_and_build_with_active_interpreter(
    monkeypatch,
) -> None:
    updater = EngineCoreUpdater()
    commands: list[list[str]] = []

    def fake_run(
        command: list[str], **_kwargs
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "Build succeeded.", "")

    monkeypatch.setattr(sys, "prefix", "/project/.venv")
    monkeypatch.setattr(sys, "base_prefix", "/usr/local")
    monkeypatch.setattr(
        "aether_engine.updater.subprocess.run", fake_run
    )

    assert updater.scan_and_upgrade_software_packages() is True
    assert updater.trigger_binary_recompilation() is True
    assert commands[0] == [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "pip",
        "ruff",
        "pyinstaller",
        "pytest",
    ]
    assert commands[1] == [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "build_app.py"),
    ]


def test_updater_core_fence_verification(monkeypatch) -> None:
    """Verify updater version state while configured inside a virtual environment."""
    updater = EngineCoreUpdater(current_version="13.0.0")

    monkeypatch.setattr(sys, "prefix", "/Users/eh/Desktop/AetherSystem/.venv")
    monkeypatch.setattr(sys, "base_prefix", "/usr/local")

    assert updater.current_version == "13.0.0"
