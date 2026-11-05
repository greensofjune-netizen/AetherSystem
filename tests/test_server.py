from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx

from aether_engine import server


def _request(
    method: str,
    path: str,
    *,
    client_address: tuple[str, int] = ("127.0.0.1", 12345),
    **kwargs: Any,
) -> httpx.Response:
    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=server.app, client=client_address)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send_request())


class FakeEngine:
    def __init__(self, model_path: Path, result: dict[str, Any]) -> None:
        self.model_path = model_path
        self.result = result
        self.calls: list[dict[str, str]] = []

    def execute_local_inference(
        self, *, prompt: str, reasoning_effort: str
    ) -> dict[str, Any]:
        self.calls.append(
            {"prompt": prompt, "reasoning_effort": reasoning_effort}
        )
        return self.result


def test_health_reports_model_availability(tmp_path, monkeypatch) -> None:
    model_path = tmp_path / "local.gguf"
    model_path.touch()
    monkeypatch.setattr(
        server,
        "engine",
        FakeEngine(model_path, {"status": "SUCCESS", "output": "ok"}),
    )

    response = _request("GET", "/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "model": "local.gguf",
        "model_available": True,
    }


def test_completion_uses_local_engine_and_returns_response(monkeypatch, tmp_path) -> None:
    fake_engine = FakeEngine(
        tmp_path / "local.gguf",
        {"status": "SUCCESS", "model": "local.gguf", "output": "Local answer."},
    )
    monkeypatch.setattr(server, "engine", fake_engine)

    response = _request(
        "POST",
        "/v1/chat/completions",
        json={"prompt": "  Explain this.  ", "reasoning_effort": "high"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "model": "local.gguf",
        "response": "Local answer.",
        "status": "success",
        "tokens_used": None,
    }
    assert fake_engine.calls == [
        {"prompt": "Explain this.", "reasoning_effort": "high"}
    ]


def test_completion_reports_unavailable_local_inference(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        server,
        "engine",
        FakeEngine(
            tmp_path / "missing.gguf",
            {
                "status": "OFFLINE_FALLBACK",
                "output": "Local model weights are missing.",
            },
        ),
    )

    response = _request(
        "POST",
        "/v1/chat/completions",
        json={"prompt": "Write code."},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "status": "OFFLINE_FALLBACK",
        "message": "Local model weights are missing.",
    }


def test_completion_rejects_malformed_local_model_result(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        server,
        "engine",
        FakeEngine(tmp_path / "local.gguf", {"status": "SUCCESS"}),
    )

    response = _request(
        "POST",
        "/v1/chat/completions",
        json={"prompt": "Write code."},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Local model returned an invalid completion response."
    )


def test_completion_rejects_blank_prompt(monkeypatch, tmp_path) -> None:
    fake_engine = FakeEngine(tmp_path / "local.gguf", {})
    monkeypatch.setattr(server, "engine", fake_engine)

    response = _request(
        "POST",
        "/v1/chat/completions",
        json={"prompt": "   "},
    )

    assert response.status_code == 422
    assert fake_engine.calls == []


def test_completion_rejects_unsupported_reasoning_effort(tmp_path) -> None:
    response = _request(
        "POST",
        "/v1/chat/completions",
        json={"prompt": "Write code.", "reasoning_effort": 10},
    )

    assert response.status_code == 422


def test_api_rejects_non_loopback_clients() -> None:
    response = _request(
        "GET",
        "/health",
        client_address=("192.0.2.10", 12345),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Loopback clients only."


def test_task_event_status_export_backup_and_restore_api(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "project.sqlite3"
    monkeypatch.setenv("AETHER_DATABASE_PATH", str(database_path))

    created_task = _request(
        "POST",
        "/api/v1/tasks",
        json={
            "title": "  Add REST endpoints  ",
            "description": "Coverage",
            "priority": "high",
            "due_date": "2026-12-01",
        },
    )
    assert created_task.status_code == 201
    task = created_task.json()
    assert task["title"] == "Add REST endpoints"
    assert task["status"] == "pending"

    listed_tasks = _request("GET", "/api/v1/tasks", params={"status": "pending"})
    assert [item["id"] for item in listed_tasks.json()] == [task["id"]]

    patched_task = _request(
        "PATCH",
        f"/api/v1/tasks/{task['id']}",
        json={"clear_due_date": True},
    )
    assert patched_task.status_code == 200
    assert patched_task.json()["due_date"] is None

    completed = _request("POST", f"/api/v1/tasks/{task['id']}/complete")
    assert completed.json()["status"] == "done"
    reopened = _request("POST", f"/api/v1/tasks/{task['id']}/reopen")
    assert reopened.json()["status"] == "pending"

    created_event = _request(
        "POST",
        "/api/v1/events",
        json={"topic": "release", "message": "API is ready"},
    )
    assert created_event.status_code == 201
    listed_events = _request("GET", "/api/v1/events", params={"topic": "release"})
    assert listed_events.json()[0]["message"] == "API is ready"

    status = _request("GET", "/api/v1/status")
    assert status.json()["pending_count"] == 1
    assert status.json()["completion_percent"] == 0

    completed_again = _request("POST", f"/api/v1/tasks/{task['id']}/complete")
    assert completed_again.status_code == 200
    complete_status = _request("GET", "/api/v1/status").json()
    assert complete_status["pending_count"] == 0
    assert complete_status["done_count"] == 1
    assert complete_status["total_count"] == 1
    assert complete_status["completion_percent"] == 100

    exported = _request("GET", "/api/v1/export")
    assert exported.status_code == 200
    assert exported.json()["schema_version"] == 1

    backup = _request("POST", "/api/v1/backups", json={"keep": 2})
    assert backup.status_code == 201
    assert Path(backup.json()["path"]).is_file()

    empty_export = {
        "schema_version": 1,
        "exported_at": "2026-11-04T00:00:00+00:00",
        "tasks": [],
        "events": [],
    }
    restored = _request(
        "POST",
        "/api/v1/restore",
        json={"backup": empty_export, "replace": True},
    )
    assert restored.status_code == 200
    assert restored.json()["tasks_restored"] == 0
    assert restored.json()["events_restored"] == 0
    assert restored.json()["safety_backup"] is not None
    assert _request("GET", "/api/v1/tasks").json() == []
    assert _request("GET", "/api/v1/events").json() == []


def test_task_api_reports_invalid_and_missing_tasks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AETHER_DATABASE_PATH", str(tmp_path / "tasks.sqlite3"))

    invalid = _request("POST", "/api/v1/tasks", json={"title": "  "})
    missing = _request("POST", "/api/v1/tasks/99/complete")

    assert invalid.status_code == 422
    assert missing.status_code == 404


def test_doctor_api_returns_structured_diagnostics(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AETHER_DATABASE_PATH", str(tmp_path / "missing.sqlite3"))

    response = _request("GET", "/api/v1/doctor")

    assert response.status_code == 200
    assert response.json()["healthy"] is False
    assert response.json()["diagnostics"][0]["name"] == "Database"


def test_backup_schedule_api_exposes_status_and_management(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "schedule.sqlite3"
    monkeypatch.setenv("AETHER_DATABASE_PATH", str(database_path))
    schedule_path = tmp_path / "schedule.plist"
    calls: list[tuple[str, object]] = []

    def fake_status(path: Path) -> tuple[Path, bool, bool, int | None]:
        calls.append(("status", path))
        return schedule_path, True, True, 0

    def fake_install(path: Path, *, keep: int) -> Path:
        calls.append(("install", (path, keep)))
        return schedule_path

    def fake_uninstall(path: Path) -> tuple[Path, bool]:
        calls.append(("uninstall", path))
        return schedule_path, True

    monkeypatch.setattr(server, "backup_schedule_status", fake_status)
    monkeypatch.setattr(server, "install_backup_schedule", fake_install)
    monkeypatch.setattr(server, "uninstall_backup_schedule", fake_uninstall)

    status = _request("GET", "/api/v1/backups/schedule")
    installed = _request(
        "POST",
        "/api/v1/backups/schedule",
        json={"keep": 7},
    )
    removed = _request("DELETE", "/api/v1/backups/schedule")

    assert status.json()["loaded"] is True
    assert installed.json() == {"path": str(schedule_path), "keep": 7}
    assert removed.json() == {"path": str(schedule_path), "removed": True}
    assert [action for action, _ in calls] == ["status", "install", "uninstall"]
