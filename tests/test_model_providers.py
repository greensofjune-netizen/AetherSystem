from aether_engine.model_providers import (
    ChatRequest,
    LocalEngineProvider,
    ModelInfo,
    OllamaProvider,
    ProviderMessage,
)


def test_ollama_chat_uses_typed_request_and_returns_usage(monkeypatch):
    provider = OllamaProvider()
    captured = {}

    def request(path, payload=None):
        captured["path"] = path
        captured["payload"] = payload
        return {
            "model": "qwen-local",
            "message": {"content": "  A local response.  "},
            "prompt_eval_count": 8,
            "eval_count": 4,
        }

    monkeypatch.setattr(provider, "request", request)
    response = provider.chat(
        ChatRequest(
            "qwen-local",
            (
                ProviderMessage("system", "Be concise."),
                ProviderMessage("user", "Describe the image.", ("aW1hZ2U=",)),
            ),
            temperature=0.4,
            max_output_tokens=128,
        )
    )

    assert captured["path"] == "/api/chat"
    assert captured["payload"] == {
        "model": "qwen-local",
        "stream": False,
        "messages": [
            {"role": "system", "content": "Be concise."},
            {
                "role": "user",
                "content": "Describe the image.",
                "images": ["aW1hZ2U="],
            },
        ],
        "options": {"temperature": 0.4, "num_predict": 128},
    }
    assert response.content == "  A local response.  "
    assert response.model == "qwen-local"
    assert response.prompt_tokens == 8
    assert response.completion_tokens == 4


def test_ollama_list_models_returns_typed_capabilities_and_health(monkeypatch):
    provider = OllamaProvider()
    monkeypatch.setattr(
        provider,
        "request",
        lambda path: {
            "models": [
                {"name": "qwen-local", "capabilities": ["vision", "tools"]},
                {"name": "text-local"},
            ]
        },
    )

    assert provider.list_models() == (
        ModelInfo("qwen-local", ("vision", "tools")),
        ModelInfo("text-local", ()),
    )
    assert provider.health().available is True
    assert provider.health().model_count == 2


def test_local_engine_provider_maps_chat_and_reasoning_effort(tmp_path):
    class LocalEngine:
        model_path = tmp_path / "local.gguf"

        def execute_local_inference(
            self, *, prompt, reasoning_effort, max_output_tokens=None
        ):
            assert prompt == "Explain this."
            assert reasoning_effort == "high"
            assert max_output_tokens == 2048
            return {"status": "SUCCESS", "model": "local.gguf", "output": "Answer"}

        def preload(self):
            return None

    provider = LocalEngineProvider(LocalEngine)
    result = provider.chat(
        ChatRequest(
            "local.gguf",
            (ProviderMessage("user", "Explain this."),),
            reasoning_effort="high",
        )
    )
    assert result.model == "local.gguf"
    assert result.content == "Answer"


def test_local_engine_provider_preserves_unavailable_status(tmp_path):
    class LocalEngine:
        model_path = tmp_path / "missing.gguf"

        def execute_local_inference(
            self, *, prompt, reasoning_effort, max_output_tokens=None
        ):
            return {
                "status": "OFFLINE_FALLBACK",
                "output": "Local model weights are missing.",
            }

        def preload(self):
            return None

    from aether_engine.model_providers import LocalInferenceProviderError

    provider = LocalEngineProvider(LocalEngine)
    try:
        provider.chat(
            ChatRequest("missing.gguf", (ProviderMessage("user", "Hello"),))
        )
    except LocalInferenceProviderError as error:
        assert error.status == "OFFLINE_FALLBACK"
        assert error.http_status == 503
        assert str(error) == "Local model weights are missing."
    else:
        raise AssertionError("Expected the unavailable local model to fail.")
