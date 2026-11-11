from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from .base import ChatRequest, ChatResult, ModelInfo, ProviderHealth


class LocalEngine(Protocol):
    model_path: Path

    def execute_local_inference(
        self,
        *,
        prompt: str,
        reasoning_effort: str = "medium",
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]: ...

    def preload(self) -> None: ...


class LocalInferenceProviderError(RuntimeError):
    """Raised when the local GGUF engine cannot produce a typed chat result."""

    def __init__(
        self,
        message: str,
        *,
        status: str = "INFERENCE_UNAVAILABLE",
        http_status: int = 503,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.http_status = http_status


class LocalEngineProvider:
    """Adapt Aether's local GGUF engine to the typed model-provider contract."""

    def __init__(self, engine_factory: Callable[[], LocalEngine]) -> None:
        self._engine_factory = engine_factory

    def chat(self, request: ChatRequest) -> ChatResult:
        if any(message.images for message in request.messages):
            raise ValueError("The local GGUF provider does not support image input.")
        user_messages = [
            message for message in request.messages if message.role == "user"
        ]
        if len(user_messages) != 1:
            raise ValueError("The local GGUF provider requires one user message.")
        engine = self._engine_factory()
        try:
            result = engine.execute_local_inference(
                prompt=user_messages[0].content,
                reasoning_effort=request.reasoning_effort or "medium",
                max_output_tokens=request.max_output_tokens,
            )
        except RuntimeError as error:
            raise LocalInferenceProviderError(
                "Local model returned an invalid completion response.",
                status="INVALID_RESPONSE",
                http_status=502,
            ) from error
        if not isinstance(result, dict):
            raise LocalInferenceProviderError(
                "Local model returned an invalid completion response.",
                status="INVALID_RESPONSE",
                http_status=502,
            )
        if result.get("status") != "SUCCESS":
            status = result.get("status")
            output = result.get("output")
            if not isinstance(status, str) or not isinstance(output, str):
                raise LocalInferenceProviderError(
                    "Local model returned an invalid completion response.",
                    status="INVALID_RESPONSE",
                    http_status=502,
                )
            raise LocalInferenceProviderError(output, status=status)
        output = result.get("output")
        if not isinstance(output, str):
            raise LocalInferenceProviderError(
                "Local model returned an invalid completion response.",
                status="INVALID_RESPONSE",
                http_status=502,
            )
        model = result.get("model", engine.model_path.name)
        if not isinstance(model, str):
            raise LocalInferenceProviderError(
                "Local model returned an invalid model identifier.",
                status="INVALID_RESPONSE",
                http_status=502,
            )
        return ChatResult(model=model, content=output)

    def list_models(self) -> tuple[ModelInfo, ...]:
        engine = self._engine_factory()
        if not engine.model_path.is_file():
            return ()
        return (ModelInfo(engine.model_path.name, ("chat",)),)

    def health(self) -> ProviderHealth:
        models = self.list_models()
        return ProviderHealth(available=bool(models), model_count=len(models))

    def preload(self, model: str) -> None:
        engine = self._engine_factory()
        if Path(model).name != engine.model_path.name:
            raise ValueError("Requested model does not match the configured GGUF file.")
        engine.preload()

    def cancel_pending(self) -> None:
        return None
