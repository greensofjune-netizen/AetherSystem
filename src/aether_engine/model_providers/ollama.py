from __future__ import annotations

import http.client
import json
import logging
import socket
from contextlib import contextmanager
from contextvars import ContextVar
from math import isfinite
from threading import Event, Lock
from typing import Any, Callable, Iterator

from .base import ChatRequest, ChatResult, ModelInfo, ProviderHealth, ToolCall

LOGGER = logging.getLogger(__name__)
_CANCELLATION: ContextVar[Event | None] = ContextVar(
    "ollama_cancellation", default=None
)


class OllamaProviderError(RuntimeError):
    """Raised when the local Ollama HTTP runtime cannot complete a request."""


class OllamaProvider:
    """HTTP adapter for an Ollama runtime bound to the local machine."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 11434,
        timeout: float = 120,
        preload_timeout: float = 300,
    ) -> None:
        if (
            not isfinite(timeout)
            or not isfinite(preload_timeout)
            or timeout <= 0
            or preload_timeout <= 0
        ):
            raise ValueError("Ollama timeouts must be greater than zero.")
        self.host = host
        self.port = port
        self.timeout = timeout
        self.preload_timeout = preload_timeout
        self.connection_factory: Callable[..., http.client.HTTPConnection] = (
            http.client.HTTPConnection
        )
        self._connections: dict[http.client.HTTPConnection, socket.socket | None] = {}
        self._connections_lock = Lock()
        self._request_events: dict[http.client.HTTPConnection, Event | None] = {}

    @contextmanager
    def cancellable(self, event: Event) -> Iterator[None]:
        token = _CANCELLATION.set(event)
        try:
            yield
        finally:
            _CANCELLATION.reset(token)

    def cancel_request(self, event: Event) -> None:
        event.set()
        with self._connections_lock:
            connections = tuple(
                (connection, self._connections[connection])
                for connection, owner in self._request_events.items()
                if owner is event
            )
        self._close_connections(connections)

    def request(
        self, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        cancellation = _CANCELLATION.get()
        if cancellation is not None and cancellation.is_set():
            raise OllamaProviderError("Local inference was stopped.")
        connection = self.connection_factory(self.host, self.port, timeout=self.timeout)
        with self._connections_lock:
            self._connections[connection] = None
            self._request_events[connection] = cancellation
        try:
            if cancellation is not None and cancellation.is_set():
                raise OllamaProviderError("Local inference was stopped.")
            connection.request(
                "GET" if payload is None else "POST",
                path,
                body=None if payload is None else json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            with self._connections_lock:
                self._connections[connection] = connection.sock
            if cancellation is not None and cancellation.is_set():
                raise OllamaProviderError("Local inference was stopped.")
            response = connection.getresponse()
            body = response.read(2_097_153)
            if response.status != 200:
                detail = ""
                if len(body) <= 2_097_152:
                    try:
                        error_body = json.loads(body)
                    except json.JSONDecodeError:
                        LOGGER.warning("Ollama returned a non-JSON error response.")
                    else:
                        if isinstance(error_body, dict) and isinstance(
                            error_body.get("error"), str
                        ):
                            detail = f" {error_body['error'][:300]}"
                raise OllamaProviderError(
                    f"Local Ollama returned HTTP {response.status}. "
                    f"Check that Ollama and the selected model are available.{detail}"
                )
            if len(body) > 2_097_152:
                raise OllamaProviderError(
                    "Local Ollama response exceeds the 2 MiB limit."
                )
            result = json.loads(body)
            if not isinstance(result, dict):
                raise OllamaProviderError("Local Ollama returned an invalid response.")
            return result
        except (
            OSError,
            http.client.HTTPException,
            json.JSONDecodeError,
            ValueError,
        ) as error:
            raise OllamaProviderError(
                "Local Ollama is unavailable or returned invalid data. "
                "Start Ollama and retry."
            ) from error
        finally:
            with self._connections_lock:
                self._connections.pop(connection, None)
                self._request_events.pop(connection, None)
            connection.close()

    def chat(self, request: ChatRequest) -> ChatResult:
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            item: dict[str, Any] = {
                "role": message.role,
                "content": message.content,
            }
            if message.images:
                item["images"] = list(message.images)
            messages.append(item)
        payload: dict[str, Any] = {
            "model": request.model.strip(),
            "stream": False,
            "messages": messages,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_output_tokens,
            },
        }
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in request.tools
            ]
        if request.reasoning_effort == "none":
            payload["think"] = False
        result = self.request("/api/chat", payload)
        reply = result.get("message")
        if (
            not isinstance(reply, dict)
            or not isinstance(reply.get("content", ""), str)
        ):
            raise OllamaProviderError("Local Ollama returned an invalid chat response.")
        content = reply.get("content", "")
        tool_calls = self._tool_calls(reply.get("tool_calls", []))
        if not content.strip() and not tool_calls:
            raise OllamaProviderError("Local Ollama returned no response text.")
        response_model = result.get("model", request.model)
        if not isinstance(response_model, str) or not response_model.strip():
            raise OllamaProviderError("Local Ollama returned an invalid model name.")
        return ChatResult(
            model=response_model,
            content=content,
            prompt_tokens=self._optional_count(result.get("prompt_eval_count")),
            completion_tokens=self._optional_count(result.get("eval_count")),
            tool_calls=tool_calls,
        )

    @staticmethod
    def _tool_calls(value: Any) -> tuple[ToolCall, ...]:
        if not isinstance(value, list):
            raise OllamaProviderError("Local Ollama returned invalid tool calls.")
        calls: list[ToolCall] = []
        for item in value:
            function = item.get("function") if isinstance(item, dict) else None
            if not isinstance(function, dict):
                raise OllamaProviderError("Local Ollama returned an invalid tool call.")
            name = function.get("name")
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError as error:
                    raise OllamaProviderError(
                        "Local Ollama returned invalid tool arguments."
                    ) from error
            if not isinstance(name, str) or not name.strip() or not isinstance(arguments, dict):
                raise OllamaProviderError("Local Ollama returned an invalid tool call.")
            calls.append(ToolCall(name=name, arguments=arguments))
        return tuple(calls)

    def list_models(self) -> tuple[ModelInfo, ...]:
        result = self.request("/api/tags")
        values = result.get("models")
        if not isinstance(values, list):
            raise OllamaProviderError("Local Ollama returned an invalid model list.")
        models: list[ModelInfo] = []
        for value in values:
            if (
                not isinstance(value, dict)
                or not isinstance(value.get("name"), str)
                or not value["name"].strip()
            ):
                raise OllamaProviderError(
                    "Local Ollama returned an invalid model list."
                )
            capabilities = value.get("capabilities", [])
            if not isinstance(capabilities, list) or any(
                not isinstance(capability, str) for capability in capabilities
            ):
                raise OllamaProviderError(
                    "Local Ollama returned invalid model capabilities."
                )
            models.append(ModelInfo(value["name"], tuple(dict.fromkeys(capabilities))))
        return tuple(models)

    def health(self) -> ProviderHealth:
        return ProviderHealth(available=True, model_count=len(self.list_models()))

    def preload(self, model: str) -> None:
        from ..local_ai_runtime import preload_local_model

        preload_local_model(model, timeout=self.preload_timeout)

    @staticmethod
    def _optional_count(value: Any) -> int | None:
        return value if type(value) is int and value >= 0 else None

    def cancel_pending(self) -> None:
        with self._connections_lock:
            connections = tuple(self._connections.items())
        self._close_connections(connections)

    @staticmethod
    def _close_connections(
        connections: tuple[
            tuple[http.client.HTTPConnection, socket.socket | None], ...
        ],
    ) -> None:
        for connection, sock in connections:
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    LOGGER.debug("Ollama socket already closed during shutdown.")
            connection.close()
