import plistlib
import subprocess
from pathlib import Path

import pytest

from aether_engine.cli import main
from aether_engine.scheduler import (
    SchedulerError,
    backup_schedule_status,
    install_backup_schedule,
    uninstall_backup_schedule,
)


class FakeCrontab:
    def __init__(self) -> None:
        self.contents = ""
        self.commands: list[list[str]] = []

    def __call__(
        self, command: list[str], **kwargs
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if command == ["crontab", "-l"]:
            if self.contents:
                return subprocess.CompletedProcess(command, 0, self.contents, "")
            return subprocess.CompletedProcess(command, 1, "", "no crontab for test")
        self.contents = kwargs["input"]
        return subprocess.CompletedProcess(command, 0, "", "")


class FakeLaunchctl:
    def __init__(self) -> None:
        self.loaded = False
        self.last_exit_code: int | None = None
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        action = command[1]
        if action == "print":
            if self.loaded:
                output = (
                    f"last exit code = {self.last_exit_code}\n"
                    if self.last_exit_code is not None
                    else ""
                )
                return subprocess.CompletedProcess(command, 0, output, "")
            return subprocess.CompletedProcess(
                command,
                113,
                "",
                'Could not find service "label" in domain for user gui: 501',
            )
        if action == "bootstrap":
            self.loaded = True
        elif action == "bootout":
            self.loaded = False
        return subprocess.CompletedProcess(command, 0, "", "")


@pytest.fixture
def launchd_platform(monkeypatch) -> None:
    from aether_engine import scheduler

    monkeypatch.setattr(scheduler.sys, "platform", "darwin")


@pytest.mark.usefixtures("launchd_platform")
def test_install_status_and_uninstall_launch_agent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    database = tmp_path / "project" / ".aether-engine.sqlite3"
    runner = FakeLaunchctl()

    agent_path = install_backup_schedule(
        database,
        python_executable="/project/.venv/bin/python",
        keep=7,
        home=home,
        uid=501,
        runner=runner,
    )

    assert agent_path.exists()
    contents = plistlib.loads(agent_path.read_bytes())
    assert contents["ProgramArguments"] == [
        "/project/.venv/bin/python",
        "-m",
        "aether_engine",
        "--database",
        str(database.resolve()),
        "backup",
        "--directory",
        str(database.parent.resolve() / ".aether-backups"),
        "--keep",
        "7",
    ]
    assert contents["StartCalendarInterval"] == {"Hour": 9, "Minute": 0}
    assert contents["RunAtLoad"] is False
    assert agent_path.stat().st_mode & 0o777 == 0o600
    backup_directory = database.parent / ".aether-backups"
    assert backup_directory.stat().st_mode & 0o777 == 0o700
    assert (backup_directory / "launchd.stdout.log").stat().st_mode & 0o777 == 0o600
    assert (backup_directory / "launchd.stderr.log").stat().st_mode & 0o777 == 0o600

    status_path, installed, loaded, last_exit_code = backup_schedule_status(
        database, home=home, uid=501, runner=runner
    )
    assert status_path == agent_path
    assert installed and loaded
    assert last_exit_code is None

    runner.last_exit_code = 7
    status_path, installed, loaded, last_exit_code = backup_schedule_status(
        database, home=home, uid=501, runner=runner
    )
    assert installed and loaded
    assert last_exit_code == 7

    removed_path, removed = uninstall_backup_schedule(
        database, home=home, uid=501, runner=runner
    )
    assert removed_path == agent_path
    assert removed
    assert not agent_path.exists()
    assert not runner.loaded


@pytest.mark.usefixtures("launchd_platform")
def test_install_refuses_to_overwrite_unrelated_agent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    database = tmp_path / "project" / ".aether-engine.sqlite3"
    agent_directory = home / "Library" / "LaunchAgents"
    agent_directory.mkdir(parents=True)

    from aether_engine.scheduler import _schedule_identity

    _, agent_path, _ = _schedule_identity(database, home)
    original = plistlib.dumps({"Label": "someone.else"})
    agent_path.write_bytes(original)

    with pytest.raises(SchedulerError, match="Refusing to overwrite"):
        install_backup_schedule(database, home=home, runner=FakeLaunchctl())

    assert agent_path.read_bytes() == original


@pytest.mark.usefixtures("launchd_platform")
def test_uninstall_reports_absent_schedule(tmp_path: Path) -> None:
    agent_path, removed = uninstall_backup_schedule(
        tmp_path / "project" / "data.sqlite3",
        home=tmp_path / "home",
        runner=FakeLaunchctl(),
    )
    assert not removed
    assert not agent_path.exists()


@pytest.mark.usefixtures("launchd_platform")
def test_status_surfaces_launchctl_failures(tmp_path: Path) -> None:
    class FailedPrint(FakeLaunchctl):
        def __call__(self, command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
            self.commands.append(command)
            return subprocess.CompletedProcess(
                command, 5, "", "launchd communication failed"
            )

    database = tmp_path / "project" / "data.sqlite3"
    home = tmp_path / "home"
    agent_path = install_backup_schedule(
        database, home=home, runner=FakeLaunchctl()
    )
    with pytest.raises(SchedulerError, match="launchd communication failed"):
        backup_schedule_status(database, home=home, runner=FailedPrint())
    assert agent_path.exists()


@pytest.mark.usefixtures("launchd_platform")
def test_install_bootstrap_failure_removes_new_plist(tmp_path: Path) -> None:
    class FailedBootstrap(FakeLaunchctl):
        def __call__(self, command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
            self.commands.append(command)
            if command[1] == "bootstrap":
                return subprocess.CompletedProcess(
                    command, 1, "", "test bootstrap failure"
                )
            return subprocess.CompletedProcess(
                command,
                113,
                "",
                'Could not find service "label" in domain for user gui: 501',
            )

    from aether_engine.scheduler import _schedule_identity

    home = tmp_path / "home"
    database = tmp_path / "project" / "data.sqlite3"
    _, agent_path, _ = _schedule_identity(database, home)

    with pytest.raises(SchedulerError, match="test bootstrap failure"):
        install_backup_schedule(database, home=home, runner=FailedBootstrap())

    assert not agent_path.exists()


def test_status_cli_reports_last_run_failure(tmp_path: Path, monkeypatch, capsys) -> None:
    from aether_engine import cli

    database = tmp_path / "database.sqlite3"
    monkeypatch.setattr(
        cli,
        "backup_schedule_status",
        lambda _database: (
            tmp_path / "agent.plist",
            True,
            True,
            7,
        ),
    )

    assert main(
        ["--database", str(database), "backup", "schedule", "status"]
    ) == 1
    output = capsys.readouterr()
    assert "schedule is active" in output.out
    assert "FAILED (exit code 7)" in output.err
    assert "launchd.stderr.log" in output.err


def test_install_status_and_uninstall_linux_cron_schedule(
    tmp_path: Path, monkeypatch
) -> None:
    from aether_engine import scheduler

    monkeypatch.setattr(scheduler.sys, "platform", "linux")
    runner = FakeCrontab()
    runner.contents = "# preserve this user job\n"
    database = tmp_path / "project" / "data.sqlite3"

    schedule_path = install_backup_schedule(
        database,
        python_executable="/project/.venv/bin/python",
        keep=9,
        runner=runner,
    )
    assert schedule_path == Path("user crontab")
    assert "0 9 * * *" in runner.contents
    assert "--keep 9" in runner.contents
    assert "AETHER_ENGINE_BACKUP:" in runner.contents
    assert str(database.resolve()) in runner.contents
    assert "# preserve this user job" in runner.contents

    install_backup_schedule(database, keep=12, runner=runner)
    assert runner.contents.count("AETHER_ENGINE_BACKUP:") == 1
    assert "--keep 12" in runner.contents

    _, installed, loaded, last_exit_code = backup_schedule_status(
        database, runner=runner
    )
    assert installed and loaded
    assert last_exit_code is None

    result_file = database.parent / ".aether-backups" / "last-exit-code"
    result_file.write_text("0\n", encoding="ascii")
    _, installed, loaded, last_exit_code = backup_schedule_status(
        database, runner=runner
    )
    assert installed and loaded
    assert last_exit_code == 0

    removed_path, removed = uninstall_backup_schedule(database, runner=runner)
    assert removed_path == Path("user crontab")
    assert removed
    assert "AETHER_ENGINE_BACKUP:" not in runner.contents
