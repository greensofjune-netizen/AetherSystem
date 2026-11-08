from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


@pytest.fixture
def matrix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module_path = Path(__file__).resolve().parents[1] / "aether_master_matrix.py"
    spec = importlib.util.spec_from_file_location("aether_master_matrix_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "LOG_FILE", tmp_path / "historian.json")
    return module


def test_telemetry_writer_appends_json_entries(matrix):
    matrix.log_telemetry_event(1, 0.75, 120.12345, 50.56789, "EQUILIBRIUM")
    matrix.log_telemetry_event(2, 0.05, 140.0, 1_000_000.0, "BOUNCE_ACTIVE")

    entries = json.loads(matrix.LOG_FILE.read_text(encoding="utf-8"))
    assert len(entries) == 2
    assert entries[0]["epoch"] == 1
    assert entries[0]["scale_factor"] == 0.75
    assert entries[0]["entanglement_entropy_nats"] == 120.1235
    assert entries[1]["system_status"] == "BOUNCE_ACTIVE"
    assert entries[0]["timestamp"]


def test_telemetry_writer_reports_corrupt_existing_data(matrix):
    matrix.LOG_FILE.write_text("{invalid", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Could not read telemetry vault"):
        matrix.log_telemetry_event(1, 0.75, 120.0, 42.0, "EQUILIBRIUM")

    assert matrix.LOG_FILE.read_text(encoding="utf-8") == "{invalid"


def test_test_drive_records_all_steps_and_bounce_status(matrix):
    asyncio.run(
        matrix.run_master_matrix_test_drive(steps=3, interval_seconds=0)
    )

    entries = json.loads(matrix.LOG_FILE.read_text(encoding="utf-8"))
    assert len(entries) == 3
    assert [entry["epoch"] for entry in entries] == [1, 2, 3]
    assert entries[0]["system_status"] == "EQUILIBRIUM"
    assert entries[-1]["system_status"] == "BOUNCE_ACTIVE"


@pytest.mark.parametrize(("steps", "interval"), [(0, 0), (1, -0.1)])
def test_test_drive_rejects_invalid_parameters(matrix, steps, interval):
    with pytest.raises(ValueError):
        asyncio.run(
            matrix.run_master_matrix_test_drive(
                steps=steps,
                interval_seconds=interval,
            )
        )


def test_dashboard_serves_latest_metrics_and_escapes_status(matrix):
    matrix.log_telemetry_event(
        1,
        0.5,
        123.4567,
        789.1234,
        "<script>alert(1)</script>",
    )
    server = matrix.LocalThreadingHTTPServer(
        ("127.0.0.1", 0),
        matrix.HistorianLiveServer,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/") as response:
            page = response.read().decode("utf-8")
            assert response.status == 200
            assert "frame-src 'self'" in response.headers[
                "Content-Security-Policy"
            ]
            assert 'src="/weather"' in page
            assert 'src="/stargazer"' not in page
            assert 'title="Copernicus and Observatory Shell"' in page
            assert 'loading="lazy"' in page
            assert "123.4567" in page
            assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
            assert "<script>alert(1)</script>" not in page
            assert "chatForm" not in page
            assert "AetherSystem // Copernicus" in page
            assert "Personal companion | Matrix-themed, no data link" in page
            assert "AetherSystem // Copernicus" in page
            assert "[HISTORIAN MASTER]" not in page
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    ("path", "content_type", "marker"),
    [
        ("/weather", "text/html", b"Copernicus &amp; Observatory"),
        ("/weather.css", "text/css", b"prefers-color-scheme: dark"),
        ("/weather.js", "text/javascript", b"cloud_cover"),
        ("/copernicus.js", "text/javascript", b"/api/chat"),
        ("/stargazer", "text/html", b"ILLUSTRATIVE SKY"),
        ("/stargazer.css", "text/css", b"--star-glow"),
        ("/stargazer.js", "text/javascript", b"CONSTELLATIONS"),
    ],
)
def test_frontend_assets_are_served_without_reading_private_telemetry(
    matrix, path, content_type, marker
):
    matrix.LOG_FILE.write_text("{invalid", encoding="utf-8")
    server = matrix.LocalThreadingHTTPServer(
        ("127.0.0.1", 0), matrix.HistorianLiveServer
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}{path}") as response:
            assert response.status == 200
            assert response.headers["Content-Type"].startswith(content_type)
            assert response.headers["Cache-Control"] == "no-cache"
            policy = response.headers["Content-Security-Policy"]
            if not path.startswith("/stargazer"):
                assert "connect-src 'self' https://api.open-meteo.com https://geocoding-api.open-meteo.com" in policy
            else:
                assert "connect-src 'self'" in policy
            assert "frame-ancestors 'self'" in policy
            content = response.read()
            assert marker in content
            if path == "/weather":
                assert "frame-src 'self'" in policy
                assert b'role="tablist"' in content
                assert b'data-copernicus="true"' in content
                assert b'id="copernicus-tab"' in content
                assert b'id="cloud-cover"' in content
                assert b'id="history-form"' not in content
                assert b'<script src="/copernicus.js" defer></script>' in content
                assert b'aria-controls="weather-panel"' in content
                assert b'aria-controls="stargazer-panel"' in content
                assert b'data-src="/stargazer"' in content
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_copernicus_chat_uses_only_the_current_message_and_optional_weather(matrix, monkeypatch):
    observed = {}

    def query_brain(self, prompt, *, system=None):
        observed["prompt"] = prompt
        observed["system"] = system
        return "A local reply."

    monkeypatch.setattr(matrix.AetherHistorian, "query_brain", query_brain)
    monkeypatch.setattr(matrix, "COPERNICUS_MODEL", "qwen2.5-coder")
    server = matrix.LocalThreadingHTTPServer(
        ("127.0.0.1", 0), matrix.HistorianLiveServer
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with urlopen(f"{base_url}/api/chat/status") as response:
            assert json.loads(response.read()) == {
                "enabled": True,
                "model": "qwen2.5-coder",
            }
        with urlopen(f"{base_url}/api/clock") as response:
            assert "+00:00" in json.loads(response.read())["utc"]
        request = Request(
            f"{base_url}/api/chat",
            data=json.dumps({"message": "Hello"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            result = json.loads(response.read())
        assert result["model"] == "qwen2.5-coder"
        assert result["response"] == "A local reply."
        assert result["request_utc"] <= result["response_utc"]
        assert observed["prompt"] == "Hello"
        assert "no persistent profile or memory" in observed["system"]

        weather_context = {
            "city": "Upland, CA",
            "cloud_cover_percent": 42,
            "observed_at": "2026-11-07T16:00",
            "timezone": "America/Los_Angeles",
            "freshness": "stale",
        }
        request = Request(
            f"{base_url}/api/chat",
            data=json.dumps(
                {"message": "What is the cloud cover?", "weather_context": weather_context}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            assert response.status == 200
        assert observed["prompt"] == "What is the cloud cover?"
        assert "Upland, CA" in observed["system"]
        assert "42" in observed["system"]
        assert "stale" in observed["system"]
        assert "not an affiliation or endorsement" in observed["system"]

        invalid_weather = {**weather_context, "cloud_cover_percent": 101}
        request = Request(
            f"{base_url}/api/chat",
            data=json.dumps(
                {"message": "Hello", "weather_context": invalid_weather}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request)
        assert error.value.code == 422

        invalid = Request(
            f"{base_url}/api/chat",
            data=json.dumps({"message": " ", "history": ["not relayed"]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(invalid)
        assert error.value.code == 422

        cross_origin = Request(
            f"{base_url}/api/chat",
            data=json.dumps({"message": "Hello"}).encode(),
            headers={
                "Content-Type": "application/json",
                "Origin": "https://evil.example",
            },
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(cross_origin)
        assert error.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_reports_corrupt_telemetry_instead_of_falling_back(matrix):
    matrix.LOG_FILE.write_text("{invalid", encoding="utf-8")
    server = matrix.LocalThreadingHTTPServer(
        ("127.0.0.1", 0),
        matrix.HistorianLiveServer,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(HTTPError) as error:
            urlopen(f"http://127.0.0.1:{server.server_port}/")
        assert error.value.code == 500
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    "path",
    [
        "/not-found",
        "/aether_master_matrix.py",
        "/historian_telemetry_vault.json",
        "/weather/../aether_master_matrix.py",
    ],
)
def test_dashboard_rejects_unknown_paths(matrix, path):
    server = matrix.LocalThreadingHTTPServer(
        ("127.0.0.1", 0),
        matrix.HistorianLiveServer,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(HTTPError) as error:
            urlopen(f"http://127.0.0.1:{server.server_port}{path}")
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
