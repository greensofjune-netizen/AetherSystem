from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ProviderMessage:
    role: Literal["system", "user", "assistant"]
    content: str
    images: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant"}:
            raise ValueError("Model message role is not supported.")
        if not isinstance(self.content, str):
            raise TypeError("Model message content must be text.")
        if any(not isinstance(image, str) or not image for image in self.images):
            raise ValueError("Model message images must be non-empty strings.")


@dataclass(frozen=True)
class ChatTool:
    name: str
    description: str
    parameters: dict[str, Any]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not self.name.strip()
            or not isinstance(self.description, str)
            or not self.description.strip()
        ):
            raise ValueError("Chat tools require a name and description.")
        if not isinstance(self.parameters, dict):
            raise TypeError("Chat tool parameters must be a JSON object schema.")


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ChatRequest:
    model: str
    messages: tuple[ProviderMessage, ...]
    temperature: float = 0.2
    max_output_tokens: int = 2048
    reasoning_effort: Literal[
        "none", "low", "medium", "high", "xhigh", "max"
    ] | None = None
    tools: tuple[ChatTool, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("Model name cannot be empty.")
        if not self.messages:
            raise ValueError("At least one model message is required.")
        if not isfinite(self.temperature) or not 0 <= self.temperature <= 2:
            raise ValueError("Model temperature must be between 0 and 2.")
        if (
            type(self.max_output_tokens) is not int
            or not 1 <= self.max_output_tokens <= 8192
        ):
            raise ValueError("Model output token limit must be between 1 and 8192.")
        if self.reasoning_effort not in {
            None,
            "none",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        }:
            raise ValueError("Model reasoning effort is not supported.")
        if len({tool.name for tool in self.tools}) != len(self.tools):
            raise ValueError("Chat tool names must be unique.")


@dataclass(frozen=True)
class ChatResult:
    model: str
    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class ModelInfo:
    name: str
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderHealth:
    available: bool
    model_count: int


class ModelProvider(Protocol):
    """Typed model operations supported by an Aether provider."""

    def chat(self, request: ChatRequest) -> ChatResult: ...

    def list_models(self) -> tuple[ModelInfo, ...]: ...

    def health(self) -> ProviderHealth: ...

    def preload(self, model: str) -> None: ...

    def cancel_pending(self) -> None: ...
