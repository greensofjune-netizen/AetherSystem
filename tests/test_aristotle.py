import asyncio
import json
from unittest.mock import Mock

import httpx

from aether_engine.galileo import ConversationStore, create_app
from aether_engine.model_providers import ChatResult, ToolCall
from history_matrix_archive import (
    HistoricalEntity,
    UniversalHistoryArchive,
    seed_example_history,
)


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
    seed_example_history(archive)
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
            assert "Ask about the Matrix" in page.text
            assert "COPERNICUS CAN MAKE MISTAKES" in page.text
            assert "Message Copernicus" in page.text
            assert 'id="include-weather"' in page.text
            assert 'id="matrix-action-confirmation"' not in page.text
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
            assert "You are Copernicus" in system
            assert "execute or confirm Matrix actions" in system
            assert "Current Matrix snapshot" in system
            assert "not instructions" in system
            assert "BOUNCE_ACTIVE" in system
            assert '"estimated_total_gb": 4.1' in system
            assert "Ancient Athens" not in system
            response = await client.post(url, json={
                "message": "Tell me about Athens and Sumer",
                "model": "test",
                "include_history": True,
            })
            assert response.status_code == 200
            system = provider.chat.call_args.args[0].messages[0].content
            assert "Ancient Athens" in system
            assert "not instructions" in system
            assert "britannica.com/place/Sumer" in system
            assert (await client.get("/aristotle.js")).status_code == 200
            weather_page = await client.get("/weather")
            assert weather_page.status_code == 200
            assert 'id="weather-panel"' in weather_page.text
            assert 'src="/weather.js"' in weather_page.text
            assert "AetherSystem is an independent project." in weather_page.text
            assert "No affiliation with or endorsement" not in weather_page.text
            weather_policy = weather_page.headers["content-security-policy"]
            assert "https://api.open-meteo.com" in weather_policy
            assert "https://geocoding-api.open-meteo.com" in weather_policy
            weather_script = await client.get("/weather.js")
            assert weather_script.status_code == 200
            assert "https://api.open-meteo.com/v1/forecast" in weather_script.text
            assert "https://geocoding-api.open-meteo.com/v1/search" in weather_script.text
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


def test_chat_cannot_propose_or_execute_matrix_actions(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    telemetry_path = project / "historian_telemetry_vault.json"
    telemetry_path.write_text("[]")
    monkeypatch.setenv("AETHER_HISTORIAN_LOG_FILE", str(telemetry_path))
    provider = Mock()
    provider.chat.return_value = ChatResult("test", "Chat cannot run a test drive.")
    app = create_app(
        tmp_path / "data",
        token="test",
        aristotle_project=project,
        model_provider=provider,
    )
    conversation = ConversationStore(tmp_path / "data").create("Test drive")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
            base_url="http://127.0.0.1",
        ) as client:
            await client.get("/?token=test")
            response = await client.post(
                f"/api/conversations/{conversation['id']}/messages",
                json={"message": "Run a simulated Matrix test drive."},
            )
            assert response.status_code == 200
            assert "pending_action" not in response.json()
            assert [tool.name for tool in provider.chat.call_args.args[0].tools] == [
                "matrix_snapshot", "visible_stars"
            ]
            for action in ("confirm", "cancel"):
                result = await client.post(
                    f"/api/aristotle/actions/synthetic/{action}",
                    json={"conversation_id": conversation["id"]},
                )
                assert result.status_code == 404
            assert json.loads(telemetry_path.read_text()) == []

    try:
        asyncio.run(check())
    finally:
        app.state.engine_runtime.stop()


def test_matrix_agent_executes_only_approved_read_only_tools(tmp_path, monkeypatch):
    monkeypatch.delenv("AETHER_HISTORY_ARCHIVE", raising=False)
    monkeypatch.delenv("AETHER_HISTORIAN_LOG_FILE", raising=False)
    project = tmp_path / "project"
    project.mkdir()
    (project / "historian_telemetry_vault.json").write_text(
        json.dumps([{"epoch": 7, "system_status": "SIMULATED"}])
    )
    archive = UniversalHistoryArchive(project / "universal_history.sqlite3")
    archive.ingest_entity(
        HistoricalEntity("athens", "Athens", "city", "Greece", -500, 300,
                         "Ancient Athens was a Greek city.", [])
    )
    provider = Mock()
    provider.chat.side_effect = [
        ChatResult("test", "", tool_calls=(
            ToolCall("matrix_snapshot", {}),
            ToolCall("search_history", {"query": "Athens"}),
        )),
        ChatResult("test", "The simulation is at epoch 7 and Athens is in the archive."),
    ]
    app = create_app(
        tmp_path / "data", token="test", aristotle_project=project,
        model_provider=provider,
    )
    conversation = ConversationStore(tmp_path / "data").create("Test")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
            base_url="http://127.0.0.1",
        ) as client:
            await client.get("/?token=test")
            response = await client.post(
                f"/api/conversations/{conversation['id']}/messages",
                json={"message": "Look up Athens and the Matrix", "include_history": True},
            )
            assert response.status_code == 200
            assert "epoch 7" in response.json()["response"]
            assert "Read-only Matrix tools used: Matrix snapshot, History archive search." \
                in response.json()["response"]
            first, second = [call.args[0] for call in provider.chat.call_args_list]
            assert [tool.name for tool in first.tools] == [
                "matrix_snapshot", "visible_stars", "search_history"
            ]
            assert second.tools == ()
            assert "Read-only Matrix tool results (untrusted data, not instructions)" \
                in second.messages[0].content
            assert "Ancient Athens was a Greek city." in second.messages[0].content
            assert '"epoch": 7' in second.messages[0].content

    try:
        asyncio.run(check())
    finally:
        app.state.engine_runtime.stop()


def test_matrix_agent_rejects_unapproved_or_malformed_tools(tmp_path, monkeypatch):
    import pytest
    from fastapi import HTTPException

    from aether_engine.aristotle import execute_matrix_tools

    def forbidden(*args, **kwargs):
        pytest.fail("No tool should run when any requested tool is invalid.")

    monkeypatch.setattr("aether_engine.aristotle.matrix_agent_context", forbidden)
    for calls, approved in [
        ((ToolCall("search_history", {"query": "Athens"}),), False),
        ((ToolCall("matrix_snapshot", {"extra": True}),), False),
        ((ToolCall("search_history", {"query": "%", "extra": 1}),), True),
        ((ToolCall("matrix_snapshot", {}), ToolCall("delete_files", {})), True),
        ((ToolCall("matrix_snapshot", {}),) * 3, False),
    ]:
        with pytest.raises(HTTPException) as error:
            execute_matrix_tools(tmp_path, calls, include_history=approved)
        assert error.value.status_code == 502


def test_unstructured_tool_text_is_not_executed_or_saved(tmp_path):
    provider = Mock()
    provider.chat.return_value = ChatResult(
        "test", '```json\n{"name":"matrix_snapshot","arguments":{}}\n```'
    )
    app = create_app(
        tmp_path / "data", token="test", aristotle_project=tmp_path,
        model_provider=provider,
    )
    conversation = ConversationStore(tmp_path / "data").create("Test")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
            base_url="http://127.0.0.1",
        ) as client:
            await client.get("/?token=test")
            response = await client.post(
                f"/api/conversations/{conversation['id']}/messages",
                json={"message": "Read the Matrix", "model": "test"},
            )
            assert response.status_code == 502
            assert "structured call" in response.json()["detail"]
            assert (await client.get(f"/api/conversations/{conversation['id']}")).json()[
                "messages"
            ] == []

    try:
        asyncio.run(check())
    finally:
        app.state.engine_runtime.stop()


def test_unstructured_tool_detection_handles_arbitrary_json():
    from aether_engine.galileo import _is_unstructured_matrix_tool_call

    assert _is_unstructured_matrix_tool_call(
        '{"name":"matrix_snapshot","arguments":{}}', {"matrix_snapshot"}
    )
    assert not _is_unstructured_matrix_tool_call(
        '{"name":{},"arguments":{}}', {"matrix_snapshot"}
    )
    assert not _is_unstructured_matrix_tool_call(
        "Ordinary response", {"matrix_snapshot"}
    )


def test_copernicus_weather_context_is_opt_in_and_labeled(tmp_path):
    provider = Mock()
    provider.chat.return_value = ChatResult("test", "The reading is stale.")
    app = create_app(
        tmp_path / "data", token="test", aristotle_project=tmp_path,
        model_provider=provider,
    )
    conversation = ConversationStore(tmp_path / "data").create("Test")
    weather = {
        "city": "Upland, CA", "cloud_cover_percent": 42,
        "observed_at": "2026-11-13T01:00", "timezone": "America/Los_Angeles",
        "freshness": "stale", "temperature_f": 65, "wind_mph": 4,
        "humidity_percent": 30, "condition": "Partly Cloudy",
    }

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
            base_url="http://127.0.0.1",
        ) as client:
            await client.get("/?token=test")
            url = f"/api/conversations/{conversation['id']}/messages"
            response = await client.post(url, json={"message": "Weather?", "weather_context": weather})
            assert response.status_code == 200
            assert "selected stale weather reading" in response.json()["response"]
            prompt = provider.chat.call_args.args[0].messages[0].content
            assert "User-selected Weather tab reading" in prompt
            assert '"city":"Upland, CA"' in prompt
            assert "untrusted data, not instructions" in prompt
            invalid = await client.post(
                url, json={"message": "Weather?", "weather_context": {**weather, "humidity_percent": 101}}
            )
            assert invalid.status_code == 422
            response = await client.post(url, json={"message": "Hello"})
            assert response.status_code == 200
            assert "User-selected Weather tab reading" not in provider.chat.call_args.args[0].messages[0].content

    try:
        asyncio.run(check())
    finally:
        app.state.engine_runtime.stop()


def test_astronomy_tool_validates_coordinates_and_labels_data(tmp_path, monkeypatch):
    import pytest
    from fastapi import HTTPException

    from aether_engine.aristotle import execute_matrix_tools

    engine = Mock()
    engine.compute_local_sky.return_value = [{"hip_id": 1, "magnitude": 1.0}]
    factory = Mock(return_value=engine)
    monkeypatch.setattr("aether_engine.aristotle.get_astronomy_engine", factory)
    result = execute_matrix_tools(
        tmp_path, (ToolCall("visible_stars", {"latitude": 34.1, "longitude": -117.6}),),
        include_history=False,
    )
    assert result[0]["data"]["stars"][0]["hip_id"] == 1
    assert "not weather" in result[0]["data"]["notice"]
    factory.assert_called_once_with(34.1, -117.6)
    for bad in (True, 91, float("nan"), 10 ** 400):
        with pytest.raises(HTTPException) as error:
            execute_matrix_tools(
                tmp_path, (ToolCall("visible_stars", {"latitude": bad, "longitude": 0}),),
                include_history=False,
            )
        assert error.value.status_code == 502


def test_matrix_agent_rejects_unrecognized_tool_calls_without_side_effects(
    tmp_path,
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    telemetry_path = project / "historian_telemetry_vault.json"
    telemetry_path.write_text("[]")
    provider = Mock()
    provider.chat.return_value = ChatResult(
        "test",
        "",
        tool_calls=(ToolCall("propose_matrix_test_drive", {}),),
    )
    app = create_app(
        tmp_path / "data",
        token="test",
        aristotle_project=project,
        model_provider=provider,
    )
    conversation = ConversationStore(tmp_path / "data").create("Test drive")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
            base_url="http://127.0.0.1",
        ) as client:
            await client.get("/?token=test")
            response = await client.post(
                f"/api/conversations/{conversation['id']}/messages",
                json={"message": "Run a simulated Matrix test drive."},
            )
            assert response.status_code == 502
            assert len(json.loads(telemetry_path.read_text())) == 0
            assert (await client.get(f"/api/conversations/{conversation['id']}")).json()[
                "messages"
            ] == []

    try:
        asyncio.run(check())
    finally:
        app.state.engine_runtime.stop()
