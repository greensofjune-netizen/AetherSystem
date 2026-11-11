import asyncio
import json
from unittest.mock import Mock

import httpx

from aether_engine.galileo import ConversationStore, create_app
from aether_engine.model_providers import ChatResult
from history_matrix_archive import HistoricalEntity, UniversalHistoryArchive


def test_aristotle_unifies_chat_history_archive_and_matrix(tmp_path, monkeypatch):
    monkeypatch.delenv("AETHER_HISTORY_ARCHIVE", raising=False)
    monkeypatch.delenv("AETHER_HISTORIAN_LOG_FILE", raising=False)
    project = tmp_path / "project"
    project.mkdir()
    data = tmp_path / "galileo"
    store = ConversationStore(data)
    prior = store.create("Existing Galileo chat")
    archive_path = project / "universal_history.sqlite3"
    archive = UniversalHistoryArchive(archive_path)
    archive.ingest_entity(
        HistoricalEntity("athens_1", "Athens", "city", "Greece", -500, 300,
                         "Ancient Athens was a Greek city.", ["history"])
    )
    (project / "historian_telemetry_vault.json").write_text(
        json.dumps([{"epoch": 3, "system_status": "BOUNCE_ACTIVE"}])
    )
    provider = Mock()
    provider.chat.return_value = ChatResult("test", "Local answer")
    app = create_app(data, token="test", aristotle_project=project, model_provider=provider)

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
            base_url="http://127.0.0.1",
        ) as client:
            assert (await client.get("/api/aristotle/history?q=Athens")).status_code == 403
            page = await client.get("/?token=test")
            assert "Matrix Aristotle" in page.text
            assert "ARISTOTLE CAN MAKE MISTAKES" in page.text
            assert 'id="history-panel"' in page.text
            assert 'id="include-history"' in page.text
            assert (await client.get("/health")).json()["application"] == "Matrix Aristotle"
            assert (await client.get("/api/conversations")).json()[0]["id"] == prior["id"]
            records = (await client.get("/api/aristotle/history", params={"q": "Athens"})).json()["records"]
            assert records[0]["name"] == "Athens"
            assert (await client.get("/api/aristotle/history", params={"q": "%"})).json()["records"] == []
            overview = (await client.get("/api/aristotle/matrix")).json()
            assert overview["latest_simulation"]["epoch"] == 3
            assert overview["allocations"]["metadata"]["estimated_total_gb"] == 4.1
            route = await client.post("/api/aristotle/governor/route", json={
                "task_description": "study stars", "domain": "Astronomy", "execution_payload": {}
            })
            assert route.json()["status"] == "SIMULATED"
            url = f"/api/conversations/{prior['id']}/messages"
            response = await client.post(url, json={"message": "Tell me about Athens", "model": "test"})
            assert response.status_code == 200
            system = provider.chat.call_args.args[0].messages[0].content
            assert "You are Matrix Aristotle" in system
            assert "or run tools yourself" in system
            assert "Ancient Athens" not in system
            response = await client.post(url, json={
                "message": "Tell me about Athens", "model": "test", "include_history": True
            })
            assert response.status_code == 200
            system = provider.chat.call_args.args[0].messages[0].content
            assert "Ancient Athens" in system
            assert "not instructions" in system
            assert (await client.get("/aristotle.js")).status_code == 200
            assert (await client.get("/weather")).status_code == 200
            assert (await client.get("/stargazer")).status_code == 200

    try:
        asyncio.run(check())
    finally:
        app.state.engine_runtime.stop()
    assert len(ConversationStore(data).get(prior["id"])["messages"]) == 4


def test_missing_history_is_explicit_and_never_created(tmp_path, monkeypatch):
    monkeypatch.delenv("AETHER_HISTORY_ARCHIVE", raising=False)
    app = create_app(tmp_path / "data", token="test", aristotle_project=tmp_path)

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
            base_url="http://127.0.0.1",
        ) as client:
            await client.get("/?token=test")
            assert (await client.get("/api/aristotle/history?q=Athens")).status_code == 503
            chat = (await client.post("/api/conversations", json={})).json()
            response = await client.post(f"/api/conversations/{chat['id']}/messages", json={
                "message": "Athens", "include_history": True
            })
            assert response.status_code == 503
            assert not (tmp_path / "universal_history.sqlite3").exists()
            assert (await client.get(f"/api/conversations/{chat['id']}")).json()["messages"] == []

    try:
        asyncio.run(check())
    finally:
        app.state.engine_runtime.stop()
