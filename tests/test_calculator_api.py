import asyncio
import json
import logging

import httpx

from aether_engine.calculator_api import MAX_REQUEST_BYTES, create_app


def test_calculator_api_requires_bearer_token_even_on_loopback(caplog):
    token = "secret-for-tests"
    app = create_app(token=token)

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
            base_url="http://127.0.0.1",
        ) as client:
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json()["application"] == "Aether Calculator API"

            unauthenticated = await client.post(
                "/api/formulas/quantum", json={"state_density": 57}
            )
            assert unauthenticated.status_code == 401

            invalid_token = await client.post(
                "/api/formulas/quantum",
                json={"state_density": 57},
                headers={"Authorization": "Bearer wrong"},
            )
            assert invalid_token.status_code == 401

            authorized = await client.post(
                "/api/formulas/quantum",
                json={"state_density": 57},
                headers={"Authorization": "Bearer secret-for-tests"},
            )
            assert authorized.status_code == 200
            assert authorized.json()["wave_coherence_percent"] == 70.0
            assert authorized.json()["entropy_index"] == 67.0
            client.headers["Authorization"] = f"Bearer {token}"

            status = await client.get(
                "/api/engine/status",
            )
            assert status.status_code == 200
            assert status.json()["state"] == "ready"
            assert "formula.quantum" in status.json()["capabilities"]

            rejected = await client.post(
                "/api/formulas/quantum",
                json={"state_density": 57, "sensitive_prompt": "never-log-this"},
            )
            assert rejected.status_code == 422
            assert rejected.headers["x-request-id"]

            hidden_docs = await client.get(
                "/docs", headers={"Authorization": "Bearer secret-for-tests"}
            )
            assert hidden_docs.status_code == 404

    with caplog.at_level(logging.INFO, logger="aether_engine.requests"):
        asyncio.run(check())
    telemetry = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "aether_engine.requests"
    ]
    assert telemetry
    assert all("request_id" in item and "duration_ms" in item for item in telemetry)
    assert "never-log-this" not in caplog.text


def test_calculator_api_fails_closed_and_limits_request_size(monkeypatch):
    monkeypatch.delenv("AETHER_CALCULATOR_TOKEN", raising=False)
    unconfigured_app = create_app()
    authenticated_app = create_app(token="secret-for-tests")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=unconfigured_app, client=("127.0.0.1", 1)
            ),
            base_url="http://127.0.0.1",
        ) as client:
            unconfigured = await client.post(
                "/api/formulas/quantum", json={"state_density": 57}
            )
            assert unconfigured.status_code == 503

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=authenticated_app, client=("127.0.0.1", 1)
            ),
            base_url="http://127.0.0.1",
        ) as client:
            oversized = await client.post(
                "/api/formulas/quantum",
                json={"state_density": 1, "extra": "x" * MAX_REQUEST_BYTES},
                headers={"Authorization": "Bearer secret-for-tests"},
            )
            assert oversized.status_code == 413

    asyncio.run(check())
