import json
from pathlib import Path

import pytest

from aether_engine.updater import (
    ConfigurationReloadAnomalyError,
    EngineUpdater,
)


def test_reload_system_manifest_loads_json_configuration(tmp_path: Path) -> None:
    config_path = tmp_path / "manifest.json"
    expected = {"engine": {"enabled": True}, "workers": 3}
    config_path.write_text(json.dumps(expected))

    updater = EngineUpdater(config_path)

    assert updater.config_path == config_path
    assert updater.reload_system_manifest() == expected


def test_reload_system_manifest_raises_for_missing_file(tmp_path: Path) -> None:
    updater = EngineUpdater(tmp_path / "missing.json")

    with pytest.raises(
        ConfigurationReloadAnomalyError,
        match="Target update manifest missing",
    ):
        updater.reload_system_manifest()


def test_reload_system_manifest_raises_for_malformed_json(tmp_path: Path) -> None:
    config_path = tmp_path / "manifest.json"
    config_path.write_text("{invalid json")
    updater = EngineUpdater(config_path)

    with pytest.raises(
        ConfigurationReloadAnomalyError,
        match="Malformed configuration syntax detected",
    ):
        updater.reload_system_manifest()
