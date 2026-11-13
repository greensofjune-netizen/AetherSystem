"""Opt-in local model evaluation using synthetic, disposable Matrix data."""

import asyncio
import json
import os
from time import perf_counter
from unittest.mock import Mock

import httpx
import pytest

from aether_engine.engine_runtime import EngineConfig
from aether_engine.galileo import create_app
from aether_engine.model_providers import OllamaProvider
from history_matrix_archive import HistoricalEntity, UniversalHistoryArchive

MODELS = (
    "qwen3.5:4b", "llama3.2:3b", "atlas-qwen-coder:latest",
    "aethersystem-core:latest",
)


@pytest.mark.skipif(
    os.environ.get("AETHER_EVAL_MATRIX_MODELS") != "1",
    reason="Local model evaluation is opt-in and requires Ollama and installed models.",
)
@pytest.mark.parametrize("model", MODELS)
def test_local_matrix_agent_evaluation(tmp_path, monkeypatch, model):
    monkeypatch.delenv("AETHER_HISTORY_ARCHIVE", raising=False)
    monkeypatch.delenv("AETHER_HISTORIAN_LOG_FILE", raising=False)
    sky = Mock()
    sky.compute_local_sky.return_value = [{"hip_id": 12345, "magnitude": 1.0}]
    monkeypatch.setattr(
        "aether_engine.aristotle.get_astronomy_engine", lambda _lat, _lon: sky
    )
    project = tmp_path / "project"
    project.mkdir()
    telemetry = project / "historian_telemetry_vault.json"
    telemetry.write_text(json.dumps([{"epoch": 7, "system_status": "SIMULATED"}]))
    archive = UniversalHistoryArchive(project / "universal_history.sqlite3")
    archive.ingest_entity(
        HistoricalEntity(
            "athens", "Athens", "city", "Greece", -500, 300,
            "Ancient Athens was a Greek city.", [],
        )
    )
    app = create_app(
        tmp_path / "data",
        token="evaluation",
        aristotle_project=project,
        model_provider=OllamaProvider(timeout=120),
        engine_config=EngineConfig(max_output_tokens=256),
    )

    async def evaluate():
        results = []
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
            base_url="http://127.0.0.1",
            timeout=240,
        ) as client:
            await client.get("/?token=evaluation")
            weather = {
                "city": "Example City", "cloud_cover_percent": 42,
                "observed_at": "2026-11-13T01:00", "timezone": "America/Los_Angeles",
                "freshness": "stale", "temperature_f": 65, "wind_mph": 4,
                "humidity_percent": 30, "condition": "Partly Cloudy",
            }
            for name, message, include_history, weather_context, expected in (
                (
                    "snapshot",
                    "Use the matrix_snapshot tool now and report the simulation epoch.",
                    False,
                    None,
                    ("Read-only Matrix tools used: Matrix snapshot.", "7"),
                ),
                (
                    "history",
                    "Use the search_history tool to search for Athens and report the result.",
                    True,
                    None,
                    ("History archive search", "Athens"),
                ),
                (
                    "astronomy",
                    "Use the visible_stars tool with latitude 34.1 and longitude -117.6.",
                    False,
                    None,
                    ("Astronomy calculation",),
                ),
                (
                    "weather",
                    "What is the temperature in the selected weather reading?",
                    False,
                    weather,
                    ("65", "selected stale weather reading"),
                ),
                (
                    "no_actions",
                    "Can you run a Matrix test drive? Do not run any tools.",
                    False,
                    None,
                    (),
                ),
            ):
                conversation = (await client.post("/api/conversations", json={})).json()
                started = perf_counter()
                response = await client.post(
                    f"/api/conversations/{conversation['id']}/messages",
                    json={
                        "message": message,
                        "model": model,
                        "include_history": include_history,
                        **({"weather_context": weather_context} if weather_context else {}),
                    },
                )
                elapsed = perf_counter() - started
                body = response.json()
                reply = body.get("response", "")
                passed = (
                    response.status_code == 200
                    and bool(reply.strip())
                    and all(part in reply for part in expected)
                    and (name != "no_actions" or "Read-only Matrix tools used:" not in reply)
                )
                results.append((name, passed))
                print(
                    f"MODEL_EVAL model={model} case={name} "
                    f"status={response.status_code} passed={passed} seconds={elapsed:.2f} "
                    f"detail={body.get('detail', '')} "
                    f"response={reply[:400] if not passed else ''}",
                    flush=True,
                )
        return results

    try:
        results = asyncio.run(evaluate())
        assert json.loads(telemetry.read_text()) == [
            {"epoch": 7, "system_status": "SIMULATED"}
        ]
        assert all(passed for _, passed in results), results
    finally:
        app.state.engine_runtime.stop()
