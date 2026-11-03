from __future__ import annotations

import hashlib
import os
import plistlib
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

from .backups import DEFAULT_BACKUP_RETENTION, secure_backup_directory

_LABEL_PREFIX = "com.aethersystem.backup"
_MARKER_KEY = "AETHER_ENGINE_DATABASE"
_LAST_EXIT_CODE = re.compile(r"^\s*last exit code = (-?\d+)\s*$", re.MULTILINE)
_CRON_MARKER_PREFIX = "# AETHER_ENGINE_BACKUP:"


class SchedulerError(RuntimeError):
    pass


def _cron_identity(database_path: str | Path) -> tuple[str, Path]:
    database = Path(database_path).expanduser().resolve()
    digest = hashlib.sha256(os.fsencode(database)).hexdigest()[:12]
    return f"{_CRON_MARKER_PREFIX}{digest}", database.parent / ".aether-backups"


def _read_crontab(
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> str:
    try:
        result = runner(
            ["crontab", "-l"], capture_output=True, text=True, check=False
        )
    except OSError as error:
        raise SchedulerError(f"Could not read the user crontab: {error}") from error
    if result.returncode == 0:
        return result.stdout
    if "no crontab" in result.stderr.lower():
        return ""
    detail = result.stderr.strip() or result.stdout.strip()
    raise SchedulerError(f"Could not read the user crontab: {detail}")


def _write_crontab(
    contents: str,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    try:
        result = runner(
            ["crontab", "-"],
            input=contents,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise SchedulerError(f"Could not update the user crontab: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SchedulerError(f"Could not update the user crontab: {detail}")


def _install_cron_schedule(
    database_path: str | Path,
    *,
    python_executable: str,
    keep: int,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> Path:
    database = Path(database_path).expanduser().resolve()
    marker, backup_directory = _cron_identity(database)
    if keep < 1:
        raise ValueError("Backup retention count must be at least 1.")
    secure_backup_directory(backup_directory)
    for protected_path in (
        backup_directory / "launchd.stdout.log",
        backup_directory / "launchd.stderr.log",
        backup_directory / "last-exit-code",
    ):
        if protected_path.is_symlink():
            raise SchedulerError(
                f"Refusing to use a symlink as a scheduled backup file: {protected_path}"
            )
    current = _read_crontab(runner)
    preserved = [
        line for line in current.splitlines() if marker not in line
    ]
    command = " ".join(
        shlex.quote(part)
        for part in (
            str(Path(python_executable).expanduser().resolve()),
            "-m",
            "aether_engine",
            "--database",
            str(database),
            "backup",
            "--directory",
            str(backup_directory),
            "--keep",
            str(keep),
        )
    )
    stdout_log = backup_directory / "launchd.stdout.log"
    stderr_log = backup_directory / "launchd.stderr.log"
    result_file = backup_directory / "last-exit-code"
    entry = (
        f"0 9 * * * umask 077; {command} >> {shlex.quote(str(stdout_log))} "
        f"2>> {shlex.quote(str(stderr_log))}; result=$?; "
        f"printf '%s\\n' \"$result\" > {shlex.quote(str(result_file))} {marker}"
    )
    contents = "\n".join((*preserved, entry)) + "\n"
    _write_crontab(contents, runner)
    return Path("user crontab")


def _cron_schedule_status(
    database_path: str | Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> tuple[Path, bool, bool, int | None]:
    marker, backup_directory = _cron_identity(database_path)
    current = _read_crontab(runner)
    installed = any(marker in line for line in current.splitlines())
    if not installed:
        return Path("user crontab"), False, False, None
    result_file = backup_directory / "last-exit-code"
    if result_file.is_symlink():
        raise SchedulerError(f"Refusing to read a symlinked schedule result: {result_file}")
    try:
        raw_code = result_file.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        last_exit_code = None
    except (OSError, UnicodeError) as error:
        raise SchedulerError(f"Could not read scheduled backup result: {error}") from error
    else:
        try:
            last_exit_code = int(raw_code)
        except ValueError as error:
            raise SchedulerError(
                f"Scheduled backup result is not an integer: {result_file}"
            ) from error
    return Path("user crontab"), True, True, last_exit_code


def _uninstall_cron_schedule(
    database_path: str | Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> tuple[Path, bool]:
    marker, _ = _cron_identity(database_path)
    current = _read_crontab(runner)
    preserved = [
        line for line in current.splitlines() if marker not in line
    ]
    if len(preserved) == len(current.splitlines()):
        return Path("user crontab"), False
    contents = "\n".join(preserved)
    _write_crontab(f"{contents}\n" if contents else "", runner)
    return Path("user crontab"), True


def _schedule_identity(
    database_path: str | Path, home: Path | None = None
) -> tuple[str, Path, Path]:
    database = Path(database_path).expanduser().resolve()
    digest = hashlib.sha256(os.fsencode(database)).hexdigest()[:12]
    label = f"{_LABEL_PREFIX}.{digest}"
    home_directory = (home or Path.home()).expanduser().resolve()
    agent_path = home_directory / "Library" / "LaunchAgents" / f"{label}.plist"
    backup_directory = database.parent / ".aether-backups"
    return label, agent_path, backup_directory


def _agent_contents(
    database_path: str | Path,
    python_executable: str,
    *,
    keep: int = DEFAULT_BACKUP_RETENTION,
    home: Path | None = None,
) -> tuple[str, Path, dict[str, object]]:
    database = Path(database_path).expanduser().resolve()
    label, agent_path, backup_directory = _schedule_identity(database, home)
    contents: dict[str, object] = {
        "Label": label,
        "ProgramArguments": [
            str(Path(python_executable).resolve()),
            "-m",
            "aether_engine",
            "--database",
            str(database),
            "backup",
            "--directory",
            str(backup_directory),
            "--keep",
            str(keep),
        ],
        "WorkingDirectory": str(database.parent),
        "StartCalendarInterval": {"Hour": 9, "Minute": 0},
        "RunAtLoad": False,
        "StandardOutPath": str(backup_directory / "launchd.stdout.log"),
        "StandardErrorPath": str(backup_directory / "launchd.stderr.log"),
        "EnvironmentVariables": {_MARKER_KEY: str(database)},
    }
    return label, agent_path, contents


def _run_launchctl(
    runner: Callable[..., subprocess.CompletedProcess[str]], *arguments: str
) -> subprocess.CompletedProcess[str]:
    try:
        result = runner(
            ["/bin/launchctl", *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise SchedulerError(f"Could not run launchctl: {error}") from error
    return result


def _is_loaded(
    label: str,
    uid: int,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> tuple[bool, int | None]:
    result = _run_launchctl(runner, "print", f"gui/{uid}/{label}")
    if result.returncode == 0:
        match = _LAST_EXIT_CODE.search(result.stdout)
        return True, int(match.group(1)) if match else None
    if result.returncode == 113 and "Could not find service" in result.stderr:
        return False, None
    detail = result.stderr.strip() or result.stdout.strip()
    raise SchedulerError(
        f"Could not determine whether LaunchAgent '{label}' is loaded"
        + (f": {detail}" if detail else ".")
    )


def install_backup_schedule(
    database_path: str | Path,
    *,
    python_executable: str = sys.executable,
    keep: int = DEFAULT_BACKUP_RETENTION,
    home: Path | None = None,
    uid: int | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Path:
    if sys.platform == "linux":
        return _install_cron_schedule(
            database_path,
            python_executable=python_executable,
            keep=keep,
            runner=runner,
        )
    if sys.platform == "win32":
        raise SchedulerError(
            "Automatic scheduling is not yet supported on Windows; use Task Scheduler."
        )
    database = Path(database_path).expanduser().resolve()
    if keep < 1:
        raise ValueError("Backup retention count must be at least 1.")
    label, agent_path, backup_directory = _schedule_identity(database, home)
    agent_path.parent.mkdir(parents=True, exist_ok=True)
    secure_backup_directory(backup_directory)
    _, _, contents = _agent_contents(
        database, python_executable, keep=keep, home=home
    )
    for log_name in ("launchd.stdout.log", "launchd.stderr.log"):
        log_path = backup_directory / log_name
        if log_path.is_symlink():
            raise SchedulerError(f"Refusing to use a symlink as a launch log: {log_path}")
        descriptor = os.open(
            log_path,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT,
            0o600,
        )
        os.close(descriptor)
        os.chmod(log_path, 0o600)

    previous_contents: bytes | None = None
    if agent_path.exists():
        try:
            previous = plistlib.loads(agent_path.read_bytes())
        except (OSError, plistlib.InvalidFileException) as error:
            raise SchedulerError(
                f"Existing LaunchAgent is not a valid plist: {agent_path}"
            ) from error
        environment = previous.get("EnvironmentVariables", {})
        if not isinstance(environment, dict) or environment.get(_MARKER_KEY) != str(
            database
        ):
            raise SchedulerError(
                f"Refusing to overwrite an unrelated LaunchAgent: {agent_path}"
            )
        previous_contents = plistlib.dumps(previous, fmt=plistlib.FMT_XML)

    launch_uid = os.getuid() if uid is None else uid
    was_loaded, _ = _is_loaded(label, launch_uid, runner)
    if was_loaded:
        result = _run_launchctl(runner, "bootout", f"gui/{launch_uid}/{label}")
        if result.returncode != 0:
            raise SchedulerError(
                f"Could not unload existing LaunchAgent: {result.stderr.strip()}"
            )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{label}.", suffix=".plist", dir=agent_path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(plistlib.dumps(contents, fmt=plistlib.FMT_XML))
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, agent_path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)

    result = _run_launchctl(
        runner, "bootstrap", f"gui/{launch_uid}", str(agent_path)
    )
    if result.returncode != 0:
        if previous_contents is None:
            agent_path.unlink(missing_ok=True)
        else:
            agent_path.write_bytes(previous_contents)
            _run_launchctl(
                runner, "bootstrap", f"gui/{launch_uid}", str(agent_path)
            )
        raise SchedulerError(
            f"Could not load LaunchAgent: {result.stderr.strip()}"
        )
    return agent_path


def backup_schedule_status(
    database_path: str | Path,
    *,
    home: Path | None = None,
    uid: int | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[Path, bool, bool, int | None]:
    if sys.platform == "linux":
        return _cron_schedule_status(database_path, runner=runner)
    if sys.platform == "win32":
        raise SchedulerError(
            "Automatic scheduling is not yet supported on Windows; use Task Scheduler."
        )
    database = Path(database_path).expanduser().resolve()
    label, agent_path, _ = _schedule_identity(database, home)
    if not agent_path.exists():
        return agent_path, False, False, None
    try:
        contents = plistlib.loads(agent_path.read_bytes())
    except (OSError, plistlib.InvalidFileException) as error:
        raise SchedulerError(
            f"Could not read LaunchAgent plist: {agent_path}"
        ) from error
    environment = contents.get("EnvironmentVariables", {})
    if not isinstance(environment, dict) or environment.get(_MARKER_KEY) != str(
        database
    ):
        raise SchedulerError(
            f"LaunchAgent plist is not managed by Aether Engine: {agent_path}"
        )
    launch_uid = os.getuid() if uid is None else uid
    loaded, last_exit_code = _is_loaded(label, launch_uid, runner)
    return agent_path, True, loaded, last_exit_code


def uninstall_backup_schedule(
    database_path: str | Path,
    *,
    home: Path | None = None,
    uid: int | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[Path, bool]:
    if sys.platform == "linux":
        return _uninstall_cron_schedule(database_path, runner=runner)
    if sys.platform == "win32":
        raise SchedulerError(
            "Automatic scheduling is not yet supported on Windows; use Task Scheduler."
        )
    agent_path, installed, loaded, _ = backup_schedule_status(
        database_path, home=home, uid=uid, runner=runner
    )
    if not installed:
        return agent_path, False
    database = Path(database_path).expanduser().resolve()
    label, _, _ = _schedule_identity(database, home)
    launch_uid = os.getuid() if uid is None else uid
    if loaded:
        result = _run_launchctl(runner, "bootout", f"gui/{launch_uid}/{label}")
        if result.returncode != 0:
            raise SchedulerError(
                f"Could not unload LaunchAgent: {result.stderr.strip()}"
            )
    agent_path.unlink()
    return agent_path, True
