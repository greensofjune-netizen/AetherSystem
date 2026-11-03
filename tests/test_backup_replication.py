import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from aether_engine.database import AetherStore
from backup_replication import BackupReplicator, main


def test_local_backup_contains_real_project_data_and_is_private(
    tmp_path: Path, capsys
) -> None:
    database = tmp_path / "project.sqlite3"
    store = AetherStore(database)
    store.add_task("Actual task", "Actual description", "high", "2026-12-01")
    store.add_event("test", "Actual event")

    replicator = BackupReplicator(
        database, backup_dir=tmp_path / "local-backups"
    )
    backup = replicator.generate_local_backup()

    payload = json.loads(backup.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["tasks"][0]["title"] == "Actual task"
    assert payload["tasks"][0]["priority"] == "high"
    assert payload["events"][0]["message"] == "Actual event"
    assert backup.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "local-backups").stat().st_mode & 0o777 == 0o700
    assert "Local Aether backup created" in capsys.readouterr().out


def test_missing_database_does_not_create_empty_backup(tmp_path: Path) -> None:
    database = tmp_path / "missing.sqlite3"
    replicator = BackupReplicator(database, backup_dir=tmp_path / "backups")

    with pytest.raises(FileNotFoundError, match="Database file does not exist"):
        replicator.generate_local_backup()

    assert not (tmp_path / "backups").exists()


def test_non_aether_database_is_rejected_without_modification(
    tmp_path: Path,
) -> None:
    database = tmp_path / "other.sqlite3"
    database.write_bytes(b"not an sqlite database")
    original = database.read_bytes()
    replicator = BackupReplicator(database, backup_dir=tmp_path / "backups")

    with pytest.raises(sqlite3.DatabaseError):
        replicator.generate_local_backup()

    assert database.read_bytes() == original
    assert not (tmp_path / "backups").exists()


def test_replication_uses_explicit_ssh_target_and_existing_backup(
    tmp_path: Path, capsys
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    database = tmp_path / "project.sqlite3"
    AetherStore(database).add_task("Replicate me")
    replicator = BackupReplicator(
        database,
        "backup-user",
        "backup.example.net",
        "/srv/backups/aether",
        backup_dir=tmp_path / "local",
        identity_file=tmp_path / "ssh-key",
        runner=fake_run,
    )

    backup = replicator.generate_local_backup()
    assert replicator.replicate_off_machine(backup)

    command, options = calls[0]
    assert command[:5] == [
        "scp",
        "-p",
        "-o",
        "BatchMode=yes",
        "-i",
    ]
    assert command[5] == str(tmp_path / "ssh-key")
    assert command[-2] == str(backup.resolve())
    assert command[-1] == (
        f"backup-user@backup.example.net:/srv/backups/aether/{backup.name}"
    )
    assert options["check"] is True
    assert options["timeout"] == 120
    assert "Off-machine backup copy complete" in capsys.readouterr().out


def test_remote_transfer_failure_is_reported(tmp_path: Path, capsys) -> None:
    def failed_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(
            1, command, stderr="connection unavailable"
        )

    database = tmp_path / "project.sqlite3"
    AetherStore(database)
    replicator = BackupReplicator(
        database,
        "backup-user",
        "backup.example.net",
        "/srv/backups",
        backup_dir=tmp_path / "local",
        runner=failed_run,
    )

    backup = replicator.generate_local_backup()
    assert not replicator.replicate_off_machine(backup)
    assert "connection unavailable" in capsys.readouterr().err


def test_remote_options_are_validated_and_local_mode_never_transfers(
    tmp_path: Path, capsys
) -> None:
    with pytest.raises(ValueError, match="provided together"):
        BackupReplicator(tmp_path / "db.sqlite3", remote_user="user")
    with pytest.raises(ValueError, match="unsupported characters"):
        BackupReplicator(
            tmp_path / "db.sqlite3",
            "user;bad",
            "host.example",
            "/backup",
        )
    with pytest.raises(ValueError, match="absolute POSIX path"):
        BackupReplicator(
            tmp_path / "db.sqlite3",
            "user",
            "host.example",
            "~/backup",
        )

    database = tmp_path / "project.sqlite3"
    AetherStore(database)
    assert main(
        ["--database", str(database), "--backup-dir", str(tmp_path / "local")]
    ) == 0
    output = capsys.readouterr().out
    assert "Local-only mode" in output
