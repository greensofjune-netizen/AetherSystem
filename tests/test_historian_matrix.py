from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import httpx


def shell_module():
    path = Path(__file__).resolve().parents[1] / "historian_matrix.py"
    spec = importlib.util.spec_from_file_location("historian_matrix", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shell_replaces_history_with_copernicus_chat(tmp_path):
    module = shell_module()
    app = module.create_app()

    async def check():
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8765"
        ) as client:
            page = await client.get("/")
            assert 'data-copernicus="true"' in page.text
            assert "/copernicus.js" in page.text
            assert "Copernicus" in page.text
            assert "Matrix data and controls are not connected." in page.text
            assert "frame-src 'self'" in page.headers["Content-Security-Policy"]
            assert (
                await client.get("/api/history")
            ).status_code == 404
            assert (
                await client.post(
                    "/api/history",
                    json={"topic": "release", "message": "Do not persist"},
                )
            ).status_code == 405
            for route in [
                "/aether_master_matrix.py",
                "/api/v1/export",
                "/v1/chat/completions",
            ]:
                assert (await client.get(route)).status_code == 404
            assert (await client.get("/health")).json()["status"] == "healthy"
            assert (await client.get("/copernicus.js")).status_code == 200

    asyncio.run(check())
    assert not list(tmp_path.iterdir())


def test_ai_receives_current_message_and_optional_weather_context(monkeypatch):
    module = shell_module()
    prompts = []
    systems = []
    fail = False

    def query(self, prompt, *, system=None):
        prompts.append(prompt)
        systems.append(system)
        if fail:
            raise module.OllamaConnectionError("offline")
        return "Hello from Copernicus."

    monkeypatch.setattr(module.AetherHistorian, "query_brain", query)
    app = module.create_app(ollama_model="atlas-qwen-coder:latest")

    async def check():
        nonlocal fail
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1"
        ) as client:
            assert 'id="copernicus-panel"' in (await client.get("/")).text
            assert (await client.get("/api/chat/status")).json()["enabled"]
            answer = await client.post("/api/chat", json={"message": "Hello"})
            data = answer.json()
            assert data["model"] == "atlas-qwen-coder:latest"
            assert data["response"] == "Hello from Copernicus."
            assert data["request_utc"] <= data["response_utc"]
            assert data["request_utc"] in systems[0]
            assert "+00:00" in (await client.get("/api/clock")).json()["utc"]
            assert len(prompts) == 1 and prompts[0].endswith("Hello")
            assert "personal companion" in systems[0]
            assert "no persistent profile or memory" in systems[0]
            assert "not a technical connection" in systems[0]
            assert "Matrix telemetry" in systems[0]
            assert "warm, attentive, thoughtful" in systems[0]
            weather_context = {
                "city": "Upland, CA",
                "cloud_cover_percent": 42,
                "observed_at": "2026-11-07T16:00",
                "timezone": "America/Los_Angeles",
                "freshness": "live",
            }
            response = await client.post(
                "/api/chat",
                json={"message": "Will it be cloudy?", "weather_context": weather_context},
            )
            assert response.status_code == 200
            assert prompts[1] == "Will it be cloudy?"
            assert "Upland, CA" in systems[1]
            assert "42" in systems[1]
            assert "live or stale" in systems[1]
            assert "not an affiliation or endorsement" in systems[1]
            assert (
                await client.post("/api/chat", json={"message": " "})
            ).status_code == 422
            assert (
                await client.post("/api/chat", json={"message": "x", "history": []})
            ).status_code == 422
            invalid_weather = {**weather_context, "cloud_cover_percent": 101}
            assert (
                await client.post(
                    "/api/chat",
                    json={"message": "Hello", "weather_context": invalid_weather},
                )
            ).status_code == 422
            fail = True
            assert (
                await client.post("/api/chat", json={"message": "Hello"})
            ).status_code == 503
            assert (await client.get("/api/history")).status_code == 404
            fail = False
            assert (
                await client.post("/api/chat", json={"message": "retry"})
            ).status_code == 200

    asyncio.run(check())


def test_ai_disabled_by_default():
    app = shell_module().create_app()

    async def check():
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1"
        ) as client:
            assert not (await client.get("/api/chat/status")).json()["enabled"]
            assert (
                await client.post("/api/chat", json={"message": "Hi"})
            ).status_code == 503

    asyncio.run(check())


def test_shell_rejects_remote_hosts_clients_and_cross_origin_writes():
    app = shell_module().create_app()

    async def check():
        for address, host in [
            ("192.0.2.1", "127.0.0.1"),
            ("127.0.0.1", "evil.example"),
        ]:
            transport = httpx.ASGITransport(app=app, client=(address, 12345))
            async with httpx.AsyncClient(
                transport=transport, base_url=f"http://{host}"
            ) as client:
                assert (await client.get("/api/chat/status")).status_code == 403
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1"
        ) as client:
            response = await client.post(
                "/api/chat",
                json={"message": "Hello"},
                headers={"Origin": "https://evil.example"},
            )
            assert response.status_code == 403
            assert (
                await client.post("/api/chat", content="not json")
            ).status_code == 415
            assert (await client.get("/api/history")).status_code == 404

    asyncio.run(check())
