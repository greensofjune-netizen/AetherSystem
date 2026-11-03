from __future__ import annotations

import json
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .backups import _BACKUP_NAME
from .database import AetherStore, database_permission_issues
from .scheduler import SchedulerError, backup_schedule_status


@dataclass(frozen=True)
class Diagnostic:
    name: str
    status: str
    detail: str


class AetherEngineDoctor:
    def __init__(
        self,
        db_path: str | Path,
        *,
        backup_dir: str | Path | None = None,
    ) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.backup_dir = (
            Path(backup_dir).expanduser().absolute()
            if backup_dir is not None
            else self.db_path.parent / ".aether-backups"
        )

    def diagnose_database(self) -> Diagnostic:
        if not self.db_path.is_file():
            return Diagnostic("Database", "FAIL", f"Not found: {self.db_path}")
        try:
            uri = f"{self.db_path.as_uri()}?mode=ro"
            with sqlite3.connect(uri, uri=True) as connection:
                integrity = connection.execute("PRAGMA quick_check").fetchone()
                if integrity is None or integrity[0] != "ok":
                    detail = integrity[0] if integrity else "no integrity result"
                    return Diagnostic("Database", "FAIL", str(detail))
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                missing = {"tasks", "events"} - tables
                if missing:
                    return Diagnostic(
                        "Database",
                        "FAIL",
                        f"Missing required table(s): {', '.join(sorted(missing))}",
                    )
                task_count = connection.execute(
                    "SELECT COUNT(*) FROM tasks"
                ).fetchone()[0]
                event_count = connection.execute(
                    "SELECT COUNT(*) FROM events"
                ).fetchone()[0]
        except sqlite3.Error as error:
            return Diagnostic("Database", "FAIL", str(error))
        try:
            insecure_files = database_permission_issues(self.db_path)
        except OSError as error:
            return Diagnostic(
                "Database", "FAIL", f"Could not verify database permissions: {error}"
            )
        if insecure_files:
            return Diagnostic(
                "Database",
                "FAIL",
                "Database files must be restricted to the current user: "
                + ", ".join(insecure_files),
            )
        return Diagnostic(
            "Database",
            "OK",
            f"Integrity check passed; {task_count} task(s), {event_count} event(s).",
        )

    def diagnose_backups(self) -> list[Diagnostic]:
        if self.backup_dir.is_symlink():
            return [
                Diagnostic(
                    "Backups",
                    "FAIL",
                    f"Backup directory must not be a symlink: {self.backup_dir}",
                ),
                Diagnostic(
                    "Backup permissions",
                    "FAIL",
                    "Cannot verify permissions through a symlinked backup directory.",
                ),
            ]
        if not self.backup_dir.is_dir():
            return [
                Diagnostic("Backups", "WARN", f"Directory not found: {self.backup_dir}"),
                Diagnostic(
                    "Backup permissions",
                    "WARN",
                    "Cannot check permissions before a backup exists.",
                ),
            ]

        entries = list(self.backup_dir.iterdir())
        backup_entries = [
            path for path in entries if _BACKUP_NAME.fullmatch(path.name)
        ]
        snapshots = sorted(
            (path for path in backup_entries if path.is_file() and not path.is_symlink()),
            key=lambda path: path.name,
        )
        if not snapshots:
            backup_result = Diagnostic("Backups", "WARN", "No timestamped backups found.")
        else:
            latest = snapshots[-1]
            try:
                with latest.open(encoding="utf-8") as backup_file:
                    payload = json.load(backup_file)
                AetherStore.validate_export(payload)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                backup_result = Diagnostic(
                    "Backups", "FAIL", f"Latest snapshot is invalid: {error}"
                )
            else:
                backup_result = Diagnostic(
                    "Backups", "OK", f"Latest snapshot is valid: {latest.name}"
                )

        directory_mode = self.backup_dir.stat().st_mode & 0o777
        protected_files = [
            path
            for path in entries
            if path.name
            in ("launchd.stdout.log", "launchd.stderr.log", "last-exit-code")
            or _BACKUP_NAME.fullmatch(path.name)
        ]
        unsafe_paths: list[str] = []
        for path in protected_files:
            if path.is_symlink():
                unsafe_paths.append(f"{path.name} is a symlink")
            elif path.exists():
                if not path.is_file():
                    unsafe_paths.append(f"{path.name} is not a regular file")
                elif path.stat().st_mode & 0o077:
                    unsafe_paths.append(
                        f"{path.name} is accessible by other users"
                    )
        if directory_mode & 0o077 or unsafe_paths:
            details = []
            if directory_mode & 0o077:
                details.append(f"directory mode is {directory_mode:04o}, expected 0700")
            details.extend(unsafe_paths)
            permission_result = Diagnostic(
                "Backup permissions", "FAIL", "; ".join(details)
            )
        else:
            permission_result = Diagnostic(
                "Backup permissions",
                "OK",
                f"Directory and protected files are owner-only; "
                f"{len(snapshots)} snapshot(s) found.",
            )
        return [backup_result, permission_result]

    def diagnose_schedule(self) -> Diagnostic:
        if sys.platform == "win32":
            return Diagnostic(
                "Backup schedule",
                "WARN",
                "Automatic schedule management is not available; configure "
                "Windows Task Scheduler manually.",
            )
        try:
            _, installed, loaded, last_exit_code = backup_schedule_status(
                self.db_path
            )
        except SchedulerError as error:
            return Diagnostic("Backup schedule", "FAIL", str(error))
        if not installed:
            return Diagnostic("Backup schedule", "WARN", "No LaunchAgent installed.")
        if not loaded:
            return Diagnostic("Backup schedule", "FAIL", "LaunchAgent is not loaded.")
        if last_exit_code is None:
            return Diagnostic("Backup schedule", "WARN", "No previous run result available.")
        if last_exit_code != 0:
            return Diagnostic(
                "Backup schedule",
                "FAIL",
                f"Last run exited with code {last_exit_code}; inspect "
                f"{self.backup_dir / 'launchd.stderr.log'}.",
            )
        return Diagnostic("Backup schedule", "OK", "Loaded; last run succeeded.")

    def diagnostics(self) -> list[Diagnostic]:
        results = [self.diagnose_database()]
        results.extend(self.diagnose_backups())
        results.append(self.diagnose_schedule())
        if sys.prefix != sys.base_prefix:
            results.append(
                Diagnostic("Python environment", "OK", f"Virtual environment: {sys.prefix}")
            )
        else:
            results.append(
                Diagnostic(
                    "Python environment",
                    "WARN",
                    f"Running outside a virtual environment ({sys.executable}).",
                )
            )
        return results

    def execute_complete_medical_sweep(self) -> int:
        print("AETHER ENGINE DOCTOR")
        print(time.strftime("Checked at %Y-%m-%d %H:%M:%S %Z"))
        results = self.diagnostics()
        for result in results:
            print(f"[{result.status}] {result.name}: {result.detail}")

        failures = sum(result.status == "FAIL" for result in results)
        warnings = sum(result.status == "WARN" for result in results)
        if failures:
            print(f"Result: {failures} failure(s), {warnings} warning(s).")
            return 1
        if warnings:
            print(f"Result: healthy with {warnings} warning(s).")
            return 0
        print("Result: all checks passed.")
        return 0
