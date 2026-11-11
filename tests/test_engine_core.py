import pytest

from aether_engine.engine_core import (
    EngineCapability,
    EngineCapabilityUnavailableError,
    EngineOrchestrator,
)


def test_engine_orchestrator_dispatches_registered_capability():
    capability = EngineCapability("formula.quantum", lambda value: value + 1)
    engine = EngineOrchestrator()
    engine.register(capability)

    assert engine.execute(capability, 4) == 5


def test_engine_orchestrator_rejects_duplicate_and_unregistered_capabilities():
    capability = EngineCapability("formula.quantum", lambda value: value)
    engine = EngineOrchestrator()
    engine.register(capability)

    with pytest.raises(ValueError, match="already registered"):
        engine.register(capability)
    with pytest.raises(EngineCapabilityUnavailableError, match="not registered"):
        engine.execute(EngineCapability("formula.unknown", lambda value: value), 4)
