from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from threading import Lock
from time import perf_counter
from typing import Any, TypeVar

from .engine_core import EngineCapability, EngineOrchestrator
from .inference_scheduler import InferenceScheduler
from .model_providers import (
    ChatRequest,
    ChatResult,
    ModelInfo,
    ModelProvider,
    ProviderHealth,
)

ResultT = TypeVar("ResultT")


def _environment_integer(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer.") from error


def _environment_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a number.") from error


@dataclass(frozen=True)
class EngineConfig:
    max_concurrent_inferences: int = 1
    max_queued_inferences: int = 2
    inference_queue_timeout_seconds: float = 15
    model_request_timeout_seconds: float = 120
    model_preload_timeout_seconds: float = 300
    max_output_tokens: int = 2048
    max_context_chars: int = 240_000

    def __post_init__(self) -> None:
        if (
            type(self.max_concurrent_inferences) is not int
            or self.max_concurrent_inferences < 1
        ):
            raise ValueError("Maximum concurrent inferences must be at least one.")
        if (
            type(self.max_queued_inferences) is not int
            or self.max_queued_inferences < 0
        ):
            raise ValueError("Maximum queued inferences cannot be negative.")
        if (
            not isfinite(self.inference_queue_timeout_seconds)
            or self.inference_queue_timeout_seconds <= 0
        ):
            raise ValueError("Inference queue timeout must be greater than zero.")
        if (
            not isfinite(self.model_request_timeout_seconds)
            or self.model_request_timeout_seconds <= 0
        ):
            raise ValueError("Model request timeout must be greater than zero.")
        if (
            not isfinite(self.model_preload_timeout_seconds)
            or self.model_preload_timeout_seconds <= 0
        ):
            raise ValueError("Model preload timeout must be greater than zero.")
        if (
            type(self.max_output_tokens) is not int
            or not 1 <= self.max_output_tokens <= 8192
        ):
            raise ValueError("Maximum output tokens must be between 1 and 8192.")
        if type(self.max_context_chars) is not int or self.max_context_chars < 1:
            raise ValueError("Maximum context characters must be at least one.")

    @classmethod
    def from_environment(cls) -> EngineConfig:
        return cls(
            max_concurrent_inferences=_environment_integer(
                "AETHER_MAX_CONCURRENT_INFERENCES", 1
            ),
            max_queued_inferences=_environment_integer(
                "AETHER_MAX_QUEUED_INFERENCES", 2
            ),
            inference_queue_timeout_seconds=_environment_float(
                "AETHER_INFERENCE_QUEUE_TIMEOUT_SECONDS", 15
            ),
            model_request_timeout_seconds=_environment_float(
                "AETHER_MODEL_REQUEST_TIMEOUT_SECONDS", 120
            ),
            model_preload_timeout_seconds=_environment_float(
                "AETHER_MODEL_PRELOAD_TIMEOUT_SECONDS", 300
            ),
            max_output_tokens=_environment_integer("AETHER_MAX_OUTPUT_TOKENS", 2048),
        )


class EngineState(str, Enum):
    CREATED = "created"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"


class EngineNotReadyError(RuntimeError):
    """Raised when an operation is requested outside the ready lifecycle state."""


class EngineMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._operations: dict[str, dict[str, float | int]] = {}
        self._active = 0

    def measure(self, name: str, operation: Callable[[], ResultT]) -> ResultT:
        with self._lock:
            self._active += 1
            values = self._operations.setdefault(
                name,
                {"calls": 0, "failures": 0, "duration_ms_total": 0.0},
            )
            values["calls"] = int(values["calls"]) + 1
        started = perf_counter()
        failed = False
        try:
            return operation()
        except Exception:
            failed = True
            raise
        finally:
            duration_ms = (perf_counter() - started) * 1000
            with self._lock:
                values = self._operations[name]
                if failed:
                    values["failures"] = int(values["failures"]) + 1
                values["duration_ms_total"] = (
                    float(values["duration_ms_total"]) + duration_ms
                )
                self._active -= 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            operations = {
                name: {
                    "calls": int(values["calls"]),
                    "failures": int(values["failures"]),
                    "average_duration_ms": round(
                        float(values["duration_ms_total"]) / int(values["calls"]), 2
                    ),
                }
                for name, values in sorted(self._operations.items())
            }
            return {
                "active_operations": self._active,
                "total_operations": sum(item["calls"] for item in operations.values()),
                "failed_operations": sum(
                    item["failures"] for item in operations.values()
                ),
                "operations": operations,
            }


class EngineRuntime:
    """Own app-scoped engine lifecycle, capability dispatch, and provider work."""

    def __init__(
        self,
        orchestrator: EngineOrchestrator,
        providers: Mapping[str, ModelProvider] | None = None,
        config: EngineConfig | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.providers = dict(providers or {})
        self.config = config or EngineConfig()
        self.scheduler = InferenceScheduler(
            self.config.max_concurrent_inferences,
            self.config.max_queued_inferences,
            self.config.inference_queue_timeout_seconds,
        )
        self.metrics = EngineMetrics()
        self._state = EngineState.CREATED
        self._lock = Lock()

    @property
    def state(self) -> EngineState:
        with self._lock:
            return self._state

    def start(self) -> None:
        with self._lock:
            if self._state is EngineState.READY:
                return
            if self._state is not EngineState.CREATED:
                raise EngineNotReadyError(
                    f"Engine cannot start from state {self._state.value}."
                )
            self._state = EngineState.READY

    def stop(self) -> None:
        with self._lock:
            if self._state is EngineState.STOPPED:
                return
            if self._state is EngineState.STOPPING:
                return
            self._state = EngineState.STOPPING
        self.scheduler.close()
        failures: list[Exception] = []
        for provider in self.providers.values():
            try:
                provider.cancel_pending()
            except Exception as error:
                failures.append(error)
        with self._lock:
            self._state = EngineState.STOPPED
        if failures:
            raise ExceptionGroup("One or more providers failed to stop.", failures)

    def execute(
        self, capability: EngineCapability[Any, ResultT], request: Any
    ) -> ResultT:
        self._ensure_ready()
        return self.metrics.measure(
            capability.name,
            lambda: self.orchestrator.execute(capability, request),
        )

    def chat(self, provider_name: str, request: ChatRequest) -> ChatResult:
        provider = self._provider(provider_name)
        return self.metrics.measure(
            f"provider.{provider_name}.chat",
            lambda: self.scheduler.run(lambda: provider.chat(request)),
        )

    def list_models(self, provider_name: str) -> tuple[ModelInfo, ...]:
        provider = self._provider(provider_name)
        return self.metrics.measure(
            f"provider.{provider_name}.list_models", provider.list_models
        )

    def health(self, provider_name: str) -> ProviderHealth:
        provider = self._provider(provider_name)
        return self.metrics.measure(
            f"provider.{provider_name}.health", provider.health
        )

    def preload(self, provider_name: str, model: str) -> None:
        provider = self._provider(provider_name)
        self.metrics.measure(
            f"provider.{provider_name}.preload",
            lambda: self.scheduler.run(lambda: provider.preload(model)),
        )

    def status(self) -> dict[str, Any]:
        scheduler = self.scheduler.snapshot()
        return {
            "state": self.state.value,
            "providers": sorted(self.providers),
            "capabilities": list(self.orchestrator.capability_names()),
            "inference": {
                "active": scheduler.active,
                "queued": scheduler.queued,
                "capacity": scheduler.capacity,
                "closed": scheduler.closed,
            },
            "metrics": self.metrics.snapshot(),
        }

    def _provider(self, name: str) -> ModelProvider:
        self._ensure_ready()
        try:
            return self.providers[name]
        except KeyError as error:
            raise LookupError(f"Model provider is not registered: {name}.") from error

    def _ensure_ready(self) -> None:
        if self.state is not EngineState.READY:
            raise EngineNotReadyError(
                f"Engine is not ready (state: {self.state.value})."
            )
