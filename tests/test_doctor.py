import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from aether_engine import backups as backups_module
from aether_engine import engine_doctor as doctor_module
from aether_engine.backups import write_backup
from aether_engine.database import AetherStore, SecureAetherStore
from aether_engine.engine_doctor import (
    AetherEngineDoctor,
    EngineDoctor,
    SystemEnvironmentAnomalyError,
)


def test_engine_doctor_validates_local_interpreter_and_project(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    executable = str(tmp_path / ".venv" / "bin" / "python")
    monkeypatch.setattr(doctor_module.sys, "executable", executable)

    doctor = EngineDoctor(project)

    assert doctor.verify_interpreter_sandbox() == executable
    assert doctor.run_full_diagnostic_sweep() == {
        "interpreter_path": executable,
        "pyproject_validated": True,
        "status_healthy": True,
    }


def test_engine_doctor_reports_non_virtual_interpreter(tmp_path: Path, monkeypatch) -> None:
    executable = str(tmp_path / "python")
    monkeypatch.setattr(doctor_module.sys, "executable", executable)

    doctor = EngineDoctor(tmp_path)

    with pytest.raises(SystemEnvironmentAnomalyError, match="Rogue execution runtime"):
        doctor.verify_interpreter_sandbox()
    assert doctor.run_full_diagnostic_sweep() == {
        "error_telemetry": f"Rogue execution runtime identified at: {executable}",
        "status_healthy": False,
    }


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


def test_windows_backup_protection_covers_directory_existing_and_new_files(
    tmp_path: Path, monkeypatch
) -> None:
    store = AetherStore(tmp_path / "project.sqlite3")
    directory = tmp_path / ".aether-backups"
    directory.mkdir()
    existing = directory / "aether-backup-20261103T120000.000000Z.json"
    existing.write_text("{}")
    unrelated = directory / "unrelated.txt"
    unrelated.write_text("leave alone")
    calls: list[tuple[Path, bool]] = []
    monkeypatch.setattr(
        backups_module, "os", SimpleNamespace(**(vars(os) | {"name": "nt"}))
    )
    monkeypatch.setattr(
        backups_module,
        "_secure_windows_file",
        lambda path, *, directory=False: calls.append((path, directory)),
    )

    snapshot, _ = write_backup(store, directory)

    assert calls[0] == (directory, True)
    assert (existing, False) in calls
    assert (unrelated, False) not in calls
    assert calls[-1][0].suffix == ".tmp"
    assert calls[-1][1] is False
    assert snapshot.is_file()


def test_windows_backup_acl_failure_does_not_publish_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    store = AetherStore(tmp_path / "project.sqlite3")
    monkeypatch.setattr(
        backups_module, "os", SimpleNamespace(**(vars(os) | {"name": "nt"}))
    )

    def secure(path: Path, *, directory: bool = False) -> None:
        if not directory:
            raise PermissionError("Snapshot ACL failed")

    monkeypatch.setattr(backups_module, "_secure_windows_file", secure)
    with pytest.raises(PermissionError, match="Snapshot ACL failed"):
        write_backup(store)
    assert list((tmp_path / ".aether-backups").iterdir()) == []


@pytest.mark.parametrize("unsafe", [False, True])
def test_windows_backup_doctor_uses_acl_checks_not_posix_modes(
    tmp_path: Path, monkeypatch, unsafe: bool
) -> None:
    store = AetherStore(tmp_path / "project.sqlite3")
    snapshot, _ = write_backup(store)
    calls: list[Path] = []

    def check_acl(path: Path) -> list[str]:
        calls.append(path)
        return ["excessive Windows access"] if unsafe else []

    monkeypatch.setattr(
        doctor_module, "os", SimpleNamespace(**(vars(os) | {"name": "nt"}))
    )
    monkeypatch.setattr(doctor_module, "_windows_acl_permission_issues", check_acl)
    results = AetherEngineDoctor(store.database_path).diagnose_backups()

    assert calls == [snapshot.parent, snapshot]
    assert results[1].status == ("FAIL" if unsafe else "OK")


@pytest.mark.skipif(os.name != "nt", reason="Requires native Windows ACLs")
def test_native_windows_database_and_backup_permissions(tmp_path: Path) -> None:
    store = AetherStore(tmp_path / "project.sqlite3")
    store.add_task("Native Windows persistence")
    write_backup(store)
    doctor = AetherEngineDoctor(store.database_path)

    assert doctor.diagnose_database().status == "OK"
    assert [result.status for result in doctor.diagnose_backups()] == ["OK", "OK"]
