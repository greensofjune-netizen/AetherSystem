from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

RequestT = TypeVar("RequestT")
ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class EngineCapability(Generic[RequestT, ResultT]):
    name: str
    handler: Callable[[RequestT], ResultT]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Engine capability name cannot be empty.")
        if not callable(self.handler):
            raise ValueError("Engine capability handler must be callable.")


class EngineCapabilityUnavailableError(LookupError):
    """Raised when a requested capability is not registered with the engine."""


class EngineOrchestrator:
    """Register and dispatch typed operations to independent engine capabilities."""

    def __init__(self) -> None:
        self._capabilities: dict[str, object] = {}

    def register(
        self, capability: EngineCapability[RequestT, ResultT]
    ) -> None:
        if capability.name in self._capabilities:
            raise ValueError(
                f"Engine capability is already registered: {capability.name}."
            )
        self._capabilities[capability.name] = capability

    def execute(
        self,
        capability: EngineCapability[RequestT, ResultT],
        request: RequestT,
    ) -> ResultT:
        if self._capabilities.get(capability.name) is not capability:
            raise EngineCapabilityUnavailableError(
                f"Engine capability is not registered: {capability.name}."
            )
        return capability.handler(request)

    def capability_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._capabilities))
