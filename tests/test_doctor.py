from pathlib import Path

from aether_engine import engine_doctor as doctor_module
from aether_engine.backups import write_backup
from aether_engine.database import AetherStore
from aether_engine.engine_doctor import AetherEngineDoctor


def test_doctor_checks_database_backup_permissions_and_schedule(
    tmp_path: Path, monkeypatch, capsys
) -> None:
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
