from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aether_engine.historian_behavior import (
    AetherHistorian,
    OllamaConnectionError,
    main,
    run_llm_pipeline,
    search_for_model_paths,
)


def test_scanner_reports_locations_without_source_contents(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "settings.toml").write_text(
        'model_path = "/private/model.gguf"\n', encoding="utf-8"
    )
    (tmp_path / ".env").write_text(
        "API_TOKEN=do-not-print-this\n", encoding="utf-8"
    )

    matches = search_for_model_paths(tmp_path)
    output = capsys.readouterr().out

    assert matches == [(Path("settings.toml"), 1)]
    assert "settings.toml:1" in output
    assert "/private/model.gguf" not in output
    assert "do-not-print-this" not in output


def test_scanner_skips_excluded_directories_and_symlinked_files(
    tmp_path: Path,
) -> None:
    excluded = tmp_path / ".venv"
    excluded.mkdir()
    (excluded / "settings.py").write_text("model_path = 'hidden'\n", encoding="utf-8")
    target = tmp_path / "target.toml"
    target.write_text("model_file = 'visible'\n", encoding="utf-8")
    (tmp_path / "linked.toml").symlink_to(target)

    matches = search_for_model_paths(tmp_path)

    assert matches == [(Path("target.toml"), 1)]


def test_scanner_rejects_non_directory_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a directory"):
        search_for_model_paths(tmp_path / "missing")


def test_training_requires_valid_bounded_iteration_count() -> None:
    with pytest.raises(ValueError, match="between 1 and 1000"):
        run_llm_pipeline(iterations=1_001)


def test_query_brain_sends_local_non_streaming_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        status = 200
        reason = "OK"

        def read(self, size: int) -> bytes:
            captured["read_size"] = size
            return b'{"response":"  Local answer  "}'

    class FakeConnection:
        def __init__(self, host: str, port: int, *, timeout: float) -> None:
            captured["connection"] = (host, port, timeout)

        def request(
            self,
            method: str,
            endpoint: str,
            body: str,
            headers: dict[str, str],
        ) -> None:
            captured["request"] = (method, endpoint, json.loads(body), headers)

        def getresponse(self) -> FakeResponse:
            return FakeResponse()

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(
        "aether_engine.historian_behavior.http.client.HTTPConnection",
        FakeConnection,
    )

    result = AetherHistorian().query_brain("  Check the archive.  ")

    assert result == "Local answer"
    assert captured["connection"] == ("localhost", 11434, 300)
    assert captured["request"] == (
        "POST",
        "/api/generate",
        {
            "model": "aethersystem-core",
            "prompt": "Check the archive.",
            "stream": False,
            "options": {"temperature": 0.2},
        },
        {"Content-Type": "application/json"},
    )
    assert captured["read_size"] == 1_048_577
    assert captured["closed"] is True
    AetherHistorian().query_brain("Hello", system="Independent Historian.")
    request = captured["request"]
    assert isinstance(request, tuple)
    assert request[2]["system"] == "Independent Historian."


def test_query_brain_reports_http_and_invalid_response_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status = 503
        reason = "Unavailable"

        def read(self, _size: int) -> bytes:
            raise AssertionError("Error bodies should not be read.")

    class FakeConnection:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def request(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def getresponse(self) -> FakeResponse:
            return FakeResponse()

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "aether_engine.historian_behavior.http.client.HTTPConnection",
        FakeConnection,
    )

    with pytest.raises(OllamaConnectionError, match="HTTP 503"):
        AetherHistorian().query_brain("Check the archive.")

    class InvalidJsonResponse(FakeResponse):
        status = 200

        def read(self, _size: int) -> bytes:
            return b"not-json"

    class InvalidJsonConnection(FakeConnection):
        def getresponse(self) -> InvalidJsonResponse:
            return InvalidJsonResponse()

    monkeypatch.setattr(
        "aether_engine.historian_behavior.http.client.HTTPConnection",
        InvalidJsonConnection,
    )
    with pytest.raises(OllamaConnectionError, match="invalid JSON"):
        AetherHistorian().query_brain("Check the archive.")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"host": "ollama.example.com"}, "loopback"),
        ({"port": 0}, "port"),
        ({"model": " "}, "model name"),
    ],
)
def test_historian_only_accepts_valid_local_configuration(
    kwargs: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        AetherHistorian(**kwargs)


def test_telemetry_marks_supplied_historical_claims_unverified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    historian = AetherHistorian()
    captured: dict[str, str] = {}

    def fake_query(prompt: str) -> str:
        captured["prompt"] = prompt
        return "Review complete."

    monkeypatch.setattr(historian, "query_brain", fake_query)

    assert historian.run_historian_telemetry() == "Review complete."
    assert "unverified claim" in captured["prompt"]
    assert "REQUIRES_VERIFICATION" in captured["prompt"]


def test_main_can_run_historian_telemetry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeHistorian:
        def __init__(self, **options: Any) -> None:
            assert options == {
                "host": "127.0.0.1",
                "port": 11434,
                "model": "aethersystem-core",
                "timeout": 300,
            }

        def run_historian_telemetry(self) -> str:
            return "Local review result."

    monkeypatch.setattr(
        "aether_engine.historian_behavior.search_for_model_paths",
        lambda _root: [],
    )
    monkeypatch.setattr(
        "aether_engine.historian_behavior.AetherHistorian",
        FakeHistorian,
    )

    result = main(
        [
            "--scan-root",
            str(tmp_path),
            "--telemetry",
            "--ollama-host",
            "127.0.0.1",
        ]
    )

    assert result == 0
    assert "Local review result." in capsys.readouterr().out


def test_scanner_lists_gguf_weights_from_local_and_external_directories(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "project"
    (root / "models").mkdir(parents=True)
    (root / "models" / "local.gguf").write_bytes(b"1234")
    external = tmp_path / "volume" / "models"
    external.mkdir(parents=True)
    (external / "remote.gguf").write_bytes(b"12")
    (external / "notes.txt").write_text("ignore", encoding="utf-8")

    search_for_model_paths(root, external_model_dirs=[external, tmp_path / "gone"])
    output = capsys.readouterr().out

    assert "local.gguf (4 bytes)" in output
    assert "remote.gguf (2 bytes)" in output
    assert "notes.txt" not in output


def test_scanner_reads_external_directories_from_environment(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external = tmp_path / "drive"
    external.mkdir()
    (external / "env.gguf").write_bytes(b"x")
    monkeypatch.setenv("AETHER_EXTERNAL_MODEL_DIRS", str(external))

    search_for_model_paths(tmp_path)

    assert "env.gguf (1 bytes)" in capsys.readouterr().out


def test_scanner_defaults_include_atlas_drive_without_duplicates(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    atlas = tmp_path / "Atlas"
    (atlas / "models").mkdir(parents=True)
    (atlas / "models" / "atlas.gguf").write_bytes(b"abc")
    monkeypatch.setattr(
        "aether_engine.historian_behavior._DEFAULT_EXTERNAL_MODEL_DIRS", (atlas,)
    )
    monkeypatch.setenv("AETHER_EXTERNAL_MODEL_DIRS", str(atlas / "models"))

    search_for_model_paths(tmp_path)
    output = capsys.readouterr().out

    assert output.count("atlas.gguf") == 1
