from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Callable

from aether_engine.backups import DEFAULT_BACKUP_RETENTION, write_backup
from aether_engine.database import AetherStore

_REMOTE_USER = re.compile(r"[A-Za-z0-9._-]+")
_REMOTE_HOST = re.compile(r"[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\]")


class BackupReplicator:
    def __init__(
        self,
        local_db_path: str | Path,
        remote_user: str | None = None,
        remote_host: str | None = None,
        remote_dir: str | None = None,
        *,
        backup_dir: str | Path | None = None,
        identity_file: str | Path | None = None,
        keep: int = DEFAULT_BACKUP_RETENTION,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        remote_values = (remote_user, remote_host, remote_dir)
        if any(value is not None for value in remote_values) and not all(
            value is not None for value in remote_values
        ):
            raise ValueError(
                "Remote user, host, and directory must be provided together."
            )
        if remote_user is not None and not _REMOTE_USER.fullmatch(remote_user):
            raise ValueError("Remote user contains unsupported characters.")
        if remote_host is not None and not _REMOTE_HOST.fullmatch(remote_host):
            raise ValueError("Remote host contains unsupported characters.")
        if remote_dir is not None and (
            not remote_dir.startswith("/")
            or "\n" in remote_dir
            or "\r" in remote_dir
            or ":" in remote_dir
        ):
            raise ValueError("Remote directory must be an absolute POSIX path.")
        if keep < 1:
            raise ValueError("Backup retention count must be at least 1.")

        self.db_path = Path(local_db_path).expanduser().resolve()
        self.backup_dir = (
            Path(backup_dir).expanduser()
            if backup_dir is not None
            else self.db_path.parent / ".aether-backups"
        )
        self.remote_user = remote_user
        self.remote_host = remote_host
        self.remote_dir = remote_dir
        self.identity_file = (
            Path(identity_file).expanduser() if identity_file is not None else None
        )
        self.keep = keep
        self.runner = runner

    def generate_local_backup(self) -> Path:
        if not self.db_path.is_file():
            raise FileNotFoundError(f"Database file does not exist: {self.db_path}")
        with sqlite3.connect(f"{self.db_path.as_uri()}?mode=ro", uri=True) as connection:
            integrity = connection.execute("PRAGMA quick_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise ValueError(f"Database failed SQLite integrity check: {self.db_path}")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        if not {"tasks", "events"}.issubset(tables):
            raise ValueError(f"Not an Aether Engine database: {self.db_path}")
        store = AetherStore(self.db_path)
        backup_file, _ = write_backup(store, self.backup_dir, keep=self.keep)
        print(f"Local Aether backup created: {backup_file}")
        return backup_file

    def replicate_off_machine(self, backup_file: Path) -> bool:
        if not backup_file.is_file():
            raise FileNotFoundError(f"Backup file does not exist: {backup_file}")
        if self.remote_user is None or self.remote_host is None or self.remote_dir is None:
            raise ValueError(
                "Remote user, host, and directory are required for replication."
            )

        destination = (
            f"{self.remote_user}@{self.remote_host}:"
            f"{self.remote_dir.rstrip('/')}/{backup_file.name}"
        )
        command = ["scp", "-p", "-o", "BatchMode=yes"]
        if self.identity_file is not None:
            command.extend(("-i", str(self.identity_file)))
        command.extend((str(backup_file.resolve()), destination))
        print(f"Replicating backup to {self.remote_host}...")

        try:
            result = self.runner(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.CalledProcessError as error:
            detail = error.stderr.strip() if error.stderr else str(error)
            print(f"Replication failed: {detail}", file=sys.stderr)
            return False
        except (OSError, subprocess.TimeoutExpired) as error:
            print(f"Replication failed: {error}", file=sys.stderr)
            return False

        if result.returncode != 0:
            print(
                f"Replication failed with exit code {result.returncode}.",
                file=sys.stderr,
            )
            return False
        print(f"Off-machine backup copy complete: {destination}")
        return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a real Aether SQLite-data backup and optionally copy it with SCP."
    )
    parser.add_argument(
        "--database",
        default=".aether-engine.sqlite3",
        help="existing Aether SQLite database (default: .aether-engine.sqlite3)",
    )
    parser.add_argument(
        "--backup-dir",
        help="local backup directory (default: .aether-backups beside database)",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_BACKUP_RETENTION,
        help=f"local snapshot retention count (default: {DEFAULT_BACKUP_RETENTION})",
    )
    parser.add_argument("--remote-user", help="SSH account for off-machine copy")
    parser.add_argument("--remote-host", help="SSH host for off-machine copy")
    parser.add_argument(
        "--remote-dir", help="existing absolute directory on the SSH host"
    )
    parser.add_argument(
        "--identity-file",
        help="optional SSH private-key path; otherwise use SSH config/agent",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.keep < 1:
        print("--keep must be at least 1.", file=sys.stderr)
        return 2
    try:
        replicator = BackupReplicator(
            args.database,
            args.remote_user,
            args.remote_host,
            args.remote_dir,
            backup_dir=args.backup_dir,
            identity_file=args.identity_file,
            keep=args.keep,
        )
        backup_file = replicator.generate_local_backup()
        if args.remote_user is None:
            print("Local-only mode; no remote transfer attempted.")
            return 0
        return 0 if replicator.replicate_off_machine(backup_file) else 1
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
