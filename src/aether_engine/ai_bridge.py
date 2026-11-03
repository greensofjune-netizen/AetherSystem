from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any

_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}
_DEFAULT_MODEL_ID = "gpt-6-luna"
_SIMULATED_CONTENT = {
    "qed_analysis": "Topological baseline stable. Ready for 100yr sync."
}
_Transport = Callable[[dict[str, Any], str], dict[str, Any]]


class AetherLunaBridge:
    """Offline-first bridge with an optional caller-provided API transport.

    The default mode is a deterministic simulation and never sends network
    requests. A live provider must be supplied explicitly as ``transport``.
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

        if self._transport is None:
            self._logger.info(
                "AI bridge is running in offline simulation mode; no request sent."
            )
            content = json.dumps(_SIMULATED_CONTENT, ensure_ascii=False)
            return {
                "status": "SIMULATED",
                "model": self.model_id,
                "usage": {"prompt_tokens": None, "completion_tokens": None},
                "choices": [{"message": {"content": content}}],
            }

        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ValueError(
                "Authentication failed: an API key is required when using a transport."
            )

        response = self._transport(payload, self.api_key)
        if not isinstance(response, dict):
            raise ValueError("AI transport must return a response object.")
        return response


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
