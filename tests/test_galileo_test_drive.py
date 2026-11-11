import asyncio
import base64
import json
import sqlite3
from contextlib import closing
from threading import Event
from unittest.mock import Mock

import httpx
import pytest

from aether_engine import galileo
from aether_engine.galileo_desktop import DesktopActions
from aether_engine.model_providers import ChatResult, ModelInfo, OllamaProvider
from automator import bridge


def test_stop_discards_exchange_and_preserves_other_conversations(tmp_path):
    started = Event()
    release = Event()
    provider = Mock()

    def chat(request):
        started.set()
        assert release.wait(5)
        return ChatResult(request.model, "Late response")

    provider.chat.side_effect = chat
    app = galileo.create_app(tmp_path, token="test", model_provider=provider)

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
            base_url="http://127.0.0.1",
        ) as client:
            await client.get("/?token=test")
            first = (await client.post("/api/conversations", json={})).json()["id"]
            second = (await client.post("/api/conversations", json={})).json()["id"]
            url = f"/api/conversations/{first}"
            sending = asyncio.create_task(
                client.post(url + "/messages", json={"message": "Synthetic prompt"})
            )
            try:
                assert await asyncio.to_thread(started.wait, 3)
                duplicate = await client.post(
                    url + "/messages", json={"message": "Duplicate"}
                )
                assert duplicate.status_code == 409
                assert (await client.request("DELETE", url, json={})).status_code == 409
                stopped = await client.post(url + "/stop", json={})
                assert stopped.json() == {"cancelled": True}
                assert (
                    await client.post(f"/api/conversations/{second}/stop", json={})
                ).json() == {"cancelled": False}
            finally:
                release.set()
            result = await sending
            assert result.status_code == 409
            assert (await client.get(url)).json()["messages"] == []
            retry = await client.post(
                url + "/messages", json={"message": "Synthetic prompt"}
            )
            assert retry.status_code == 200
            assert len(retry.json()["conversation"]["messages"]) == 2
            assert (await client.get(f"/api/conversations/{second}")).json()[
                "messages"
            ] == []

    try:
        asyncio.run(check())
    finally:
        release.set()
        app.state.engine_runtime.stop()


def test_text_model_rejects_new_and_saved_images(tmp_path):
    provider = Mock()
    provider.list_models.return_value = (
        ModelInfo("text", ("completion",)),
        ModelInfo("vision", ("vision",)),
    )
    provider.chat.return_value = ChatResult("vision", "A synthetic image")
    app = galileo.create_app(tmp_path, token="test", model_provider=provider)
    image = {
        "name": "test.png",
        "media_type": "image/png",
        "data": base64.b64encode(b"\x89PNG\r\n\x1a\nsample").decode(),
    }

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
            base_url="http://127.0.0.1",
        ) as client:
            await client.get("/?token=test")
            identifier = (await client.post("/api/conversations", json={})).json()["id"]
            url = f"/api/conversations/{identifier}/messages"
            rejected = await client.post(
                url, json={"message": "Describe", "model": "text", "images": [image]}
            )
            assert rejected.status_code == 422
            provider.chat.assert_not_called()
            accepted = await client.post(
                url, json={"message": "Describe", "model": "vision", "images": [image]}
            )
            assert accepted.status_code == 200
            rejected = await client.post(
                url, json={"message": "Follow up", "model": "text"}
            )
            assert rejected.status_code == 422
            assert provider.chat.call_count == 1

    try:
        asyncio.run(check())
    finally:
        app.state.engine_runtime.stop()


def test_scoped_ollama_stop_does_not_close_other_requests():
    provider = OllamaProvider()
    first = Event()
    second = Event()
    first_connection = Mock()
    second_connection = Mock()
    first_socket = Mock()
    second_socket = Mock()
    provider._connections = {
        first_connection: first_socket,
        second_connection: second_socket,
    }
    provider._request_events = {first_connection: first, second_connection: second}
    provider.cancel_request(first)
    assert first.is_set()
    assert not second.is_set()
    first_socket.shutdown.assert_called_once()
    first_connection.close.assert_called_once()
    second_socket.shutdown.assert_not_called()
    second_connection.close.assert_not_called()


def test_ollama_disables_thinking_only_when_explicitly_requested(monkeypatch):
    from aether_engine.model_providers import ChatRequest, ProviderMessage

    provider = OllamaProvider()
    request = Mock(return_value={"message": {"content": "Visible response"}})
    monkeypatch.setattr(provider, "request", request)
    provider.chat(
        ChatRequest(
            "vision", (ProviderMessage("user", "Describe"),), reasoning_effort="none"
        )
    )
    assert request.call_args.args[1]["think"] is False
    provider.chat(ChatRequest("vision", (ProviderMessage("user", "Describe"),)))
    assert "think" not in request.call_args.args[1]


@pytest.mark.parametrize("outcome", ["succeeded", "failed", "cancelled"])
def test_automator_reports_metadata_only(tmp_path, monkeypatch, outcome):
    monkeypatch.delenv("AETHER_DATABASE_PATH", raising=False)
    run = Mock()
    if outcome == "failed":
        run.side_effect = RuntimeError("private error text")
    elif outcome == "cancelled":
        run.side_effect = InterruptedError("private cancellation text")
    monkeypatch.setattr(bridge, "run", run)
    if outcome == "succeeded":
        bridge.run_reported("test", project=tmp_path)
    else:
        with pytest.raises((RuntimeError, InterruptedError)):
            bridge.run_reported("test", project=tmp_path)
    with closing(sqlite3.connect(tmp_path / ".aether-engine.sqlite3")) as connection:
        rows = connection.execute("SELECT message FROM events ORDER BY id").fetchall()
    payloads = [json.loads(row[0]) for row in rows]
    assert [payload["outcome"] for payload in payloads] == ["started", outcome]
    assert all(payload["node"] == "MATRIX" for payload in payloads)
    assert all(
        set(payload)
        == {"node", "component", "action", "outcome", "duration_ms", "model"}
        for payload in payloads
    )
    assert "private" not in str(rows)


def test_desktop_actions_reject_arbitrary_commands_and_forward_paths(
    tmp_path, monkeypatch
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").touch()
    data = tmp_path / "data"
    actions = DesktopActions(data, project)
    run = Mock()
    monkeypatch.setattr(bridge, "run_reported", run)
    assert not actions.run_matrix_action("rm -rf")["ok"]
    run.assert_not_called()
    assert actions.run_matrix_action("backup")["ok"]
    run.assert_called_once_with("backup", project=project, galileo_directory=data)
    actions.voice.close()


def test_frozen_test_action_uses_project_python(tmp_path, monkeypatch):
    interpreter = tmp_path / ".venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    monkeypatch.setattr(bridge.sys, "frozen", True, raising=False)
    monkeypatch.setattr(bridge, "dialog", Mock(return_value="Continue"))
    run = Mock(return_value=Mock(returncode=0, stdout="passed", stderr=""))
    monkeypatch.setattr(bridge.subprocess, "run", run)
    bridge.run("test", project=tmp_path)
    assert run.call_args.args[0] == [str(interpreter), "-m", "pytest", "-q"]
