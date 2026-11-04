from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx

from aether_engine import server


def _request(
    method: str,
    path: str,
    **kwargs: Any,
) -> httpx.Response:
    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=server.app)
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
