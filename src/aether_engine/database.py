from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Generator


@dataclass(frozen=True)
class Event:
    id: int
    topic: str
    message: str
    created_at: str


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    description: str
    status: str
    priority: str
    due_date: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DashboardSnapshot:
    pending_count: int
    done_count: int
    overdue_count: int
    pending_tasks: list[Task]
    recent_events: list[Event]


class AetherStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY,
                    topic TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK (status IN ('pending', 'done')),
                    priority TEXT NOT NULL DEFAULT 'normal'
                        CHECK (priority IN ('low', 'normal', 'high')),
                    due_date TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            task_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(tasks)")
            }
            if "priority" not in task_columns:
                connection.execute(
                    """
                    ALTER TABLE tasks
                    ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'
                    CHECK (priority IN ('low', 'normal', 'high'))
                    """
                )
            if "due_date" not in task_columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN due_date TEXT")

    def add_event(self, topic: str, message: str) -> Event:
        topic = topic.strip()
        message = message.strip()
        if not topic:
            raise ValueError("Event topic cannot be empty.")
        if not message:
            raise ValueError("Event message cannot be empty.")

        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO events (topic, message, created_at) VALUES (?, ?, ?)",
                (topic, message, created_at),
            )
            row = connection.execute(
                "SELECT * FROM events WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        assert row is not None
        return Event(**dict(row))

    def list_events(
        self,
        limit: int = 20,
        *,
        search: str | None = None,
        topic: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[Event]:
        if limit < 1:
            raise ValueError("Event limit must be at least 1.")
        filters: list[str] = []
        values: list[object] = []
        if search is not None:
            search = search.strip()
            if not search:
                raise ValueError("Event search cannot be empty.")
            pattern = self._search_pattern(search)
            filters.append("(topic LIKE ? ESCAPE '\\' OR message LIKE ? ESCAPE '\\')")
            values.extend((pattern, pattern))
        if topic is not None:
            topic = topic.strip()
            if not topic:
                raise ValueError("Event topic filter cannot be empty.")
            filters.append("topic = ?")
            values.append(topic)
        if since is not None:
            self._validate_date(since, "Start date")
            filters.append("substr(created_at, 1, 10) >= ?")
            values.append(since)
        if until is not None:
            self._validate_date(until, "End date")
            filters.append("substr(created_at, 1, 10) <= ?")
            values.append(until)
        if since is not None and until is not None and since > until:
            raise ValueError("Start date must be on or before end date.")

        where_clause = f" WHERE {' AND '.join(filters)}" if filters else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM events{where_clause} ORDER BY id DESC LIMIT ?",
                (*values, limit),
            ).fetchall()
        return [Event(**dict(row)) for row in rows]

    def add_task(
        self,
        title: str,
        description: str = "",
        priority: str = "normal",
        due_date: str | None = None,
    ) -> Task:
        title = title.strip()
        if not title:
            raise ValueError("Task title cannot be empty.")
        if priority not in ("low", "normal", "high"):
            raise ValueError("Task priority must be 'low', 'normal', or 'high'.")
        if due_date is not None:
            try:
                parsed_due_date = date.fromisoformat(due_date)
            except ValueError as error:
                raise ValueError("Due date must use YYYY-MM-DD format.") from error
            if parsed_due_date.isoformat() != due_date:
                raise ValueError("Due date must use YYYY-MM-DD format.")

        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tasks
                    (title, description, status, priority, due_date, created_at, updated_at)
                VALUES (?, ?, 'pending', ?, ?, ?, ?)
                """,
                (title, description.strip(), priority, due_date, now, now),
            )
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        assert row is not None
        return Task(**dict(row))

    def list_tasks(
        self, status: str | None = None, search: str | None = None
    ) -> list[Task]:
        if status not in (None, "pending", "done"):
            raise ValueError("Task status must be 'pending' or 'done'.")
        filters: list[str] = []
        values: list[object] = []
        if status is not None:
            filters.append("status = ?")
            values.append(status)
        if search is not None:
            search = search.strip()
            if not search:
                raise ValueError("Task search cannot be empty.")
            pattern = self._search_pattern(search)
            filters.append(
                "(title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')"
            )
            values.extend((pattern, pattern))
        where_clause = f" WHERE {' AND '.join(filters)}" if filters else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM tasks{where_clause} ORDER BY id DESC",
                values,
            ).fetchall()
        return [Task(**dict(row)) for row in rows]

    @staticmethod
    def _search_pattern(search: str) -> str:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    @staticmethod
    def _validate_date(value: str, label: str) -> None:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{label} must use YYYY-MM-DD format.") from error
        if parsed.isoformat() != value:
            raise ValueError(f"{label} must use YYYY-MM-DD format.")

    def complete_task(self, task_id: int) -> Task | None:
        return self._set_task_status(task_id, "done")

    def reopen_task(self, task_id: int) -> Task | None:
        return self._set_task_status(task_id, "pending")

    def _set_task_status(self, task_id: int, status: str) -> Task | None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, task_id),
            )
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return Task(**dict(row)) if row is not None else None

    def update_task(
        self,
        task_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        due_date: str | None = None,
        clear_due_date: bool = False,
    ) -> Task | None:
        if not any(
            value is not None for value in (title, description, priority, due_date)
        ) and not clear_due_date:
            raise ValueError("Provide at least one field to update.")
        if clear_due_date and due_date is not None:
            raise ValueError("Cannot set and clear the due date at the same time.")
        if title is not None:
            title = title.strip()
            if not title:
                raise ValueError("Task title cannot be empty.")
        if priority is not None and priority not in ("low", "normal", "high"):
            raise ValueError("Task priority must be 'low', 'normal', or 'high'.")
        if due_date is not None:
            try:
                parsed_due_date = date.fromisoformat(due_date)
            except ValueError as error:
                raise ValueError("Due date must use YYYY-MM-DD format.") from error
            if parsed_due_date.isoformat() != due_date:
                raise ValueError("Due date must use YYYY-MM-DD format.")

        updates: list[tuple[str, object]] = []
        if title is not None:
            updates.append(("title", title))
        if description is not None:
            updates.append(("description", description.strip()))
        if priority is not None:
            updates.append(("priority", priority))
        if due_date is not None or clear_due_date:
            updates.append(("due_date", due_date))

        now = datetime.now(timezone.utc).isoformat()
        assignments = ", ".join(f"{column} = ?" for column, _ in updates)
        values = [value for _, value in updates]
        with self._connect() as connection:
            connection.execute(
                f"UPDATE tasks SET {assignments}, updated_at = ? WHERE id = ?",
                (*values, now, task_id),
            )
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return Task(**dict(row)) if row is not None else None

    def dashboard_snapshot(
        self, limit: int = 3, today: date | None = None
    ) -> DashboardSnapshot:
        if limit < 1:
            raise ValueError("Dashboard limit must be at least 1.")
        current_date = (today or date.today()).isoformat()
        with self._connect() as connection:
            task_counts = connection.execute(
                "SELECT status, COUNT(*) AS count FROM tasks GROUP BY status"
            ).fetchall()
            counts = {row["status"]: row["count"] for row in task_counts}
            overdue_count = connection.execute(
                """
                SELECT COUNT(*) AS count FROM tasks
                WHERE status = 'pending' AND due_date < ?
                """,
                (current_date,),
            ).fetchone()["count"]
            pending_tasks = connection.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'pending'
                ORDER BY
                    CASE WHEN due_date < ? THEN 0 ELSE 1 END,
                    CASE priority
                        WHEN 'high' THEN 0
                        WHEN 'normal' THEN 1
                        ELSE 2
                    END,
                    due_date IS NULL,
                    due_date ASC,
                    id ASC
                LIMIT ?
                """,
                (current_date, limit),
            ).fetchall()
            recent_events = connection.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return DashboardSnapshot(
            pending_count=counts.get("pending", 0),
            done_count=counts.get("done", 0),
            overdue_count=overdue_count,
            pending_tasks=[Task(**dict(row)) for row in pending_tasks],
            recent_events=[Event(**dict(row)) for row in recent_events],
        )

    def export_data(self) -> dict[str, list[dict[str, object]]]:
        with self._connect() as connection:
            tasks = connection.execute("SELECT * FROM tasks ORDER BY id").fetchall()
            events = connection.execute("SELECT * FROM events ORDER BY id").fetchall()
        return {
            "tasks": [dict(row) for row in tasks],
            "events": [dict(row) for row in events],
        }

    def restore_data(self, payload: object, *, replace: bool = False) -> tuple[int, int]:
        tasks, events = self.validate_export(payload)
        with self._connect() as connection:
            if not replace:
                task_count = connection.execute(
                    "SELECT COUNT(*) FROM tasks"
                ).fetchone()[0]
                event_count = connection.execute(
                    "SELECT COUNT(*) FROM events"
                ).fetchone()[0]
                if task_count or event_count:
                    raise ValueError(
                        "Database is not empty; use --replace to replace its data."
                    )
            else:
                connection.execute("DELETE FROM tasks")
                connection.execute("DELETE FROM events")

            connection.executemany(
                """
                INSERT INTO tasks
                    (id, title, description, status, priority, due_date,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        task["id"],
                        task["title"],
                        task["description"],
                        task["status"],
                        task["priority"],
                        task["due_date"],
                        task["created_at"],
                        task["updated_at"],
                    )
                    for task in tasks
                ],
            )
            connection.executemany(
                """
                INSERT INTO events (id, topic, message, created_at)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        event["id"],
                        event["topic"],
                        event["message"],
                        event["created_at"],
                    )
                    for event in events
                ],
            )
        return len(tasks), len(events)

    @staticmethod
    def validate_export(
        payload: object,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        if not isinstance(payload, dict):
            raise ValueError("Backup must contain a JSON object.")
        if type(payload.get("schema_version")) is not int:
            raise ValueError("Backup schema_version must be an integer.")
        if payload["schema_version"] != 1:
            raise ValueError(
                f"Unsupported backup schema version: {payload['schema_version']}."
            )
        exported_at = payload.get("exported_at")
        if not isinstance(exported_at, str):
            raise ValueError("Backup exported_at must be a timestamp.")
        try:
            datetime.fromisoformat(exported_at)
        except ValueError as error:
            raise ValueError("Backup exported_at must be a valid ISO timestamp.") from error

        raw_tasks = payload.get("tasks")
        raw_events = payload.get("events")
        if not isinstance(raw_tasks, list) or not isinstance(raw_events, list):
            raise ValueError("Backup tasks and events must be JSON arrays.")

        tasks: list[dict[str, object]] = []
        events: list[dict[str, object]] = []
        task_ids: set[int] = set()
        event_ids: set[int] = set()

        for index, value in enumerate(raw_tasks):
            if not isinstance(value, dict):
                raise ValueError(f"Backup task at index {index} must be an object.")
            task = dict(value)
            required = {
                "id", "title", "description", "status", "priority",
                "due_date", "created_at", "updated_at",
            }
            if not required.issubset(task):
                raise ValueError(f"Backup task at index {index} is missing fields.")
            task_id = task["id"]
            if type(task_id) is not int or task_id < 1 or task_id in task_ids:
                raise ValueError(f"Backup task at index {index} has an invalid ID.")
            task_ids.add(task_id)
            for name in ("title", "description", "status", "priority", "created_at", "updated_at"):
                if not isinstance(task[name], str):
                    raise ValueError(
                        f"Backup task at index {index} has an invalid {name}."
                    )
            if not task["title"].strip():
                raise ValueError(f"Backup task at index {index} has an empty title.")
            if task["status"] not in ("pending", "done"):
                raise ValueError(f"Backup task at index {index} has an invalid status.")
            if task["priority"] not in ("low", "normal", "high"):
                raise ValueError(
                    f"Backup task at index {index} has an invalid priority."
                )
            due_date = task["due_date"]
            if due_date is not None:
                if not isinstance(due_date, str):
                    raise ValueError(
                        f"Backup task at index {index} has an invalid due_date."
                    )
                try:
                    parsed_date = date.fromisoformat(due_date)
                except ValueError as error:
                    raise ValueError(
                        f"Backup task at index {index} has an invalid due_date."
                    ) from error
                if parsed_date.isoformat() != due_date:
                    raise ValueError(
                        f"Backup task at index {index} has an invalid due_date."
                    )
            for field in ("created_at", "updated_at"):
                try:
                    datetime.fromisoformat(task[field])
                except ValueError as error:
                    raise ValueError(
                        f"Backup task at index {index} has an invalid {field}."
                    ) from error
            tasks.append(task)

        for index, value in enumerate(raw_events):
            if not isinstance(value, dict):
                raise ValueError(f"Backup event at index {index} must be an object.")
            event = dict(value)
            required = {"id", "topic", "message", "created_at"}
            if not required.issubset(event):
                raise ValueError(f"Backup event at index {index} is missing fields.")
            event_id = event["id"]
            if type(event_id) is not int or event_id < 1 or event_id in event_ids:
                raise ValueError(f"Backup event at index {index} has an invalid ID.")
            event_ids.add(event_id)
            for name in ("topic", "message", "created_at"):
                if not isinstance(event[name], str):
                    raise ValueError(
                        f"Backup event at index {index} has an invalid {name}."
                    )
            if not event["topic"].strip() or not event["message"].strip():
                raise ValueError(f"Backup event at index {index} has empty text.")
            try:
                datetime.fromisoformat(event["created_at"])
            except ValueError as error:
                raise ValueError(
                    f"Backup event at index {index} has an invalid created_at."
                ) from error
            events.append(event)

        return tasks, events
