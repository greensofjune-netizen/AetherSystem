from __future__ import annotations

import json
import os

import pytest

from aether_engine.ai_bridge import AetherLunaBridge, LocalAirGappedEngine


def test_bridge_uses_offline_simulation_without_network_or_credentials(
    monkeypatch, caplog
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    bridge = AetherLunaBridge()

    with caplog.at_level("INFO", logger="aether_engine.ai_bridge"):
        response = bridge.generate_agentic_response(
            "  Check the schema.  ", reasoning_effort="high"
        )

    assert response["status"] == "SIMULATED"
    assert response["model"] == "gpt-6-luna"
    assert json.loads(response["choices"][0]["message"]["content"]) == {
        "qed_analysis": "Topological baseline stable. Ready for 100yr sync."
    }
    assert "no request sent" in caplog.text


def test_bridge_calls_only_an_explicit_transport(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captured: dict[str, object] = {}

    def transport(payload: dict[str, object], api_key: str) -> dict[str, object]:
        captured["payload"] = payload
        captured["api_key"] = api_key
        return {"status": "SUCCESS", "choices": []}

    bridge = AetherLunaBridge(
        "test-secret",
        model_id="provider-model",
        transport=transport,
    )
    response = bridge.generate_agentic_response("Prompt", "xhigh")

    assert response["status"] == "SUCCESS"
    assert captured["api_key"] == "test-secret"
    assert captured["payload"] == {
        "model": "provider-model",
        "reasoning_effort": "xhigh",
        "messages": [
            {
                "role": "system",
                "content": "You are the Aether Co-Pilot Historian backend subagent.",
            },
            {"role": "user", "content": "Prompt"},
        ],
        "response_format": {"type": "json_object"},
    }


def test_transport_requires_api_key_and_response_object() -> None:
    bridge = AetherLunaBridge(transport=lambda _payload, _key: {})

    with pytest.raises(ValueError, match="API key is required"):
        bridge.generate_agentic_response("Prompt")

    bridge = AetherLunaBridge(
        "test-secret",
        transport=lambda _payload, _key: ["not", "an", "object"],  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="return a response object"):
        bridge.generate_agentic_response("Prompt")


@pytest.mark.parametrize(
    ("prompt", "effort", "message"),
    [
        ("  ", "medium", "Prompt cannot be empty"),
        ("valid", "invalid", "Reasoning effort must be one of"),
        ("valid", ["high"], "Reasoning effort must be one of"),
    ],
)
def test_bridge_validates_prompt_and_reasoning_effort(
    prompt: str,
    effort: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        AetherLunaBridge().generate_agentic_response(
            prompt,
            effort,  # type: ignore[arg-type]
        )


def test_bridge_rejects_empty_model_identifier() -> None:
    with pytest.raises(ValueError, match="Model identifier cannot be empty"):
        AetherLunaBridge(model_id="  ")


def test_multimodal_vision_and_audio_simulated_payloads():
    """Verifies that the upgraded bridge correctly parses both image and voice structures."""
    bridge = AetherLunaBridge(api_key="mock_qed_key")

    vision_res = bridge.analyze_visual_vector(
        "stardust_bytes_base64", "Scan the console frame."
    )
    assert vision_res["status"] == "SIMULATED"
    assert "choices" in vision_res

    audio_res = bridge.process_conversational_audio("speech_stream_bytes_base64")
    assert "audio" in audio_res["choices"][0]["message"]


def test_multimodal_simulation_does_not_require_credentials(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    bridge = AetherLunaBridge()

    assert bridge.analyze_visual_vector("image-data", "Describe the image.")[
        "status"
    ] == "SIMULATED"
    assert bridge.process_conversational_audio("audio-data")["status"] == "SIMULATED"


def test_local_engine_does_not_change_proxy_settings_or_create_model_directory(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example.test")
    monkeypatch.setenv("HTTPS_PROXY", "https://proxy.example.test")

    engine = LocalAirGappedEngine()

    assert not (tmp_path / "models").exists()
    assert engine.execute_local_inference("Check local model availability.") == {
        "status": "OFFLINE_FALLBACK",
        "output": "Local model weights are missing; no inference was performed.",
    }
    assert engine.process_local_vision("image-data", "Describe image.") == {
        "status": "INFERENCE_UNAVAILABLE",
        "analysis": "No local vision backend is configured; no image was analyzed.",
    }
    assert os.environ["HTTP_PROXY"] == "http://proxy.example.test"
    assert os.environ["HTTPS_PROXY"] == "https://proxy.example.test"
