"""ISO-639 lookup and local-only language prompting for Copernicus."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"
MAX_MESSAGE_CHARACTERS = 4_000
_TYPE_LABELS = {
    "A": "Ancient",
    "C": "Constructed",
    "E": "Extinct",
    "H": "Historical",
    "L": "Living",
    "S": "Special",
}


class CopernicusLanguageError(RuntimeError):
    pass


def _bundled_registry_path() -> Path:
    root = Path(__file__).resolve().parent
    candidates = (
        root / "src/aether_engine/world_languages_full.json",
        root / "aether_engine/world_languages_full.json",
        Path(sys.prefix)
        / "share"
        / "aether-engine"
        / "languages"
        / "world_languages_full.json",
    )
    return next((path for path in candidates if path.is_file()), candidates[0])


class CopernicusLanguageBridge:
    """Read-only ISO-639 registry lookup and local Copilot prompt support."""

    def __init__(self, json_path: str | os.PathLike[str] | None = None) -> None:
        candidate = (
            Path(json_path).expanduser()
            if json_path is not None
            else _bundled_registry_path()
        )
        self.json_path = candidate
        self.by_code: dict[str, dict[str, Any]] = {}
        self.by_name: dict[str, dict[str, Any]] = {}
        self.language_count = 0
        self._load_registry()

    def _load_registry(self) -> None:
        if self.json_path.is_symlink():
            raise CopernicusLanguageError("Language registry cannot be a symlink.")
        try:
            payload = json.loads(self.json_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CopernicusLanguageError(
                f"Language registry could not be read: {self.json_path}"
            ) from error
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != 1
            or not isinstance(payload.get("languages"), list)
        ):
            raise CopernicusLanguageError("Language registry schema is invalid.")

        for entry in payload["languages"]:
            if not isinstance(entry, dict):
                raise CopernicusLanguageError("Language registry entry is invalid.")
            code3 = entry.get("iso_639_3")
            code1 = entry.get("iso_639_1")
            name = entry.get("name")
            if not isinstance(code3, str) or len(code3) != 3:
                raise CopernicusLanguageError(
                    "Language registry ISO-639-3 identifier is invalid."
                )
            self.by_code[code3.casefold()] = entry
            if isinstance(code1, str) and code1:
                self.by_code[code1.casefold()] = entry
            if isinstance(name, str) and name.strip():
                self.by_name[name.strip().casefold()] = entry
        self.language_count = len(payload["languages"])

    def lookup_language(self, query: str) -> dict[str, Any] | None:
        if not isinstance(query, str):
            raise ValueError("Language query must be a string.")
        key = query.strip().casefold()
        if not 1 <= len(key) <= 120:
            raise ValueError("Language query must contain 1-120 characters.")
        return self.by_code.get(key) or self.by_name.get(key)

    def language_directive(self, target_language: str = "English") -> str:
        language = self.lookup_language(target_language)
        if language is None:
            raise CopernicusLanguageError(
                f"Unknown ISO-639 code or language name: {target_language}"
            )
        name = language["name"]
        code = language["iso_639_3"]
        registry_type = language.get("type") or "Unknown"
        language_type = _TYPE_LABELS.get(registry_type, registry_type)
        directive = (
            f"Respond fluently in {name} (ISO 639-3: {code}; "
            f"registry type: {language_type}). Preserve uncertainty and factual "
            "qualifications. Do not claim a literal translation for modern "
            "terminology that has no established term."
        )
        if language_type in {"Ancient", "Historical"}:
            directive += (
                " If a native-script rendering is not established, provide a "
                "marked transliteration plus clear English glosses rather than "
                "inventing a script."
            )
        return directive

    def ask_copernicus(
        self,
        user_message: str,
        target_language: str = "English",
        *,
        requester: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> str:
        if not isinstance(user_message, str) or not user_message.strip():
            raise ValueError("User message must be non-empty.")
        if len(user_message) > MAX_MESSAGE_CHARACTERS:
            raise ValueError(
                f"User message exceeds {MAX_MESSAGE_CHARACTERS} characters."
            )
        payload: dict[str, Any] = {
            "model": OLLAMA_MODEL,
            "system": (
                "You are Copernicus, a local read-only companion. You have no "
                "persistent memory, file access, or Matrix write capability. "
                + self.language_directive(target_language)
            ),
            "prompt": (
                f"[UTC_SYNC: {datetime.now(timezone.utc).isoformat()}] "
                + user_message
            ),
            "stream": False,
        }
        if requester is not None:
            try:
                result = requester(payload)
            except (OSError, TimeoutError, ValueError) as error:
                raise CopernicusLanguageError(
                    "Local Copernicus requester failed."
                ) from error
            return self._response_text(result)

        request = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (
            urllib.error.URLError,
            TimeoutError,
            UnicodeError,
            json.JSONDecodeError,
            OSError,
        ) as error:
            raise CopernicusLanguageError(
                f"Could not reach local Ollama at {OLLAMA_URL}."
            ) from error
        return self._response_text(result)

    @staticmethod
    def _response_text(result: object) -> str:
        if not isinstance(result, dict):
            raise CopernicusLanguageError("Local Copernicus response is invalid.")
        response = result.get("response")
        if not isinstance(response, str) or not response.strip():
            raise CopernicusLanguageError("Local Copernicus returned no text.")
        return response.strip()


if __name__ == "__main__":
    bridge = CopernicusLanguageBridge()
    print(f"Loaded {bridge.language_count} ISO-639 entries.")
    for code in ("en", "es", "sux", "akk", "lat"):
        language = bridge.lookup_language(code)
        print(code, language["name"] if language else "not found")
