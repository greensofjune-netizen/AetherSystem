from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}
_DEFAULT_MODEL_ID = "gpt-6-luna"
_SIMULATED_CONTENT = {
    "qed_analysis": "Topological baseline stable. Ready for 100yr sync."
}
_Transport = Callable[[dict[str, Any], str], dict[str, Any]]


class AetherLunaBridge:
    """Offline-first bridge with an optional caller-provided API transport.

    Simulation is the default and never sends requests. A live provider must
    be supplied explicitly as ``transport``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model_id: str = _DEFAULT_MODEL_ID,
        transport: _Transport | None = None,
    ) -> None:
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("Model identifier cannot be empty.")
        self.api_key = (
            api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        )
        self.model_id = model_id.strip()
        self._transport = transport
        self._logger = logging.getLogger(__name__)

    def _send_or_simulate(
        self,
        payload: dict[str, Any],
        simulated_response: dict[str, Any],
    ) -> dict[str, Any]:
        if self._transport is None:
            self._logger.info(
                "AI bridge is running in offline simulation mode; no request sent."
            )
            return simulated_response
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ValueError(
                "Authentication failed: an API key is required when using a transport."
            )

        response = self._transport(payload, self.api_key)
        if not isinstance(response, dict):
            raise ValueError("AI transport must return a response object.")
        return response

    def generate_agentic_response(
        self,
        prompt: str,
        reasoning_effort: str = "medium",
    ) -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")
        if (
            not isinstance(reasoning_effort, str)
            or reasoning_effort not in _REASONING_EFFORTS
        ):
            choices = ", ".join(sorted(_REASONING_EFFORTS))
            raise ValueError(f"Reasoning effort must be one of: {choices}.")

        payload: dict[str, Any] = {
            "model": self.model_id,
            "reasoning_effort": reasoning_effort,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the Aether Co-Pilot Historian backend subagent."
                    ),
                },
                {"role": "user", "content": prompt.strip()},
            ],
            "response_format": {"type": "json_object"},
        }
        content = json.dumps(_SIMULATED_CONTENT, ensure_ascii=False)
        simulated_response = {
            "status": "SIMULATED",
            "model": self.model_id,
            "usage": {"prompt_tokens": None, "completion_tokens": None},
            "choices": [{"message": {"content": content}}],
        }
        return self._send_or_simulate(payload, simulated_response)

    def analyze_visual_vector(
        self,
        image_base64_string: str,
        query_text: str,
    ) -> dict[str, Any]:
        """Analyze an image via an explicit transport or return a simulation."""
        if not isinstance(image_base64_string, str) or not image_base64_string.strip():
            raise ValueError("Image data cannot be empty.")
        if not isinstance(query_text, str) or not query_text.strip():
            raise ValueError("Query text cannot be empty.")

        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": query_text.strip()},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64_string}"
                            },
                        },
                    ],
                }
            ],
            "response_format": {"type": "json_object"},
        }
        return self._send_or_simulate(
            payload,
            {
                "status": "SIMULATED",
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"visual_audit": "Simulated response; '
                                'no image was analyzed."}'
                            )
                        }
                    }
                ],
            },
        )

    def process_conversational_audio(
        self,
        input_audio_base64: str,
    ) -> dict[str, Any]:
        """Process audio via an explicit transport or return a simulation."""
        if not isinstance(input_audio_base64, str) or not input_audio_base64.strip():
            raise ValueError("Audio data cannot be empty.")

        payload: dict[str, Any] = {
            "model": self.model_id,
            "modalities": ["text", "audio"],
            "audio": {"voice": "alloy", "format": "wav"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "data": input_audio_base64,
                            "format": "wav",
                        }
                    ],
                }
            ],
        }
        return self._send_or_simulate(
            payload,
            {
                "status": "SIMULATED",
                "choices": [
                    {
                        "message": {
                            "audio": {"data": "Aether_v6_audio_bytes_stub"},
                            "content": (
                                "Simulated response; no audio was processed."
                            ),
                        }
                    }
                ],
            },
        )


class LocalAirGappedEngine:
    """Local model interface that reports explicitly when inference is unavailable."""

    def __init__(
        self,
        model_filename: str = "qwen2.5-coder-7b-q4.gguf",
    ) -> None:
        self.workspace_root = Path.cwd()
        self.models_dir = self.workspace_root / "models"
        self.model_path = self.models_dir / model_filename

    def execute_local_inference(
        self,
        prompt: str,
        reasoning_effort: str = "medium",
    ) -> dict[str, Any]:
        """Report model availability; no inference backend is bundled."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")
        if (
            not isinstance(reasoning_effort, str)
            or reasoning_effort not in _REASONING_EFFORTS
        ):
            choices = ", ".join(sorted(_REASONING_EFFORTS))
            raise ValueError(f"Reasoning effort must be one of: {choices}.")

        if not self.model_path.is_file():
            logging.warning(
                "Local model weights are missing at %s; no inference was performed.",
                self.model_path,
            )
            return {
                "status": "OFFLINE_FALLBACK",
                "output": "Local model weights are missing; no inference was performed.",
            }

        return {
            "status": "INFERENCE_UNAVAILABLE",
            "model": self.model_path.name,
            "output": "Model weights are present, but no inference backend is configured.",
        }

    def process_local_vision(
        self,
        image_base64: str,
        text_query: str,
    ) -> dict[str, Any]:
        """Report that local vision is unavailable without an inference backend."""
        if not isinstance(image_base64, str) or not image_base64.strip():
            raise ValueError("Image data cannot be empty.")
        if not isinstance(text_query, str) or not text_query.strip():
            raise ValueError("Query text cannot be empty.")
        return {
            "status": "INFERENCE_UNAVAILABLE",
            "analysis": (
                "No local vision backend is configured; no image was analyzed."
            ),
        }


def main() -> int:
    bridge = AetherLunaBridge()
    result = bridge.generate_agentic_response(
        prompt="Audit the active SQLite database schema variables.",
        reasoning_effort="high",
    )
    content = result["choices"][0]["message"]["content"]
    print(f"[{result['status']}] Matrix content: {content}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
