from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .database import AetherStore

DEFAULT_BACKUP_RETENTION = 30
_BACKUP_NAME = re.compile(r"aether-backup-\d{8}T\d{6}\.\d{6}Z\.json")


def secure_backup_directory(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for path in directory.iterdir():
        if path.is_symlink():
            continue
        if path.is_file() and (
            _BACKUP_NAME.fullmatch(path.name)
            or path.name
            in ("launchd.stdout.log", "launchd.stderr.log", "last-exit-code")
        ):
            path.chmod(0o600)


def write_backup(
    store: AetherStore,
    directory: Path | None = None,
    *,
    keep: int = DEFAULT_BACKUP_RETENTION,
) -> tuple[Path, int]:
    if keep < 1:
        raise ValueError("Backup retention count must be at least 1.")

    backup_directory = directory or store.database_path.parent / ".aether-backups"
    secure_backup_directory(backup_directory)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup_path = backup_directory / f"aether-backup-{timestamp}.json"
    payload = {
        "schema_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        **store.export_data(),
    }
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".aether-backup-", suffix=".tmp", dir=backup_directory
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as backup_file:
            backup_file.write(serialized)
            backup_file.flush()
            os.fsync(backup_file.fileno())
        os.link(temporary_name, backup_path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)

    snapshots = sorted(
        (
            path
            for path in backup_directory.iterdir()
            if _BACKUP_NAME.fullmatch(path.name)
            and path.is_file()
            and not path.is_symlink()
        ),
        key=lambda path: path.name,
    )
    expired = snapshots[:-keep]
    for path in expired:
        path.unlink()
    return backup_path, len(expired)
