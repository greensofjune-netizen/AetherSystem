import json
from pathlib import Path

import pytest

from build_world_languages_json import RegistryBuildError, build_registry
from copernicus_language_bridge import (
    CopernicusLanguageBridge,
    CopernicusLanguageError,
)


def test_bridge_loads_complete_registry_and_resolves_codes_and_names():
    bridge = CopernicusLanguageBridge()

    assert bridge.language_count == 7_928
    assert bridge.lookup_language("en")["name"] == "English"
    assert bridge.lookup_language("es")["iso_639_3"] == "spa"
    assert bridge.lookup_language("Sumerian")["iso_639_3"] == "sux"


def test_bridge_builds_read_only_language_directive():
    bridge = CopernicusLanguageBridge()

    english = bridge.language_directive("English")
    sumerian = bridge.language_directive("sux")

    assert "ISO 639-3: eng" in english
    assert "registry type: Living" in english
    assert "Historical" in sumerian
    assert "marked transliteration" in sumerian
    assert "no persistent memory" in bridge.ask_copernicus(
        "hello",
        "en",
        requester=lambda payload: {
            "response": payload["system"],
        },
    )
    with pytest.raises(CopernicusLanguageError, match="Unknown"):
        bridge.language_directive("not-a-language")


def test_bridge_bounds_request_and_rejects_invalid_registry(tmp_path):
    bridge = CopernicusLanguageBridge()

    with pytest.raises(ValueError, match="exceeds"):
        bridge.ask_copernicus("x" * 4_001)

    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"schema_version": 9, "languages": []}))
    with pytest.raises(CopernicusLanguageError, match="schema"):
        CopernicusLanguageBridge(invalid)


def test_generated_registry_manifest_matches_packaged_file():
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "aether_engine"
        / "world_languages_full.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["language_count"] == len(payload["languages"]) == 7_928
    assert payload["source"].startswith("https://iso639-3.sil.org/")
    assert len(payload["source_sha256"]) == 64


def test_registry_builder_rejects_duplicate_iso_codes():
    header = (
        "Id\tPart2b\tPart2t\tPart1\tScope\tLanguage_Type\tRef_Name\tComment\n"
    )
    duplicate = "eng\teng\teng\ten\tI\tL\tEnglish\t\neng\teng\teng\ten\tI\tL\tEnglish\t\n"

    with pytest.raises(RegistryBuildError, match="Duplicate"):
        build_registry((header + duplicate).encode())
