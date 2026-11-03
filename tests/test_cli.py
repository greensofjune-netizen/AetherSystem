import json
import os
import sqlite3
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from aether_engine.cli import _resolve_database_path, main
from aether_engine.database import AetherStore, _secure_windows_file


def test_event_commands_persist_history(tmp_path: Path, capsys) -> None:
    database = str(tmp_path / "aether.sqlite3")

    assert main(
        [
            "--database",
            database,
            "event",
            "add",
            "Milestone reached",
            "--topic",
            "release",
        ]
    ) == 0
    assert "Recorded event #1 under 'release'." in capsys.readouterr().out

    assert main(["--database", database, "event", "list"]) == 0
    output = capsys.readouterr().out
    assert "release: Milestone reached" in output


def test_task_commands_create_list_and_complete(tmp_path: Path, capsys) -> None:
    database = str(tmp_path / "aether.sqlite3")

    assert main(
        [
            "--database",
            database,
            "task",
            "add",
            "Write tests",
            "--description",
            "Cover the CLI",
        ]
    ) == 0
    assert "Created task #1: Write tests" in capsys.readouterr().out

    assert main(
        ["--database", database, "task", "list", "--status", "pending"]
    ) == 0
    assert "[pending] Write tests - Cover the CLI" in capsys.readouterr().out

    assert main(["--database", database, "task", "complete", "1"]) == 0
    assert "Completed task #1: Write tests" in capsys.readouterr().out

    assert main(
        ["--database", database, "task", "list", "--status", "done"]
    ) == 0
    assert "[done] Write tests" in capsys.readouterr().out


def test_completing_unknown_task_returns_error(tmp_path: Path, capsys) -> None:
    result = main(
        [
            "--database",
            str(tmp_path / "aether.sqlite3"),
            "task",
            "complete",
            "42",
        ]
    )

    assert result == 1
    assert "Task #42 was not found." in capsys.readouterr().err


def test_status_dashboard_unifies_tasks_and_activity(
    tmp_path: Path, capsys
) -> None:
    database = str(tmp_path / "aether.sqlite3")
    assert main(["--database", database, "task", "add", "Ship dashboard"]) == 0
    capsys.readouterr()
    assert main(["--database", database, "task", "add", "Write release notes"]) == 0
    capsys.readouterr()
    assert main(["--database", database, "task", "complete", "1"]) == 0
    capsys.readouterr()
    assert main(
        [
            "--database",
            database,
            "event",
            "add",
            "Dashboard is ready",
            "--topic",
            "release",
        ]
    ) == 0
    capsys.readouterr()

    assert main(["--database", database, "status"]) == 0
    output = capsys.readouterr().out
    assert "AETHER ENGINE  /  PROJECT STATUS" in output
    assert "1 open   1 done   2 total" in output
    assert "50% complete" in output
    assert "#2  [NORMAL]  Write release notes" in output
    assert "release: Dashboard is ready" in output


def test_status_dashboard_handles_empty_project(tmp_path: Path, capsys) -> None:
    result = main(
        ["--database", str(tmp_path / "aether.sqlite3"), "status"]
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "0 open   0 done   0 total" in output
    assert "0% complete" in output
    assert "No open tasks." in output
    assert "No activity recorded." in output


def test_task_priority_and_due_date_show_on_dashboard(
    tmp_path: Path, capsys
) -> None:
    database = str(tmp_path / "aether.sqlite3")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    assert main(
        [
            "--database",
            database,
            "task",
            "add",
            "Past deadline",
            "--due",
            yesterday,
        ]
    ) == 0
    capsys.readouterr()
    assert main(
        [
            "--database",
            database,
            "task",
            "add",
            "High priority",
            "--priority",
            "high",
            "--due",
            tomorrow,
        ]
    ) == 0
    capsys.readouterr()

    assert main(["--database", database, "status"]) == 0
    output = capsys.readouterr().out
    assert "1 overdue" in output
    assert f"[NORMAL, OVERDUE {yesterday}]  Past deadline" in output
    assert f"[HIGH, DUE {tomorrow}]  High priority" in output
    assert output.index("Past deadline") < output.index("High priority")


def test_task_add_rejects_non_iso_due_date(tmp_path: Path, capsys) -> None:
    try:
        main(
            [
                "--database",
                str(tmp_path / "aether.sqlite3"),
                "task",
                "add",
                "Invalid date",
                "--due",
                "12/01/2026",
            ]
        )
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("Invalid due date should be rejected.")
    assert "must use YYYY-MM-DD format" in capsys.readouterr().err


def test_project_database_is_scoped_to_nearest_project_root(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    nested = project / "src" / "package"
    nested.mkdir(parents=True)
    (project / "pyproject.toml").write_text("", encoding="utf-8")
    standalone = tmp_path / "standalone"
    standalone.mkdir()

    assert _resolve_database_path(None, nested) == project / ".aether-engine.sqlite3"
    assert _resolve_database_path("custom.sqlite3", nested) == Path("custom.sqlite3")
    assert (
        _resolve_database_path(None, standalone)
        == standalone / ".aether-engine.sqlite3"
    )


def test_existing_task_database_is_migrated(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK (status IN ('pending', 'done')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO tasks
                (title, description, status, created_at, updated_at)
            VALUES ('Legacy task', '', 'pending', '2026-01-01', '2026-01-01')
            """
        )

    store = AetherStore(database)
    tasks = store.list_tasks()

    assert len(tasks) == 1
    assert tasks[0].title == "Legacy task"
    assert tasks[0].priority == "normal"
    assert tasks[0].due_date is None
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_schema_migrations_are_versioned_and_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "versioned.sqlite3"

    AetherStore(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2

    store = AetherStore(database)
    assert store.list_tasks() == []
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_newer_schema_version_is_rejected_without_downgrade(
    tmp_path: Path,
) -> None:
    database = tmp_path / "future.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 99")

    with pytest.raises(ValueError, match="newer than supported"):
        AetherStore(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 99


def test_failed_schema_migration_rolls_back_version_and_ddl(
    tmp_path: Path,
) -> None:
    database = tmp_path / "incomplete.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE events (
                id INTEGER PRIMARY KEY,
                topic TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute("PRAGMA user_version = 1")

    with pytest.raises(sqlite3.OperationalError, match="no such table: tasks"):
        AetherStore(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'tasks'"
        ).fetchone() is None


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes are not Windows ACLs")
def test_database_files_are_private_and_existing_modes_are_repaired(
    tmp_path: Path,
) -> None:
    database = tmp_path / "private.sqlite3"
    store = AetherStore(database)
    assert database.stat().st_mode & 0o777 == 0o600

    database.chmod(0o644)
    store.add_task("Repair database permissions")
    assert database.stat().st_mode & 0o777 == 0o600


def test_windows_database_acl_is_restricted_to_current_user(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[list[str]] = []
    path = tmp_path / "private database.sqlite3"

    def fake_icacls(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "Successfully processed", "")

    monkeypatch.setenv("USERDOMAIN", "AETHER")
    monkeypatch.setenv("USERNAME", "engine-user")
    monkeypatch.setattr("aether_engine.database.subprocess.run", fake_icacls)

    _secure_windows_file(path)

    assert calls == [
        [
            "icacls",
            str(path),
            "/reset",
            "/inheritance:r",
            "/grant:r",
            "AETHER\\engine-user:(F)",
        ]
    ]


def test_task_can_be_edited_and_reopened(tmp_path: Path, capsys) -> None:
    database = str(tmp_path / "aether.sqlite3")
    due_date = (date.today() + timedelta(days=3)).isoformat()

    assert main(
        [
            "--database",
            database,
            "task",
            "add",
            "Draft",
            "--description",
            "Old details",
        ]
    ) == 0
    capsys.readouterr()
    assert main(["--database", database, "task", "complete", "1"]) == 0
    capsys.readouterr()

    assert main(
        [
            "--database",
            database,
            "task",
            "edit",
            "1",
            "--title",
            "Publish",
            "--description",
            "Final details",
            "--priority",
            "high",
            "--due",
            due_date,
        ]
    ) == 0
    assert "Updated task #1: Publish" in capsys.readouterr().out

    store = AetherStore(database)
    edited = store.list_tasks()[0]
    assert edited.title == "Publish"
    assert edited.description == "Final details"
    assert edited.priority == "high"
    assert edited.due_date == due_date
    assert edited.status == "done"

    assert main(["--database", database, "task", "edit", "1", "--clear-due"]) == 0
    capsys.readouterr()
    assert store.list_tasks()[0].due_date is None

    assert main(["--database", database, "task", "reopen", "1"]) == 0
    assert "Reopened task #1: Publish" in capsys.readouterr().out
    assert store.list_tasks()[0].status == "pending"


def test_task_edit_requires_a_field_and_reports_missing_task(
    tmp_path: Path, capsys
) -> None:
    database = str(tmp_path / "aether.sqlite3")
    assert main(["--database", database, "task", "edit", "1"]) == 1
    assert "Provide at least one field" in capsys.readouterr().err

    assert main(
        ["--database", database, "task", "edit", "1", "--title", "Missing"]
    ) == 1
    assert "Task #1 was not found." in capsys.readouterr().err


def test_export_writes_json_and_refuses_to_overwrite(
    tmp_path: Path, capsys
) -> None:
    database = str(tmp_path / "aether.sqlite3")
    output = tmp_path / "export.json"
    assert main(["--database", database, "task", "add", "Export me"]) == 0
    capsys.readouterr()
    assert main(
        ["--database", database, "event", "add", "Exported event", "--topic", "test"]
    ) == 0
    capsys.readouterr()

    assert main(["--database", database, "export", str(output)]) == 0
    assert "Exported project data" in capsys.readouterr().out
    if os.name != "nt":
        assert output.stat().st_mode & 0o777 == 0o600
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["tasks"][0]["title"] == "Export me"
    assert payload["events"][0]["topic"] == "test"
    assert payload["events"][0]["message"] == "Exported event"

    assert main(["--database", database, "export", str(output)]) == 1
    assert "File exists" in capsys.readouterr().err

    assert main(["--database", database, "export", str(output), "--force"]) == 0
    capsys.readouterr()
    assert json.loads(output.read_text(encoding="utf-8"))["tasks"][0]["title"] == (
        "Export me"
    )
    if os.name != "nt":
        assert output.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(os.name == "nt", reason="symlink permissions vary on Windows")
def test_export_refuses_symlink_destination(tmp_path: Path, capsys) -> None:
    database = tmp_path / "aether.sqlite3"
    target = tmp_path / "sensitive.txt"
    target.write_text("unchanged", encoding="utf-8")
    destination = tmp_path / "export.json"
    destination.symlink_to(target)

    assert main(
        [
            "--database",
            str(database),
            "export",
            str(destination),
            "--force",
        ]
    ) == 1
    assert "cannot be a symlink" in capsys.readouterr().err
    assert target.read_text(encoding="utf-8") == "unchanged"


@pytest.mark.skipif(os.name == "nt", reason="symlink permissions vary on Windows")
def test_backup_refuses_symlink_directory_without_changing_target(
    tmp_path: Path,
) -> None:
    from aether_engine.backups import write_backup

    database = tmp_path / "project.sqlite3"
    store = AetherStore(database)
    target_directory = tmp_path / "shared"
    target_directory.mkdir()
    target_directory.chmod(0o755)
    backup_link = tmp_path / ".aether-backups"
    backup_link.symlink_to(target_directory, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink as the backup directory"):
        write_backup(store, backup_link)

    assert target_directory.stat().st_mode & 0o777 == 0o755


def test_export_stdout_and_database_path_protection(
    tmp_path: Path, capsys
) -> None:
    database = tmp_path / "aether.sqlite3"
    assert main(["--database", str(database), "export"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["tasks"] == []

    assert main(
        ["--database", str(database), "export", str(database), "--force"]
    ) == 1
    assert "cannot be the database file" in capsys.readouterr().err


def test_restore_round_trip_and_requires_replace_for_existing_data(
    tmp_path: Path, capsys
) -> None:
    source_db = tmp_path / "source.sqlite3"
    backup = tmp_path / "backup.json"
    destination_db = tmp_path / "destination.sqlite3"

    source = AetherStore(source_db)
    task = source.add_task(
        "Restore this", "Preserve metadata", "high", "2026-12-01"
    )
    source.complete_task(task.id)
    source.add_event("backup", "History is included")
    backup.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "exported_at": "2026-11-02T18:00:00+00:00",
                **source.export_data(),
            }
        ),
        encoding="utf-8",
    )

    destination = AetherStore(destination_db)
    assert main(["--database", str(destination_db), "restore", str(backup)]) == 0
    assert "Restored 1 task(s) and 1 event(s)" in capsys.readouterr().out
    assert destination.export_data() == source.export_data()

    destination.add_task("Keep until replacement is confirmed")
    assert main(["--database", str(destination_db), "restore", str(backup)]) == 1
    assert "use --replace" in capsys.readouterr().err
    assert [task.title for task in destination.list_tasks()] == [
        "Keep until replacement is confirmed",
        "Restore this",
    ]

    assert (
        main(
            [
                "--database",
                str(destination_db),
                "restore",
                str(backup),
                "--replace",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert destination.export_data() == source.export_data()


def test_invalid_restore_does_not_change_existing_database(
    tmp_path: Path, capsys
) -> None:
    database = tmp_path / "existing.sqlite3"
    backup = tmp_path / "invalid.json"
    store = AetherStore(database)
    store.add_task("Must survive")
    before = store.export_data()
    backup.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "exported_at": "2026-11-02T18:00:00+00:00",
                "tasks": [
                    {
                        "id": 1,
                        "title": "Invalid replacement",
                        "description": "",
                        "status": "in_progress",
                        "priority": "high",
                        "due_date": None,
                        "created_at": "2026-11-02T18:00:00+00:00",
                        "updated_at": "2026-11-02T18:00:00+00:00",
                    }
                ],
                "events": [],
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--database",
                str(database),
                "restore",
                str(backup),
                "--replace",
            ]
        )
        == 1
    )
    assert "invalid status" in capsys.readouterr().err
    assert store.export_data() == before


def test_restore_rejects_database_as_input_and_bad_json(
    tmp_path: Path, capsys
) -> None:
    database = tmp_path / "data.sqlite3"
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{", encoding="utf-8")

    assert main(
        ["--database", str(database), "restore", str(database)]
    ) == 1
    assert "cannot be the database file" in capsys.readouterr().err

    assert main(
        ["--database", str(database), "restore", str(bad_json)]
    ) == 1
    assert "error:" in capsys.readouterr().err


def test_task_search_filters_title_and_description_with_status(
    tmp_path: Path, capsys
) -> None:
    database = str(tmp_path / "search.sqlite3")
    store = AetherStore(database)
    first = store.add_task("Prepare launch", "Draft the checklist")
    store.add_task("Review notes", "Checklist for launch")
    store.complete_task(first.id)

    assert main(
        [
            "--database",
            database,
            "task",
            "list",
            "--search",
            "CHECKLIST",
            "--status",
            "pending",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert "Review notes" in output
    assert "Prepare launch" not in output

    assert main(
        ["--database", database, "task", "list", "--search", "launch"]
    ) == 0
    output = capsys.readouterr().out
    assert "Prepare launch" in output
    assert "Checklist for launch" in output


def test_event_search_topic_and_date_filters(tmp_path: Path, capsys) -> None:
    database = str(tmp_path / "events.sqlite3")
    store = AetherStore(database)
    store.add_event("release", "Build shipped")
    store.add_event("ops", "Build monitored")
    today = datetime.now(timezone.utc).date().isoformat()

    assert main(
        [
            "--database",
            database,
            "event",
            "list",
            "--search",
            "BUILD",
            "--topic",
            "release",
            "--since",
            today,
            "--until",
            today,
        ]
    ) == 0
    output = capsys.readouterr().out
    assert "release: Build shipped" in output
    assert "ops: Build monitored" not in output

    assert main(
        [
            "--database",
            database,
            "event",
            "list",
            "--since",
            today,
            "--until",
            (date.today() - timedelta(days=1)).isoformat(),
        ]
    ) == 1
    assert "Start date must be on or before end date." in capsys.readouterr().err


def test_backup_creates_dated_json_in_selected_directory(
    tmp_path: Path, capsys
) -> None:
    database = tmp_path / "data.sqlite3"
    backup_directory = tmp_path / "dated-backups"
    store = AetherStore(database)
    store.add_task("Keep this backup")
    store.add_event("test", "Backup content")

    assert main(
        [
            "--database",
            str(database),
            "backup",
            "--directory",
            str(backup_directory),
        ]
    ) == 0
    output = capsys.readouterr().out
    backup_files = list(backup_directory.glob("aether-backup-*.json"))
    assert len(backup_files) == 1
    assert str(backup_files[0]) in output
    assert backup_directory.stat().st_mode & 0o777 == 0o700
    assert backup_files[0].stat().st_mode & 0o777 == 0o600
    payload = json.loads(backup_files[0].read_text(encoding="utf-8"))
    assert payload["tasks"][0]["title"] == "Keep this backup"
    assert payload["events"][0]["message"] == "Backup content"


def test_backup_prunes_only_old_aether_snapshots_to_retention_limit(
    tmp_path: Path, capsys
) -> None:
    database = tmp_path / "data.sqlite3"
    backup_directory = tmp_path / "backups"
    store = AetherStore(database)
    store.add_task("Retention test")
    backup_directory.mkdir()
    unrelated = backup_directory / "aether-backup-not-a-timestamp.json"
    unrelated.write_text("keep me", encoding="utf-8")
    log_file = backup_directory / "launchd.stdout.log"
    log_file.write_text("keep log", encoding="utf-8")

    created: list[Path] = []
    for _ in range(4):
        assert main(
            [
                "--database",
                str(database),
                "backup",
                "--directory",
                str(backup_directory),
                "--keep",
                "2",
            ]
        ) == 0
        capsys.readouterr()
        current_snapshots = list(
            backup_directory.glob("aether-backup-????????T??????.??????Z.json")
        )
        created.append(max(current_snapshots, key=lambda path: path.name))

    snapshots = sorted(backup_directory.glob("aether-backup-????????T??????.??????Z.json"))
    assert len(snapshots) == 2
    assert set(snapshots) == set(created[-2:])
    assert unrelated.read_text(encoding="utf-8") == "keep me"
    assert log_file.read_text(encoding="utf-8") == "keep log"
    for snapshot in snapshots:
        assert json.loads(snapshot.read_text(encoding="utf-8"))["tasks"][0][
            "title"
        ] == "Retention test"


def test_backup_retention_requires_at_least_one(tmp_path: Path, capsys) -> None:
    with pytest.raises(SystemExit) as error:
        main(
            [
                "--database",
                str(tmp_path / "data.sqlite3"),
                "backup",
                "--keep",
                "0",
            ]
        )
    assert error.value.code == 2
    assert "must be at least 1" in capsys.readouterr().err


def test_backup_secures_existing_snapshots_and_logs(tmp_path: Path, capsys) -> None:
    database = tmp_path / "data.sqlite3"
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir(mode=0o755)
    old_backup = backup_directory / "aether-backup-20260101T000000.000000Z.json"
    old_backup.write_text("{}", encoding="utf-8")
    old_backup.chmod(0o644)
    launch_log = backup_directory / "launchd.stderr.log"
    launch_log.write_text("old log", encoding="utf-8")
    launch_log.chmod(0o644)
    backup_directory.chmod(0o755)

    assert main(
        [
            "--database",
            str(database),
            "backup",
            "--directory",
            str(backup_directory),
        ]
    ) == 0
    capsys.readouterr()

    assert backup_directory.stat().st_mode & 0o777 == 0o700
    assert old_backup.stat().st_mode & 0o777 == 0o600
    assert launch_log.stat().st_mode & 0o777 == 0o600


def test_replace_restore_creates_safety_backup(tmp_path: Path, capsys) -> None:
    database = tmp_path / "data.sqlite3"
    restore_file = tmp_path / "restore.json"
    store = AetherStore(database)
    store.add_task("Current data")
    restore_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "exported_at": "2026-11-02T18:00:00+00:00",
                "tasks": [],
                "events": [],
            }
        ),
        encoding="utf-8",
    )

    assert main(
        [
            "--database",
            str(database),
            "restore",
            str(restore_file),
            "--replace",
        ]
    ) == 0
    output = capsys.readouterr().out
    backups = list((tmp_path / ".aether-backups").glob("aether-backup-*.json"))
    assert len(backups) == 1
    assert str(backups[0]) in output
    assert json.loads(backups[0].read_text(encoding="utf-8"))["tasks"][0]["title"] == (
        "Current data"
    )
    assert store.list_tasks() == []
