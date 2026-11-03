from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from collections.abc import Sequence
from datetime import date, datetime, timezone
from pathlib import Path

from .backups import DEFAULT_BACKUP_RETENTION, write_backup
from .database import AetherStore
from .engine_doctor import AetherEngineDoctor
from .historian import CoPilotHistorian
from .scheduler import (
    SchedulerError,
    backup_schedule_status,
    install_backup_schedule,
    uninstall_backup_schedule,
)

_DASHBOARD_WIDTH = 68
_ANSI = {
    "cyan": "\033[96m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "dim": "\033[2m",
    "reset": "\033[0m",
}


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _iso_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must use YYYY-MM-DD format") from error
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("must use YYYY-MM-DD format")
    return value


def _resolve_database_path(
    database: str | None, cwd: Path | None = None
) -> Path:
    if database is not None:
        return Path(database)

    directory = (cwd or Path.cwd()).resolve()
    project_root = next(
        (parent for parent in (directory, *directory.parents)
         if (parent / "pyproject.toml").is_file()),
        directory,
    )
    return project_root / ".aether-engine.sqlite3"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aether-engine",
        description="Track project tasks and record a searchable event history.",
    )
    parser.add_argument(
        "--database",
        help="SQLite database path (default: project-local .aether-engine.sqlite3)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "doctor", help="check database, backups, permissions, and scheduled backup health"
    )

    event_parser = commands.add_parser("event", help="record or view project events")
    event_commands = event_parser.add_subparsers(dest="action", required=True)
    event_add = event_commands.add_parser("add", help="record an event")
    event_add.add_argument("message", help="what happened")
    event_add.add_argument("--topic", default="general", help="event topic")
    event_list = event_commands.add_parser("list", help="show recent events")
    event_list.add_argument("--limit", type=_positive_int, default=20)
    event_list.add_argument("--search", help="search event topic and message")
    event_list.add_argument("--topic", help="filter by exact topic")
    event_list.add_argument(
        "--since", type=_iso_date, metavar="YYYY-MM-DD", help="include events on/after date"
    )
    event_list.add_argument(
        "--until", type=_iso_date, metavar="YYYY-MM-DD", help="include events on/before date"
    )

    task_parser = commands.add_parser("task", help="manage project tasks")
    task_commands = task_parser.add_subparsers(dest="action", required=True)
    task_add = task_commands.add_parser("add", help="create a task")
    task_add.add_argument("title", help="short task title")
    task_add.add_argument("--description", default="", help="additional details")
    task_add.add_argument(
        "--priority", choices=("low", "normal", "high"), default="normal"
    )
    task_add.add_argument(
        "--due", type=_iso_date, metavar="YYYY-MM-DD", help="task due date"
    )
    task_list = task_commands.add_parser("list", help="show tasks")
    task_list.add_argument("--status", choices=("pending", "done"))
    task_list.add_argument(
        "--search", help="search task titles and descriptions"
    )
    task_complete = task_commands.add_parser("complete", help="complete a task")
    task_complete.add_argument("task_id", type=_positive_int)
    task_edit = task_commands.add_parser("edit", help="edit a task")
    task_edit.add_argument("task_id", type=_positive_int)
    task_edit.add_argument("--title", help="replace the task title")
    task_edit.add_argument("--description", help="replace the task description")
    task_edit.add_argument(
        "--priority", choices=("low", "normal", "high"), help="replace priority"
    )
    due_group = task_edit.add_mutually_exclusive_group()
    due_group.add_argument(
        "--due", type=_iso_date, metavar="YYYY-MM-DD", help="replace due date"
    )
    due_group.add_argument(
        "--clear-due", action="store_true", help="remove the due date"
    )
    task_reopen = task_commands.add_parser(
        "reopen", help="reopen a completed task"
    )
    task_reopen.add_argument("task_id", type=_positive_int)

    commands.add_parser("status", help="show the project status dashboard")
    export_parser = commands.add_parser(
        "export", help="export tasks and events as JSON"
    )
    export_parser.add_argument(
        "output",
        nargs="?",
        help="write JSON to this new file (default: print to stdout)",
    )
    export_parser.add_argument(
        "--force", action="store_true", help="overwrite an existing output file"
    )
    restore_parser = commands.add_parser(
        "restore", help="restore tasks and events from a JSON export"
    )
    restore_parser.add_argument("backup", help="path to a JSON export")
    restore_parser.add_argument(
        "--replace",
        action="store_true",
        help="replace all existing tasks and events in the selected database",
    )
    backup_parser = commands.add_parser("backup", help="create and manage backups")
    backup_parser.add_argument(
        "--directory",
        help="backup directory (default: .aether-backups beside the database)",
    )
    backup_parser.add_argument(
        "--keep",
        type=_positive_int,
        default=DEFAULT_BACKUP_RETENTION,
        help=f"number of timestamped backups to retain (default: {DEFAULT_BACKUP_RETENTION})",
    )
    backup_commands = backup_parser.add_subparsers(dest="backup_action")
    schedule_parser = backup_commands.add_parser(
        "schedule", help="manage the daily backup schedule"
    )
    schedule_commands = schedule_parser.add_subparsers(
        dest="schedule_action", required=True
    )
    schedule_install = schedule_commands.add_parser(
        "install", help="run a backup daily at 9:00 AM"
    )
    schedule_install.add_argument(
        "--keep",
        type=_positive_int,
        default=DEFAULT_BACKUP_RETENTION,
        help=f"number of timestamped backups to retain (default: {DEFAULT_BACKUP_RETENTION})",
    )
    schedule_commands.add_parser("status", help="show schedule installation status")
    schedule_commands.add_parser("uninstall", help="remove the daily backup schedule")
    return parser


def _export_payload(store: AetherStore) -> dict[str, object]:
    return {
        "schema_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        **store.export_data(),
    }


def _write_export_file(path: Path, serialized: str, *, force: bool) -> None:
    if path.is_symlink():
        raise ValueError(f"Export output cannot be a symlink: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output_file:
            output_file.write(serialized)
            output_file.flush()
            os.fsync(output_file.fileno())
        if os.name != "nt":
            temporary_path.chmod(0o600)
        if force:
            os.replace(temporary_path, path)
        else:
            os.link(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _dashboard_color_enabled() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _dashboard_line(text: str = "", color: str | None = None) -> str:
    text = text[:_DASHBOARD_WIDTH - 2]
    content = f" {text:<{_DASHBOARD_WIDTH - 2}} "
    if color and _dashboard_color_enabled():
        content = f"{_ANSI[color]}{content}{_ANSI['reset']}"
    return f"│{content}│"


def _dashboard_section(title: str) -> None:
    print(f"├{'─' * _DASHBOARD_WIDTH}┤")
    print(_dashboard_line(title, "cyan"))


def _print_dashboard(store: AetherStore) -> None:
    snapshot = store.dashboard_snapshot()
    total = snapshot.pending_count + snapshot.done_count
    percent = round(snapshot.done_count / total * 100) if total else 0
    filled = round(percent / 100 * 12)
    progress = f"[{'■' * filled}{'·' * (12 - filled)}] {percent:3}% complete"

    print(f"╭{'─' * _DASHBOARD_WIDTH}╮")
    print(_dashboard_line("AETHER ENGINE  /  PROJECT STATUS", "cyan"))
    print(f"├{'─' * _DASHBOARD_WIDTH}┤")
    print(
        _dashboard_line(
            f"TASKS     {snapshot.pending_count} open   "
            f"{snapshot.done_count} done   {total} total   "
            f"{snapshot.overdue_count} overdue"
        )
    )
    print(_dashboard_line(progress, "green"))

    _dashboard_section("NEXT UP")
    if snapshot.pending_tasks:
        for task in snapshot.pending_tasks:
            details = [task.priority.upper()]
            if task.due_date:
                marker = (
                    "OVERDUE"
                    if task.due_date < date.today().isoformat()
                    else "DUE"
                )
                details.append(f"{marker} {task.due_date}")
            print(
                _dashboard_line(
                    f"#{task.id}  [{', '.join(details)}]  {task.title}",
                    "yellow" if task.priority == "high" or task.due_date else None,
                )
            )
    else:
        print(
            _dashboard_line(
                "No open tasks. Add one with: aether-engine task add \"...\""
            )
        )

    _dashboard_section("RECENT ACTIVITY")
    if snapshot.recent_events:
        for event in snapshot.recent_events:
            timestamp = datetime.fromisoformat(event.created_at).astimezone(
                timezone.utc
            )
            when = timestamp.strftime("%b %d %H:%M UTC")
            print(
                _dashboard_line(
                    f"#{event.id}  {when}  {event.topic}: {event.message}", "dim"
                )
            )
    else:
        print(
            _dashboard_line(
                "No activity recorded. Add one with: aether-engine event add \"...\""
            )
        )
    print(f"╰{'─' * _DASHBOARD_WIDTH}╯")


def _print_events(
    historian: CoPilotHistorian,
    limit: int,
    *,
    search: str | None,
    topic: str | None,
    since: str | None,
    until: str | None,
) -> None:
    events = historian.history(
        limit, search=search, topic=topic, since=since, until=until
    )
    if not events:
        print("No events recorded.")
        return
    for event in events:
        print(f"#{event.id} [{event.created_at}] {event.topic}: {event.message}")


def _print_tasks(
    store: AetherStore, status: str | None, search: str | None
) -> None:
    tasks = store.list_tasks(status, search)
    if not tasks:
        print("No tasks found.")
        return
    for task in tasks:
        description = f" - {task.description}" if task.description else ""
        details = f" [{task.priority} priority]"
        if task.due_date:
            details += f" [due {task.due_date}]"
        print(f"#{task.id} [{task.status}] {task.title}{description}{details}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        database_path = _resolve_database_path(args.database)
        if args.command == "doctor":
            doctor = AetherEngineDoctor(database_path)
            return doctor.execute_complete_medical_sweep()

        store = AetherStore(database_path)
        historian = CoPilotHistorian(store)

        if args.command == "event":
            if args.action == "add":
                event = historian.record(args.topic, args.message)
                print(f"Recorded event #{event.id} under '{event.topic}'.")
            else:
                _print_events(
                    historian,
                    args.limit,
                    search=args.search,
                    topic=args.topic,
                    since=args.since,
                    until=args.until,
                )
        elif args.command == "task":
            if args.action == "add":
                task = store.add_task(
                    args.title, args.description, args.priority, args.due
                )
                details = []
                if task.priority != "normal":
                    details.append(f"{task.priority} priority")
                if task.due_date:
                    details.append(f"due {task.due_date}")
                suffix = f" ({', '.join(details)})" if details else ""
                print(f"Created task #{task.id}: {task.title}{suffix}")
            elif args.action == "list":
                _print_tasks(store, args.status, args.search)
            elif args.action == "complete":
                completed_task = store.complete_task(args.task_id)
                if completed_task is None:
                    print(f"Task #{args.task_id} was not found.", file=sys.stderr)
                    return 1
                print(f"Completed task #{completed_task.id}: {completed_task.title}")
            elif args.action == "reopen":
                reopened_task = store.reopen_task(args.task_id)
                if reopened_task is None:
                    print(f"Task #{args.task_id} was not found.", file=sys.stderr)
                    return 1
                print(f"Reopened task #{reopened_task.id}: {reopened_task.title}")
            else:
                updated_task = store.update_task(
                    args.task_id,
                    title=args.title,
                    description=args.description,
                    priority=args.priority,
                    due_date=args.due,
                    clear_due_date=args.clear_due,
                )
                if updated_task is None:
                    print(f"Task #{args.task_id} was not found.", file=sys.stderr)
                    return 1
                print(f"Updated task #{updated_task.id}: {updated_task.title}")
        elif args.command == "status":
            _print_dashboard(store)
        elif args.command == "export":
            if args.force and args.output is None:
                raise ValueError("--force requires an output file.")
            payload = _export_payload(store)
            serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
            if args.output is None:
                sys.stdout.write(serialized)
            else:
                output_path = Path(args.output)
                if output_path.resolve() == store.database_path.resolve():
                    raise ValueError("Export output cannot be the database file.")
                _write_export_file(output_path, serialized, force=args.force)
                print(f"Exported project data to {output_path}.")
        elif args.command == "restore":
            backup_path = Path(args.backup)
            if backup_path.resolve() == store.database_path.resolve():
                raise ValueError("Restore input cannot be the database file.")
            with backup_path.open(encoding="utf-8") as backup_file:
                payload = json.load(backup_file)
            if args.replace:
                store.validate_export(payload)
                current_data = store.export_data()
                if current_data["tasks"] or current_data["events"]:
                    safety_backup, pruned = write_backup(store)
                    print(f"Safety backup created: {safety_backup}")
                    if pruned:
                        print(f"Pruned {pruned} expired backup(s).")
            task_count, event_count = store.restore_data(
                payload, replace=args.replace
            )
            print(
                f"Restored {task_count} task(s) and {event_count} event(s) "
                f"from {backup_path}."
            )
        elif args.command == "backup":
            if args.backup_action is None:
                directory = Path(args.directory) if args.directory else None
                backup_path, pruned = write_backup(
                    store, directory, keep=args.keep
                )
                print(f"Backup created: {backup_path}")
                print(f"Retaining the newest {args.keep} backup(s).")
                if pruned:
                    print(f"Pruned {pruned} expired backup(s).")
            elif args.schedule_action == "install":
                agent_path = install_backup_schedule(
                    store.database_path, keep=args.keep
                )
                print(
                    f"Daily 9:00 AM backup schedule installed "
                    f"(retaining {args.keep} backups): {agent_path}"
                )
            elif args.schedule_action == "status":
                agent_path, installed, loaded, last_exit_code = (
                    backup_schedule_status(store.database_path)
                )
                if installed and loaded:
                    print(f"Daily 9:00 AM backup schedule is active: {agent_path}")
                elif installed:
                    print(
                        f"Schedule file exists but is not loaded: {agent_path}"
                    )
                else:
                    print("No daily backup schedule is installed.")
                if installed:
                    if last_exit_code is None:
                        print("Last run result is not available yet.")
                    elif last_exit_code == 0:
                        print("Last scheduled backup succeeded (exit code 0).")
                    else:
                        error_log = (
                            store.database_path.parent
                            / ".aether-backups"
                            / "launchd.stderr.log"
                        )
                        print(
                            f"Last scheduled backup FAILED (exit code "
                            f"{last_exit_code}); see {error_log}.",
                            file=sys.stderr,
                        )
                        return 1
            else:
                agent_path, removed = uninstall_backup_schedule(
                    store.database_path
                )
                if removed:
                    print(f"Daily backup schedule removed: {agent_path}")
                else:
                    print("No daily backup schedule is installed.")
    except (OSError, sqlite3.Error, ValueError, SchedulerError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
