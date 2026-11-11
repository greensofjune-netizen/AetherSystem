from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import httpx
from starlette.requests import Request

from aether_engine import server


def test_propulsion_reference_api(tmp_path, monkeypatch):
    from aether_engine.propulsion_matrix import (
        KineticPropulsionArchive,
        seed_civilian_references,
    )

    archive = KineticPropulsionArchive(tmp_path / "propulsion.sqlite3")
    seed_civilian_references(archive)
    monkeypatch.setattr(server, "KineticPropulsionArchive", lambda: archive)
    response = _request("GET", "/api/v1/propulsion/references", params={"q": "JT3D"})
    assert response.status_code == 200
    assert response.json()["references"][0]["source_url"].startswith("https://")
    assert len(response.json()["lineage"]) == 1
    assert _request("GET", "/api/v1/propulsion/references", params={"q": "x" * 201}).status_code == 422


def test_unified_dispatch_persists_updates_and_broadcasts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AETHER_DATABASE_PATH", str(tmp_path / "dispatch.sqlite3"))

    calls = []

    async def update_state(event_name, payload):
        calls.append(("state", event_name, payload))

    class FakeSupervisor:
        async def broadcast(self, *, event_type, data):
            calls.append(("broadcast", event_type, data))
            return 2

    monkeypatch.setattr(server.live_sync_supervisor, "safe_update_dashboard_state", update_state)
    monkeypatch.setattr(server.live_sync_supervisor, "supervisor", FakeSupervisor())
    envelope = {
        "protocol_version": "1.0.0",
        "source_lang": "rust",
        "node": "ATLAS",
        "event": "BUILD_FINISHED",
        "timestamp": 1_800_000_000,
        "payload": {
            "artifact": "aether-engine",
            "last_source_lang": "spoofed",
            "last_node": "spoofed",
        },
    }

    response = _request(
        "POST",
        "/api/v1/unified/dispatch",
        client_address=("::1", 12345),
        json=envelope,
    )

    assert response.status_code == 200
    result = response.json()
    assert result == {
        "status": "ACCEPTED",
        "persisted": True,
        "event_id": result["event_id"],
        "live_subscribers_notified": 2,
    }
    assert result["event_id"] > 0
    persisted = _request(
        "GET", "/api/v1/events", params={"topic": "unified-dispatch"}
    ).json()
    assert len(persisted) == 1
    assert json.loads(persisted[0]["message"]) == envelope
    assert calls[0] == (
        "state",
        "BUILD_FINISHED",
        {
            "unified_dispatch": calls[1][2],
            "last_source_lang": "rust",
            "last_node": "ATLAS",
        },
    )
    assert calls[1][0:2] == ("broadcast", "BUILD_FINISHED")
    assert calls[1][2]["event_id"] == result["event_id"]
    assert calls[1][2]["envelope"] == envelope


def test_unified_dispatch_rejects_non_loopback_and_invalid_envelopes(
    monkeypatch,
) -> None:
    monkeypatch.delenv("AETHER_API_TOKEN", raising=False)
    envelope = {
        "protocol_version": "1.0.0",
        "source_lang": "python",
        "node": "COPERNICUS",
        "event": "PING",
        "timestamp": 1_800_000_000,
        "payload": {},
    }
    assert (
        _request(
            "POST",
            "/api/v1/unified/dispatch",
            client_address=("192.0.2.10", 12345),
            json=envelope,
        ).status_code
        == 401
    )

    for update in (
        {"protocol_version": "2.0.0"},
        {"timestamp": "not-a-number"},
        {"timestamp": -1},
        {"source_lang": "typescript"},
        {"node": "UNKNOWN"},
        {"event": "not-an-event"},
        {"payload": []},
        {"payload": None},
        {"unexpected": True},
    ):
        response = _request(
            "POST",
            "/api/v1/unified/dispatch",
            json={**envelope, **update},
        )
        assert response.status_code == 422

    oversized_payload = {**envelope, "payload": {"large": "x" * 32_768}}
    assert (
        _request(
            "POST",
            "/api/v1/unified/dispatch",
            json=oversized_payload,
        ).status_code
        == 422
    )


def test_remote_access_requires_shared_token_and_allows_loopback(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AETHER_API_TOKEN", "test-shared-secret")
    monkeypatch.setenv("AETHER_DATABASE_PATH", str(tmp_path / "dispatch.sqlite3"))
    remote = ("192.0.2.10", 12345)

    assert _request("GET", "/health", client_address=remote).status_code == 401
    assert (
        _request(
            "GET",
            "/health",
            client_address=remote,
            headers={"X-Aether-Token": "incorrect"},
        ).status_code
        == 401
    )
    assert _request("GET", "/health").status_code == 200
    assert _request(
        "GET",
        "/health",
        client_address=remote,
        headers={"X-Aether-Token": "test-shared-secret"},
    ).status_code == 200
    preflight = _request(
        "OPTIONS",
        "/api/v1/unified/dispatch",
        client_address=remote,
        headers={
            "Origin": "https://client.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-aether-token",
        },
    )
    assert preflight.status_code == 400

    envelope = {
        "protocol_version": "1.0.0",
        "source_lang": "python",
        "node": "ATLAS",
        "event": "REMOTE_AUTHORIZED",
        "timestamp": 1_800_000_000,
        "payload": {},
    }
    response = _request(
        "POST",
        "/api/v1/unified/dispatch",
        client_address=remote,
        headers={"X-Aether-Token": "test-shared-secret"},
        json=envelope,
    )
    assert response.status_code == 200


def test_unified_stream_rejects_invalid_cursor() -> None:
    response = _request(
        "GET",
        "/api/v1/unified/stream",
        headers={"Last-Event-ID": "not-an-integer"},
    )
    assert response.status_code == 400


def test_unified_protocol_schema_matches_api_model() -> None:
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "aether_protocol.schema.json").read_text(
            encoding="utf-8"
        )
    )
    model_schema = server.UnifiedEnvelope.model_json_schema()
    assert schema["required"] == model_schema["required"]
    assert schema["properties"]["protocol_version"]["const"] == "1.0.0"
    assert schema["properties"]["source_lang"]["enum"] == model_schema["properties"][
        "source_lang"
    ]["enum"]
    assert schema["properties"]["node"]["enum"] == model_schema["properties"]["node"][
        "enum"
    ]
    assert schema["properties"]["event"]["pattern"] == model_schema["properties"][
        "event"
    ]["pattern"]
    assert schema["properties"]["timestamp"]["minimum"] == model_schema[
        "properties"
    ]["timestamp"]["minimum"]
    assert schema["additionalProperties"] is False


def test_unified_dispatch_enforces_per_client_rate_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("AETHER_DATABASE_PATH", str(tmp_path / "dispatch.sqlite3"))
    monkeypatch.setattr(server, "UNIFIED_DISPATCH_RATE_LIMIT", 1)
    envelope = {
        "protocol_version": "1.0.0",
        "source_lang": "python",
        "node": "ATLAS",
        "event": "RATE_LIMIT_TEST",
        "timestamp": 1_800_000_000,
        "payload": {},
    }

    first = _request(
        "POST",
        "/api/v1/unified/dispatch",
        client_address=("127.0.0.2", 12345),
        json=envelope,
    )
    second = _request(
        "POST",
        "/api/v1/unified/dispatch",
        client_address=("127.0.0.2", 12345),
        json=envelope,
    )
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["retry-after"]


def test_unified_stream_snapshots_replays_and_cleans_up(monkeypatch, tmp_path):
    monkeypatch.setenv("AETHER_DATABASE_PATH", str(tmp_path / "dispatch.sqlite3"))
    monkeypatch.setattr(
        server.live_sync_supervisor,
        "supervisor",
        server.live_sync_supervisor.LiveSyncSupervisor(),
    )
    envelope = server.UnifiedEnvelope(
        protocol_version="1.0.0",
        source_lang="js",
        node="COPERNICUS",
        event="UI_SYNC",
        timestamp=1_800_000_000,
        payload={"status": "READY"},
    )

    async def check():
        supervisor = server.live_sync_supervisor.supervisor
        live_response = await server.unified_dispatch_stream(_stream_request())
        live_body = live_response.body_iterator
        assert (await anext(live_body)).startswith("retry:")
        assert "event: snapshot" in await anext(live_body)
        accepted = await server.unified_cross_language_dispatch(
            envelope, _stream_request()
        )
        live_event = await anext(live_body)
        assert f"id: {accepted.event_id}" in live_event
        assert "event: dispatch" in live_event
        assert '"status":"READY"' in live_event
        await live_body.aclose()
        assert not supervisor._connected_interfaces

        replay_response = await server.unified_dispatch_stream(
            _stream_request(last_event_id="0"), last_event_id="0"
        )
        replay_body = replay_response.body_iterator
        assert (await anext(replay_body)).startswith("retry:")
        replay = await anext(replay_body)
        assert f"id: {accepted.event_id}" in replay
        assert "event: dispatch" in replay
        await replay_body.aclose()
        assert not supervisor._connected_interfaces

        future_response = await server.unified_dispatch_stream(
            _stream_request(last_event_id=str(accepted.event_id + 1)),
            last_event_id=str(accepted.event_id + 1),
        )
        future_body = future_response.body_iterator
        assert (await anext(future_body)).startswith("retry:")
        reset = await anext(future_body)
        assert "event: reset" in reset
        assert f"id: {accepted.event_id}" in reset
        await future_body.aclose()

        state = await server.unified_dispatch_state()
        assert state["last_dispatch"]["event_id"] == accepted.event_id
        assert state["last_dispatch"]["envelope"] == envelope.model_dump()

    asyncio.run(check())


def test_unified_stream_resets_cursor_older_than_replay_window(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AETHER_DATABASE_PATH", str(tmp_path / "dispatch.sqlite3"))
    historian = server.CoPilotHistorian(server.get_store())
    envelope = {
        "protocol_version": "1.0.0",
        "source_lang": "python",
        "node": "HISTORIAN",
        "event": "REPLAY_TEST",
        "timestamp": 1_800_000_000,
        "payload": {},
    }
    for _ in range(server.UNIFIED_EVENT_REPLAY_LIMIT + 1):
        historian.record(server.UNIFIED_DISPATCH_TOPIC, json.dumps(envelope))

    async def check():
        response = await server.unified_dispatch_stream(
            _stream_request(last_event_id="0"), last_event_id="0"
        )
        body = response.body_iterator
        assert (await anext(body)).startswith("retry:")
        reset = await anext(body)
        assert "event: reset" in reset
        await body.aclose()

    asyncio.run(check())


def test_unified_stream_signals_replay_after_queue_overflow(monkeypatch, tmp_path):
    monkeypatch.setenv("AETHER_DATABASE_PATH", str(tmp_path / "dispatch.sqlite3"))
    monkeypatch.setattr(
        server.live_sync_supervisor, "MAX_PENDING_EVENTS_PER_INTERFACE", 1
    )
    supervisor = server.live_sync_supervisor.LiveSyncSupervisor()
    monkeypatch.setattr(server.live_sync_supervisor, "supervisor", supervisor)

    async def check():
        response = await server.unified_dispatch_stream(_stream_request())
        await supervisor.broadcast("FIRST", {})
        await supervisor.broadcast("SECOND", {})
        body = response.body_iterator
        assert (await anext(body)).startswith("retry:")
        assert "event: snapshot" in await anext(body)
        assert "event: replay-required" in await anext(body)
        await body.aclose()
        assert not supervisor._connected_interfaces

    asyncio.run(check())


def _stream_request(last_event_id: str | None = None) -> Request:
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    headers = (
        [(b"last-event-id", last_event_id.encode())]
        if last_event_id is not None
        else []
    )
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/unified/stream",
            "raw_path": b"/api/v1/unified/stream",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8000),
        },
        receive,
    )


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
        self,
        *,
        prompt: str,
        reasoning_effort: str,
        max_output_tokens: int | None = None,
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
    assert response.headers["x-request-id"]

    runtime = _request("GET", "/api/v1/engine/status")
    assert runtime.status_code == 200
    assert runtime.json()["state"] == "ready"


def test_shared_client_requires_token_for_remote_access(monkeypatch) -> None:
    monkeypatch.setenv("AETHER_API_TOKEN", "test-shared-secret")
    response = _request("GET", "/aether_client.js")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert response.content == server.SOURCE_CLIENT_PATH.read_bytes()
    assert _request(
        "GET", "/aether_client.js", client_address=("::1", 12345)
    ).status_code == 200
    remote = ("192.0.2.1", 12345)
    assert _request(
        "GET", "/aether_client.js", client_address=remote
    ).status_code == 401
    authorized = _request(
        "GET",
        "/aether_client.js",
        client_address=remote,
        headers={"X-Aether-Token": "test-shared-secret"},
    )
    assert authorized.status_code == 200
    assert authorized.content == response.content


def test_shared_client_installed_fallback_and_missing_file(tmp_path, monkeypatch):
    source = tmp_path / "missing.js"
    installed = tmp_path / "installed.js"
    installed.write_text("window.AetherClient = {};", encoding="utf-8")
    monkeypatch.setattr(server, "SOURCE_CLIENT_PATH", source)
    monkeypatch.setattr(server, "INSTALLED_CLIENT_PATH", installed)

    response = _request("GET", "/aether_client.js")
    assert response.status_code == 200
    assert response.text == "window.AetherClient = {};"

    installed.unlink()
    response = _request("GET", "/aether_client.js")
    assert response.status_code == 404
    assert response.json()["detail"] == "Shared JS file not found."


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
    assert response.headers["x-request-id"]
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


def test_image_completion_uses_typed_ollama_provider(monkeypatch):
    from aether_engine.model_providers import ChatResult

    calls = []

    def chat(request):
        calls.append(request)
        return ChatResult("qwen-local", "Image response.")

    provider = server.engine_runtime.providers["ollama"]
    monkeypatch.setattr(provider, "chat", chat)
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nsample").decode()

    response = _request(
        "POST",
        "/v1/chat/completions",
        json={
            "prompt": "Describe this.",
            "images": [
                {"name": "frame.png", "media_type": "image/png", "data": image}
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["response"] == "Image response."
    assert calls[0].messages[1].images == (image,)


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


def test_api_requires_token_from_non_loopback_clients(monkeypatch) -> None:
    monkeypatch.delenv("AETHER_API_TOKEN", raising=False)
    response = _request(
        "GET",
        "/health",
        client_address=("192.0.2.10", 12345),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Unauthorized: Valid X-Aether-Token header required for remote access."
    )


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


def test_validation_error_contract_for_schema_and_application_errors(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("AETHER_DATABASE_PATH", str(tmp_path / "tasks.sqlite3"))
    structured = _request("POST", "/api/v1/tasks", json={})
    assert structured.status_code == 422
    issue = structured.json()["detail"][0]
    assert issue["loc"] == ["body", "title"]
    assert isinstance(issue["msg"], str)
    assert isinstance(issue["type"], str)
    schema = server.app.openapi()["components"]["schemas"]["ValidationError"]
    assert schema["properties"]["loc"]["items"]["anyOf"] == [
        {"type": "string"}, {"type": "integer"}
    ]
    application_error = _request("POST", "/api/v1/tasks", json={"title": "  "})
    assert application_error.status_code == 422
    assert isinstance(application_error.json()["detail"], str)


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
