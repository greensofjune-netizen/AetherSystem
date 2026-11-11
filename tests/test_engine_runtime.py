from unittest.mock import Mock

import pytest

from aether_engine.engine_core import EngineCapability, EngineOrchestrator
from aether_engine.engine_runtime import (
    EngineConfig,
    EngineNotReadyError,
    EngineRuntime,
    EngineState,
)
from aether_engine.model_providers import (
    ChatRequest,
    ChatResult,
    ModelInfo,
    ProviderHealth,
    ProviderMessage,
)


def test_runtime_lifecycle_dispatch_and_metrics():
    capability = EngineCapability("formula.example", lambda value: value + 1)
    orchestrator = EngineOrchestrator()
    orchestrator.register(capability)
    provider = Mock()
    provider.chat.return_value = ChatResult("local", "4")
    provider.list_models.return_value = (ModelInfo("local"),)
    provider.health.return_value = ProviderHealth(True, 1)
    runtime = EngineRuntime(orchestrator, {"ollama": provider})

    with pytest.raises(EngineNotReadyError, match="not ready"):
        runtime.execute(capability, 1)

    runtime.start()
    assert runtime.state is EngineState.READY
    assert runtime.execute(capability, 1) == 2
    result = runtime.chat(
        "ollama", ChatRequest("local", (ProviderMessage("user", "2 + 2"),))
    )
    assert result.content == "4"
    assert runtime.list_models("ollama") == (ModelInfo("local"),)
    assert runtime.health("ollama") == ProviderHealth(True, 1)

    status = runtime.status()
    assert status["state"] == "ready"
    assert status["capabilities"] == ["formula.example"]
    assert status["metrics"]["total_operations"] == 4
    assert status["metrics"]["failed_operations"] == 0

    runtime.stop()
    assert runtime.state is EngineState.STOPPED
    provider.cancel_pending.assert_called_once_with()
    with pytest.raises(EngineNotReadyError, match="not ready"):
        runtime.execute(capability, 1)


def test_engine_config_reads_explicit_resource_limits(monkeypatch):
    monkeypatch.setenv("AETHER_MAX_CONCURRENT_INFERENCES", "2")
    monkeypatch.setenv("AETHER_MAX_QUEUED_INFERENCES", "4")
    monkeypatch.setenv("AETHER_INFERENCE_QUEUE_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("AETHER_MODEL_REQUEST_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("AETHER_MODEL_PRELOAD_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("AETHER_MAX_OUTPUT_TOKENS", "512")

    assert EngineConfig.from_environment() == EngineConfig(
        max_concurrent_inferences=2,
        max_queued_inferences=4,
        inference_queue_timeout_seconds=3.5,
        model_request_timeout_seconds=45,
        model_preload_timeout_seconds=90,
        max_output_tokens=512,
    )


def test_engine_config_rejects_invalid_resource_limits(monkeypatch):
    monkeypatch.setenv("AETHER_MAX_CONCURRENT_INFERENCES", "not-an-int")
    with pytest.raises(ValueError, match="must be an integer"):
        EngineConfig.from_environment()

    with pytest.raises(ValueError, match="at least one"):
        EngineConfig(max_concurrent_inferences=0)
