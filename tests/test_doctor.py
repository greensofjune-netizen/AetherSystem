import os
import sys
from pathlib import Path

import pytest

from aether_engine import engine_doctor as doctor_module
from aether_engine.backups import write_backup
from aether_engine.database import AetherStore, SecureAetherStore
from aether_engine.engine_doctor import AetherEngineDoctor


def test_doctor_reports_virtual_environment_as_ok(
    tmp_path: Path, monkeypatch
) -> None:
    virtual_env = "/Users/eh/Desktop/AetherSystem/.venv"
    monkeypatch.setattr(sys, "prefix", virtual_env)
    monkeypatch.setattr(sys, "base_prefix", "/usr/local")
    monkeypatch.setattr(
        doctor_module,
        "backup_schedule_status",
        lambda _database: (tmp_path / "agent.plist", False, False, None),
    )
    database = tmp_path / "database.db"
    AetherStore(database)

    results = AetherEngineDoctor(database).diagnostics()
    environment = next(
        result for result in results if result.name == "Python environment"
    )

    assert environment.status == "OK"
    assert environment.detail == f"Virtual environment: {virtual_env}"


def test_doctor_checks_database_backup_permissions_and_schedule(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(sys, "prefix", str(tmp_path / ".venv"))
    monkeypatch.setattr(sys, "base_prefix", "/usr/local")
    database = tmp_path / "project.sqlite3"
    backup_directory = tmp_path / ".aether-backups"
    store = AetherStore(database)
    store.add_task("Doctor test")
    write_backup(store, backup_directory)
    monkeypatch.setattr(
        doctor_module,
        "backup_schedule_status",
        lambda _database: (tmp_path / "agent.plist", True, True, 0),
    )

    doctor = AetherEngineDoctor(database)
    results = doctor.diagnostics()

    assert [(result.name, result.status) for result in results[:4]] == [
        ("Database", "OK"),
        ("Backups", "OK"),
        ("Backup permissions", "OK"),
        ("Backup schedule", "OK"),
    ]
    assert doctor.execute_complete_medical_sweep() == 0
    output = capsys.readouterr().out
    assert "AETHER ENGINE DOCTOR" in output
    assert "all checks passed" in output


def test_doctor_reports_corrupt_database_and_invalid_backup(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "corrupt.sqlite3"
    database.write_text("not sqlite", encoding="utf-8")
    backup_directory = tmp_path / ".aether-backups"
    backup_directory.mkdir()
    backup = backup_directory / "aether-backup-20261103T120000.000000Z.json"
    backup.write_text("{", encoding="utf-8")
    monkeypatch.setattr(
        doctor_module,
        "backup_schedule_status",
        lambda _database: (tmp_path / "agent.plist", False, False, None),
    )

    results = AetherEngineDoctor(database).diagnostics()

    assert results[0].status == "FAIL"
    assert "Database" in results[0].name
    assert results[1].status == "FAIL"
    assert "Latest snapshot is invalid" in results[1].detail


def test_doctor_reports_unconfigured_backup_and_schedule_as_warnings(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "empty.sqlite3"
    AetherStore(database)
    monkeypatch.setattr(
        doctor_module,
        "backup_schedule_status",
        lambda _database: (tmp_path / "agent.plist", False, False, None),
    )

    results = AetherEngineDoctor(database).diagnostics()

    assert results[0].status == "OK"
    assert results[1].status == "WARN"
    assert results[2].status == "WARN"
    assert results[3].status == "WARN"


def test_secure_store_uses_existing_schema_and_private_permissions(
    tmp_path: Path,
) -> None:
    database = tmp_path / "secure.sqlite3"

    store = SecureAetherStore(database)
    task = store.add_task("Check secure store")

    assert task.title == "Check secure store"
    assert store.list_tasks()[0].id == task.id
    if os.name != "nt":
        assert database.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes are not Windows ACLs")
def test_doctor_reports_insecure_database_permissions(tmp_path: Path) -> None:
    database = tmp_path / "insecure.sqlite3"
    AetherStore(database)
    database.chmod(0o644)

    result = AetherEngineDoctor(database).diagnose_database()

    assert result.status == "FAIL"
    assert "restricted to the current user" in result.detail


@pytest.mark.skipif(os.name == "nt", reason="symlink permissions vary on Windows")
def test_doctor_flags_symlinked_backup_directory(tmp_path: Path) -> None:
    database = tmp_path / "project.sqlite3"
    AetherStore(database)
    target_directory = tmp_path / "other-backups"
    target_directory.mkdir()
    backup_link = tmp_path / ".aether-backups"
    backup_link.symlink_to(target_directory, target_is_directory=True)

    backup_results = AetherEngineDoctor(database).diagnose_backups()

    assert [result.status for result in backup_results] == ["FAIL", "FAIL"]
    assert "must not be a symlink" in backup_results[0].detail

    custom_doctor = AetherEngineDoctor(database, backup_dir=backup_link)
    custom_results = custom_doctor.diagnose_backups()
    assert [result.status for result in custom_results] == ["FAIL", "FAIL"]
