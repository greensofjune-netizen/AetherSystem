import asyncio
import base64
from threading import Event
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException

from aether_engine import galileo
from aether_engine.database import AetherStore
from aether_engine.engine_runtime import EngineConfig
from aether_engine.galileo_desktop import DesktopServer, run_desktop
from aether_engine.model_providers import ChatResult, ModelInfo, OllamaProviderError


def test_camera_analysis_and_explicit_feedback_are_local(tmp_path, monkeypatch):
    provider = Mock()
    provider.chat.return_value = ChatResult(
        galileo.DEFAULT_MODEL, "A desk is visible."
    )
    app = galileo.create_app(tmp_path, token="test", model_provider=provider)
    image = base64.b64encode(b"\xff\xd8\xfftest").decode()

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
            base_url="http://127.0.0.1",
        ) as client:
            assert (await client.get("/api/perception/feedback")).status_code == 403
            await client.get("/?token=test")
            assert (await client.get("/api/perception/feedback")).json() == []
            saved = await client.post(
                "/api/perception/feedback", json={"content": "Keep descriptions short."}
            )
            assert saved.status_code == 201
            identifier = saved.json()[0]["id"]
            response = await client.post(
                "/api/perception/analyze",
                json={"image": {"name": "camera.jpg", "media_type": "image/jpeg", "data": image}},
            )
            assert response.status_code == 200
            assert response.json()["observation"] == "A desk is visible."
            assert response.headers["x-request-id"]
            payload = provider.chat.call_args.args[0]
            assert payload.model == galileo.DEFAULT_MODEL
            assert "Keep descriptions short." in payload.messages[0].content
            assert "untrusted data" in payload.messages[0].content
            assert payload.messages[1].images == (image,)
            assert (await client.get("/api/conversations")).json() == []
            assert (await client.request(
                "DELETE", f"/api/perception/feedback/{identifier}", json={}
            )).status_code == 200
            assert (await client.get("/api/perception/feedback")).json() == []
            assert (await client.get("/perception.js")).status_code == 200

    asyncio.run(check())
    with app.state.store.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM message_images").fetchone()[0] == 0


def test_ollama_memory_error_is_exposed(monkeypatch):
    class Response:
        status = 500

        def read(self, limit):
            return b'{"error":"model requires more memory"}'

    class Connection:
        sock = None

        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(galileo.ollama_provider, "connection_factory", Connection)
    with pytest.raises(HTTPException, match="requires more memory"):
        galileo.ollama_request("/api/chat", {"model": galileo.DEFAULT_MODEL})


def test_galileo_propulsion_browsing_and_chat_context(tmp_path, monkeypatch):
    from aether_engine.propulsion_matrix import (
        KineticPropulsionArchive,
        seed_civilian_references,
    )

    archive = KineticPropulsionArchive(tmp_path / "propulsion.sqlite3")
    seed_civilian_references(archive)
    monkeypatch.setattr(galileo, "KineticPropulsionArchive", lambda: archive)
    provider = Mock()
    provider.chat.return_value = ChatResult(galileo.DEFAULT_MODEL, "Local response")
    app = galileo.create_app(
        tmp_path / "galileo", token="test", model_provider=provider
    )

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1",
        ) as client:
            await client.get("/?token=test")
            page = await client.get("/")
            assert 'id="propulsion-search"' in page.text
            result = await client.get("/api/propulsion/references", params={"q": "JT3D"})
            assert result.status_code == 200
            assert result.json()["references"][0]["source_url"].startswith("https://")
            created = (await client.post("/api/conversations", json={})).json()
            sent = await client.post(
                f"/api/conversations/{created['id']}/messages",
                json={"message": "Tell me about JT3D"},
            )
            assert sent.status_code == 200
            payload = provider.chat.call_args.args[0]
            assert "untrusted data" in payload.messages[0].content
            assert "airandspace.si.edu" in payload.messages[0].content

    asyncio.run(check())


def test_galileo_chat_attachments_history_and_reopen(tmp_path, monkeypatch):
    provider = Mock()
    provider.list_models.return_value = (
        ModelInfo(galileo.DEFAULT_MODEL, ("vision",)),
    )
    provider.chat.return_value = ChatResult(galileo.DEFAULT_MODEL, "Test reply")
    app = galileo.create_app(
        tmp_path, token="test-session", model_provider=provider
    )

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1",
        ) as client:
            assert (await client.get("/")).status_code == 403
            bootstrap = await client.get("/?token=test-session")
            assert bootstrap.status_code == 200
            assert "HttpOnly" in bootstrap.headers["set-cookie"]
            assert "Galileo" in bootstrap.text
            assert (await client.get("/health")).json()["application"] == "Galileo"
            runtime_status = await client.get("/api/engine/status")
            assert runtime_status.status_code == 200
            assert runtime_status.json()["runtime"]["state"] == "ready"
            models = (await client.get("/api/models")).json()
            assert models == {
                "models": [galileo.DEFAULT_MODEL],
                "vision_models": [galileo.DEFAULT_MODEL],
                "default_model": galileo.DEFAULT_MODEL,
            }
            assert (await client.get("/api/model/status")).json()["status"] == "pending"
            large_invalid = await client.post(
                "/api/conversations", json={"unexpected": "x" * 1_100_000}
            )
            assert large_invalid.status_code == 422
            created = (await client.post("/api/conversations", json={})).json()
            url = f"/api/conversations/{created['id']}"
            image_data = base64.b64encode(b"\x89PNG\r\n\x1a\nsample").decode()
            response = await client.post(
                url + "/messages",
                json={
                    "message": "Explain this",
                    "model": galileo.DEFAULT_MODEL,
                    "attachments": [
                        {"name": "sample.txt", "content": "Test reference"}
                    ],
                    "images": [
                        {
                            "name": "sample.png",
                            "media_type": "image/png",
                            "data": image_data,
                        }
                    ],
                },
            )
            assert response.status_code == 200, response.text
            saved = response.json()["conversation"]
            assert len(saved["messages"]) == 2
            assert "Test reference" in saved["messages"][0]["content"]
            assert saved["title"] == "Explain this"
            assert saved["messages"][0]["images"][0]["data"] == image_data
            assert provider.chat.call_args.args[0].messages[-1].images == (image_data,)
            second = await client.post(url + "/messages", json={"message": "And now?"})
            assert second.status_code == 200
            messages = provider.chat.call_args.args[0].messages
            assert len(messages) == 4
            assert messages[0].role == "system"
            assert messages[-2].content == "Test reply"
            assert messages[1].images == (image_data,)
            assert (await client.get(url)).json()["messages"][-1][
                "content"
            ] == "Test reply"
            assert len((await client.get("/api/conversations")).json()) == 1
            for asset in [
                "/galileo.js",
                "/galileo.css",
                "/multimodal.css",
                "/speech.js",
                "/astrology.js",
                "/astrology.css",
                "/formulas.js",
                "/formulas.css",
                "/weather",
                "/weather.js",
                "/stargazer",
                "/stargazer.js",
            ]:
                assert (await client.get(asset)).status_code == 200
            assert (await client.get("/not-a-file")).status_code == 404

    asyncio.run(check())
    reopened = galileo.ConversationStore(tmp_path)
    assert len(reopened.get(reopened.list()[0]["id"])["messages"]) == 4
    assert reopened.path.stat().st_mode & 0o777 == 0o600
    assert tmp_path.stat().st_mode & 0o777 == 0o700


def test_galileo_chat_applies_inference_backpressure(tmp_path):
    entered = Event()
    release = Event()
    provider = Mock()

    def blocked_chat(request):
        entered.set()
        assert release.wait(2)
        return ChatResult(galileo.DEFAULT_MODEL, "Finished")

    provider.chat.side_effect = blocked_chat
    app = galileo.create_app(
        tmp_path,
        token="test",
        model_provider=provider,
        engine_config=EngineConfig(
            max_concurrent_inferences=1,
            max_queued_inferences=0,
            inference_queue_timeout_seconds=1,
        ),
    )
    conversation = app.state.store.create("Test")
    other_conversation = app.state.store.create("Other")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1",
            cookies={"galileo_session": "test"},
        ) as client:
            first = asyncio.create_task(
                client.post(
                    f"/api/conversations/{conversation['id']}/messages",
                    json={"message": "First"},
                )
            )
            assert await asyncio.to_thread(entered.wait, 1)
            second = await client.post(
                f"/api/conversations/{other_conversation['id']}/messages",
                json={"message": "Second"},
            )
            assert second.status_code == 429
            assert second.headers["retry-after"] == "1"
            release.set()
            completed = await first
            assert completed.status_code == 200

    asyncio.run(check())


def test_galileo_astronomy_endpoint_validates_and_returns_visible_stars(
    tmp_path, monkeypatch
):
    engine = Mock()
    engine.compute_local_sky.return_value = [{"hip_id": 1, "alt_deg": 10.0}]
    monkeypatch.setattr(galileo, "get_astronomy_engine", lambda *_coordinates: engine)
    app = galileo.create_app(tmp_path, token="test")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1",
            cookies={"galileo_session": "test"},
        ) as client:
            response = await client.get(
                "/api/astronomy/visible-stars?latitude=34&longitude=-117"
            )
            assert response.status_code == 200
            assert response.json()["stars"] == [{"hip_id": 1, "alt_deg": 10.0}]
            assert engine.compute_local_sky.call_args.args[1] == 4.0
            invalid = await client.get(
                "/api/astronomy/visible-stars?latitude=91&longitude=-117"
            )
            assert invalid.status_code == 422

    asyncio.run(check())


def test_galileo_formula_lab_uses_existing_calculators(tmp_path):
    from aether_engine.spin_network_boundary import compute_spin_network_boundary

    app = galileo.create_app(tmp_path, token="test")
    app.state.model_status["status"] = "ready"
    expected_spins, expected_area, expected_entropy = compute_spin_network_boundary(
        num_links=12,
        seed=7,
    )

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1",
            cookies={"galileo_session": "test"},
        ) as client:
            page = await client.get("/")
            assert page.status_code == 200
            assert 'data-tab="formula"' in page.text
            assert 'id="quantum-form"' in page.text
            assert 'id="spin-form"' in page.text
            assert 'id="los-form"' in page.text

            quantum = await client.post(
                "/api/formulas/quantum",
                json={
                    "risk_coefficient": 0.3,
                    "fluctuation_velocity": 50,
                    "state_density": 57,
                },
            )
            assert quantum.status_code == 200
            assert quantum.json()["wave_coherence_percent"] == 70.0
            assert quantum.json()["entropy_index"] == 67.0
            collapse = await client.post(
                "/api/formulas/quantum",
                json={"state_density": 200},
            )
            assert collapse.status_code == 422

            spin = await client.post(
                "/api/formulas/spin-network",
                json={"num_links": 12, "seed": 7},
            )
            assert spin.status_code == 200
            assert spin.json()["mean_spin"] == float(expected_spins.mean())
            assert spin.json()["boundary_area_planck_squared"] == expected_area
            assert spin.json()["entanglement_entropy_nats"] == expected_entropy
            invalid_spin = await client.post(
                "/api/formulas/spin-network",
                json={"num_links": 10_001, "seed": 7},
            )
            assert invalid_spin.status_code == 422

            los = await client.post(
                "/api/formulas/los-link",
                json={
                    "tx_lat": 34,
                    "tx_lon": -117,
                    "tx_height_m": 10,
                    "rx_lat": 34.01,
                    "rx_lon": -117,
                    "rx_height_m": 10,
                    "freq_ghz": 5.8,
                },
            )
            assert los.status_code == 200
            assert los.json()["distance_km"] > 0
            assert "fresnel_60pct_clearance_m" in los.json()
            invalid_los = await client.post(
                "/api/formulas/los-link",
                json={
                    "tx_lat": 34,
                    "tx_lon": -117,
                    "tx_height_m": 10,
                    "rx_lat": 34.01,
                    "rx_lon": -117,
                    "rx_height_m": 10,
                    "freq_ghz": 0,
                },
            )
            assert invalid_los.status_code == 422

    asyncio.run(check())


def test_galileo_workspace_import_is_private_bounded_and_local(tmp_path, monkeypatch):
    database_path = tmp_path / "workspace-events.sqlite3"
    monkeypatch.setenv("AETHER_DATABASE_PATH", str(database_path))
    app = galileo.create_app(tmp_path / "galileo", token="test")
    app.state.model_status["status"] = "ready"

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1",
        ) as client:
            assert (await client.post(
                "/api/workspace/import",
                json={"records": [{"id": "calendar-1", "summary": "Plan"}]},
            )).status_code == 403
            await client.get("/?token=test")
            page = await client.get("/")
            assert 'data-tab="workspace"' in page.text
            assert 'id="workspace-json"' in page.text
            assert (await client.get("/workspace.js")).status_code == 200
            assert (await client.get("/workspace.css")).status_code == 200

            records = [
                {
                    "id": "calendar-1",
                    "summary": "Stargazing session",
                    "tracking_pixel_hash": "discard this",
                },
                {
                    "id": "calendar-2",
                    "summary": "Unauthorized tracking test",
                    "description": "Review exploit attempt",
                },
            ]
            preview = await client.post(
                "/api/workspace/import",
                json={"records": records, "dry_run": True},
            )
            assert preview.status_code == 200
            assert preview.json()["dry_run"] is True
            assert preview.json()["cleared_count"] == 1
            assert preview.json()["blocked_count"] == 1
            assert preview.json()["events"][0]["payload_summary"] == "Stargazing session"
            assert "tracking_pixel_hash" not in preview.text
            assert not database_path.exists()

            saved = await client.post(
                "/api/workspace/import",
                json={
                    "records": [
                        {"id": "calendar-3", "summary": "Planning", "description": ""}
                    ],
                    "dry_run": False,
                },
            )
            assert saved.status_code == 200
            assert saved.json()["dry_run"] is False
            assert saved.json()["cleared_count"] == 1
            stored = AetherStore(database_path).list_events(topic="workspace-bridge")
            assert len(stored) == 1
            assert "sanitized_calendar-3: Planning" in stored[0].message

            invalid = await client.post(
                "/api/workspace/import",
                json={"records": [{"id": "calendar-4", "summary": None}]},
            )
            assert invalid.status_code == 422
            too_many = await client.post(
                "/api/workspace/import",
                json={
                    "records": [
                        {"id": str(index), "summary": "Plan"} for index in range(101)
                    ]
                },
            )
            assert too_many.status_code == 422
            oversized = await client.post(
                "/api/workspace/import",
                json={
                    "records": [
                        {
                            "id": "calendar-5",
                            "summary": "x" * galileo.MAX_WORKSPACE_IMPORT_BYTES,
                        }
                    ]
                },
            )
            assert oversized.status_code == 413

    asyncio.run(check())


def test_galileo_failure_preserves_saved_chat(tmp_path, monkeypatch):
    provider = Mock()
    provider.chat.side_effect = OllamaProviderError("Ollama offline.")
    app = galileo.create_app(tmp_path, token="test", model_provider=provider)
    conversation = app.state.store.create("New conversation")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1",
            cookies={"galileo_session": "test"},
        ) as client:
            result = await client.post(
                f"/api/conversations/{conversation['id']}/messages",
                json={"message": "Please respond"},
            )
            assert result.status_code == 503
            assert app.state.store.get(conversation["id"])["messages"] == []
            app.state.store.get(conversation["id"])
            assert (await client.get("/api/conversations/missing")).status_code == 404

    asyncio.run(check())


def test_galileo_deletes_conversation_and_messages(tmp_path):
    app = galileo.create_app(tmp_path, token="test")
    deleted = app.state.store.create("Delete me")
    retained = app.state.store.create("Keep me")
    app.state.store.save_exchange(deleted["id"], "Question", "Answer", "Delete me")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1",
            cookies={"galileo_session": "test"},
        ) as client:
            response = await client.request(
                "DELETE", f"/api/conversations/{deleted['id']}", json={}
            )
            assert response.status_code == 200
            assert response.json() == {"deleted": True}
            assert (
                await client.get(f"/api/conversations/{deleted['id']}")
            ).status_code == 404
            assert (
                await client.get(f"/api/conversations/{retained['id']}")
            ).status_code == 200
            assert (await client.get("/api/conversations")).json() == [
                {
                    "id": retained["id"],
                    "title": retained["title"],
                    "updated_at": retained["updated_at"],
                }
            ]
            assert (
                await client.request(
                    "DELETE", f"/api/conversations/{deleted['id']}", json={}
                )
            ).status_code == 404

    asyncio.run(check())
    with app.state.store.connection() as connection:
        message_count = connection.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
            (deleted["id"],),
        ).fetchone()[0]
    assert message_count == 0


@pytest.mark.parametrize(
    "attachment",
    [
        {"name": "../secret.txt", "content": "text"},
        {"name": "sample.pdf", "content": "text"},
        {"name": "sample.txt", "content": "\x00binary"},
        {"name": "sample.txt", "content": "x" * 60001},
        {"name": "sample.txt", "content": "\u00e9" * 30001},
    ],
)
def test_galileo_rejects_invalid_attachments(attachment):
    with pytest.raises(ValueError):
        galileo.Attachment.model_validate(attachment)


def test_galileo_blocks_remote_access_and_cross_origin_writes(tmp_path):
    app = galileo.create_app(tmp_path, token="test")

    async def check():
        for host, address in [
            ("evil.example", "127.0.0.1"),
            ("127.0.0.1", "192.0.2.1"),
        ]:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, client=(address, 123)),
                base_url=f"http://{host}",
                cookies={"galileo_session": "test"},
            ) as client:
                assert (await client.get("/health")).status_code == 403
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1",
            cookies={"galileo_session": "test"},
        ) as client:
            assert (
                await client.post(
                    "/api/conversations",
                    json={},
                    headers={"Origin": "https://evil.example"},
                )
            ).status_code == 403
            assert (
                await client.post("/api/conversations", content="no json")
            ).status_code == 415
            assert (
                await client.post("/api/conversations", json={"title": " "})
            ).status_code == 422
            assert (
                await client.post(
                    "/api/conversations",
                    content="x" * 8_500_001,
                    headers={"Content-Type": "application/json"},
                )
            ).status_code == 413

    asyncio.run(check())


def test_desktop_server_starts_and_closes_listener(tmp_path):
    import socket
    from urllib.request import urlopen

    server = DesktopServer(tmp_path)
    try:
        server.start()
        with urlopen(server.url) as response:
            assert response.status == 200
        assert server.thread.is_alive()
    finally:
        server.stop()
    assert not server.thread.is_alive()
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", server.port)) != 0


@pytest.mark.parametrize(
    ("aristotle", "model_args", "expected_model"),
    [
        (False, [], "qwen3.5:4b"),
        (False, ["--model", "custom-model"], "custom-model"),
        (True, [], "qwen3.5:4b"),
    ],
)
def test_desktop_model_default_and_override(
    tmp_path, monkeypatch, aristotle, model_args, expected_model
):
    import sys

    from aether_engine import galileo_desktop

    (tmp_path / "galileo.log").touch()
    server = Mock()
    desktop_server = Mock(return_value=server)
    monkeypatch.setattr(galileo_desktop, "DesktopServer", desktop_server)
    monkeypatch.setattr(galileo_desktop, "run_desktop", Mock())
    monkeypatch.setattr(galileo_desktop.importlib, "import_module", Mock())
    monkeypatch.setattr(galileo_desktop.logging, "basicConfig", Mock())
    monkeypatch.setattr(
        sys, "argv", ["galileo", "--data-directory", str(tmp_path), *model_args]
    )

    assert galileo_desktop.main(project_directory=tmp_path, aristotle=aristotle) == 0
    desktop_server.assert_called_once_with(
        tmp_path, expected_model, aristotle_project=tmp_path if aristotle else None
    )


def test_desktop_window_failure_still_stops_backend():
    server = Mock()
    webview = Mock()
    webview.start.side_effect = RuntimeError("Native window failed")
    with pytest.raises(RuntimeError, match="Native window"):
        run_desktop(server, webview)
    server.stop.assert_called_once()


def test_window_shutdown_interrupts_waiting_ollama_response(monkeypatch):
    import http.client
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Event, Thread

    reading = Event()
    release = Event()
    errors = []

    class SlowModel(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.flush()
            reading.set()
            release.wait(5)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowModel)
    original = http.client.HTTPConnection
    monkeypatch.setattr(
        galileo.ollama_provider,
        "connection_factory",
        lambda *args, **kwargs: original("127.0.0.1", server.server_port, timeout=5),
    )
    serving = Thread(target=server.serve_forever, daemon=True)

    def request():
        try:
            galileo.ollama_request("/api/tags")
        except HTTPException as error:
            errors.append(error)

    worker = Thread(target=request, daemon=True)
    serving.start()
    worker.start()
    try:
        assert reading.wait(3)
        galileo.cancel_ollama_requests()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert errors and errors[0].status_code == 503
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        serving.join(timeout=2)
        worker.join(timeout=2)
