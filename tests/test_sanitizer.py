from pathlib import Path

import pytest

from aether_engine.database import AetherStore
from aether_engine.sanitizer import sanitize_text


def test_sanitizer_trims_prompts_and_trailing_markdown_only() -> None:
    assert (
        sanitize_text(
            "  eh@Mac ~ % echo first && second; third | fourth**` \n",
            field_name="Event message",
        )
        == "echo first && second; third | fourth"
    )
    assert (
        sanitize_text("> Task title__", field_name="Task title")
        == "Task title"
    )


def test_sanitizer_rejects_empty_and_non_text_values() -> None:
    with pytest.raises(ValueError, match="Task title cannot be empty"):
        sanitize_text(" \t\n", field_name="Task title")
    with pytest.raises(ValueError, match="Event message cannot be empty"):
        sanitize_text("> ```", field_name="Event message")
    with pytest.raises(ValueError, match="Task title must be text"):
        sanitize_text(None, field_name="Task title")  # type: ignore[arg-type]


def test_database_sanitizes_added_and_edited_text(tmp_path: Path) -> None:
    store = AetherStore(tmp_path / "project.sqlite3")

    task = store.add_task(
        "  eh@Mac ~ % Build release**`  ",
        "  > Review checklist```  ",
    )
    event = store.add_event("  release  ", "  > Build shipped```  ")

    assert task.title == "Build release"
    assert task.description == "Review checklist"
    assert event.topic == "release"
    assert event.message == "Build shipped"

    updated = store.update_task(
        task.id,
        title="  > Revised title__  ",
        description="  revised details  ",
    )
    assert updated is not None
    assert updated.title == "Revised title"
    assert updated.description == "revised details"

    with pytest.raises(ValueError, match="Task title cannot be empty"):
        store.add_task("  ")
    with pytest.raises(ValueError, match="Event message cannot be empty"):
        store.add_event("release", " \t ")
    with pytest.raises(ValueError, match="Task description must be text"):
        store.add_task("Valid title", None)  # type: ignore[arg-type]


def test_restore_sanitizes_text_before_database_write(tmp_path: Path) -> None:
    source = AetherStore(tmp_path / "source.sqlite3")
    source.add_task("Task title")
    source.add_event("release", "Event message")
    payload = {
        "schema_version": 1,
        "exported_at": "2026-11-03T00:00:00+00:00",
        **source.export_data(),
    }
    payload["tasks"][0]["title"] = "  > Imported task**`  "
    payload["tasks"][0]["description"] = "  imported details  "
    payload["events"][0]["topic"] = "  release  "
    payload["events"][0]["message"] = "eh@Mac ~ % Imported event```"

    restored = AetherStore(tmp_path / "restored.sqlite3")
    assert restored.restore_data(payload) == (1, 1)

    task = restored.list_tasks()[0]
    event = restored.list_events()[0]
    assert task.title == "Imported task"
    assert task.description == "imported details"
    assert event.topic == "release"
    assert event.message == "Imported event"
