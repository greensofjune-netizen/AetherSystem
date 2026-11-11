"""Shared local Ollama model startup behavior."""

from __future__ import annotations

import http.client
import json

DEFAULT_LOCAL_MODEL = "qwen3.5:4b"
MODEL_KEEP_ALIVE = "10m"


class LocalModelUnavailableError(RuntimeError):
    """Raised when the requested, already-installed local model cannot be loaded."""


def preload_local_model(model: str, *, timeout: float = 300) -> None:
    """Load an installed Ollama model without pulling or generating a reply."""
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Local model name cannot be empty.")
    if timeout <= 0:
        raise ValueError("Model preload timeout must be greater than zero.")

    connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=timeout)
    try:
        connection.request(
            "POST",
            "/api/generate",
            body=json.dumps(
                {
                    "model": model.strip(),
                    "prompt": "",
                    "stream": False,
                    "keep_alive": MODEL_KEEP_ALIVE,
                    "options": {"num_predict": 0},
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        body = response.read(1_048_577)
        if response.status != 200:
            detail = ""
            if len(body) <= 1_048_576:
                try:
                    result = json.loads(body)
                except json.JSONDecodeError:
                    pass
                else:
                    if isinstance(result, dict) and isinstance(
                        result.get("error"), str
                    ):
                        detail = f": {result['error'][:240]}"
            raise LocalModelUnavailableError(
                f"Ollama returned HTTP {response.status} while loading the model"
                f"{detail}."
            )
        if len(body) > 1_048_576:
            raise LocalModelUnavailableError(
                "Ollama model preload response exceeded the size limit."
            )
        result = json.loads(body)
        if not isinstance(result, dict) or result.get("model") != model.strip():
            raise LocalModelUnavailableError(
                "Ollama returned an invalid model preload response."
            )
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as error:
        raise LocalModelUnavailableError(
            "Local Ollama is unavailable or could not load the installed model."
        ) from error
    finally:
        connection.close()
