from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.util
import json
import re
import shutil
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from aether_engine.database import AetherStore


@pytest.fixture
def matrix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module_path = Path(__file__).resolve().parents[1] / "aether_master_matrix.py"
    spec = importlib.util.spec_from_file_location(
        "aether_master_matrix_test", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "LOG_FILE", tmp_path / "historian.json")
    monkeypatch.setenv(
        "AETHER_MATRIX_EVIDENCE_LEDGER_FILE",
        str(tmp_path / "matrix-evidence-ledger.json"),
    )
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
    assert entries[0]["timestamp"].endswith("+00:00")


def test_telemetry_writer_reports_corrupt_existing_data(matrix):
    matrix.LOG_FILE.write_text("{invalid", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Could not read telemetry vault"):
        matrix.log_telemetry_event(1, 0.75, 120.0, 42.0, "EQUILIBRIUM")

    assert matrix.LOG_FILE.read_text(encoding="utf-8") == "{invalid"


def test_test_drive_records_all_steps_and_bounce_status(matrix):
    asyncio.run(matrix.run_master_matrix_test_drive(steps=3, interval_seconds=0))

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


@pytest.mark.parametrize(
    ("steps", "interval"),
    [
        (True, 0),
        (0, 0),
        (1001, 0),
        (1, float("nan")),
        (1, float("inf")),
        (1, True),
        (1, 60.1),
    ],
)
def test_test_drive_rejects_non_finite_or_non_numeric_parameters(
    matrix, steps, interval
):
    with pytest.raises(ValueError):
        asyncio.run(
            matrix.run_master_matrix_test_drive(
                steps=steps,
                interval_seconds=interval,
            )
        )


def test_telemetry_writer_rejects_invalid_values(matrix):
    with pytest.raises(ValueError, match="epoch"):
        matrix.log_telemetry_event(True, 0.75, 120.0, 50.0, "OK")
    with pytest.raises(ValueError, match="entropy"):
        matrix.log_telemetry_event(1, 0.75, float("nan"), 50.0, "OK")
    with pytest.raises(ValueError, match="status"):
        matrix.log_telemetry_event(1, 0.75, 120.0, 50.0, "")
    assert not matrix.LOG_FILE.exists()


def test_main_starts_dashboard_without_running_simulation(matrix, monkeypatch):
    calls = []
    monkeypatch.setattr(matrix, "run_web_server", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(
        matrix,
        "run_master_matrix_test_drive",
        lambda **_kwargs: pytest.fail("normal dashboard launch ran a test drive"),
    )

    assert matrix.main(["--port", "8123"]) == 0
    assert calls == [{"port": 8123}]


def test_main_rejects_invalid_port_from_environment(matrix, monkeypatch):
    monkeypatch.setenv("AETHER_PORT", "not-a-port")

    with pytest.raises(SystemExit) as error:
        matrix.main([])

    assert error.value.code == 2


def test_main_runs_test_drive_only_when_requested(matrix, monkeypatch):
    calls = []

    async def drive(*, steps, interval_seconds):
        calls.append((steps, interval_seconds))

    monkeypatch.setattr(matrix, "run_master_matrix_test_drive", drive)
    monkeypatch.setattr(
        matrix,
        "run_web_server",
        lambda **_kwargs: pytest.fail("test-drive mode started dashboard"),
    )

    assert matrix.main(["--test-drive", "--steps", "4", "--interval", "0"]) == 0
    assert calls == [(4, 0)]


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
            policy = response.headers["Content-Security-Policy"]
            inline_script = re.search(r"<script>(.*?)</script>", page, re.DOTALL)
            assert response.status == 200
            assert "frame-src 'self'" in policy
            assert "connect-src 'self'" in policy
            assert "frame-ancestors 'none'" in policy
            assert "object-src 'none'" in policy
            assert "script-src 'unsafe-inline'" not in policy
            assert inline_script is not None
            script_hash = base64.b64encode(
                hashlib.sha256(inline_script.group(1).encode("utf-8")).digest()
            ).decode("ascii")
            assert f"script-src 'sha256-{script_hash}'" in policy
            assert response.headers["X-Frame-Options"] == "DENY"
            assert response.headers["Referrer-Policy"] == "no-referrer"
            assert 'src="/weather"' in page
            assert '<a class="skip-link" href="#main-content">' in page
            assert 'id="motion-toggle"' in page
            assert "color-scheme:dark" in page
            assert "transition:all" not in page
            assert "document.hidden || artsTelemetryInFlight" in page
            assert 'class="observatory-frame"' in page
            assert 'src="/stargazer"' not in page
            assert 'title="Copernicus and Observatory Shell"' in page
            assert 'loading="lazy"' in page
            assert "visibilitychange" in page
            assert "123.4567" in page
            assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
            assert "<script>alert(1)</script>" not in page
            assert "chatForm" not in page
            assert "<title>AetherSystem | Local Operations Dashboard</title>" in page
            assert "<h1>AetherSystem</h1>" in page
            assert "Local operations dashboard | simulated metrics" in page
            assert '<span class="badge-label">Simulation</span>' in page
            assert "AetherSystem // Copernicus" not in page
            assert "[HISTORIAN MASTER]" not in page
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_shows_latest_matrix_arts_telemetry(matrix, tmp_path, monkeypatch):
    database = tmp_path / "aether.sqlite3"
    monkeypatch.setenv("AETHER_DATABASE_PATH", str(database))
    envelope = {
        "protocol_version": "1.0.0",
        "source_lang": "python",
        "node": "MATRIX",
        "event": "ARTS_STAGE_CUE_REQUESTED",
        "timestamp": 1_800_000_000,
        "payload": {
            "cue": "/theatre/act1/spotlight",
            "value": "WARM_AMBER_85",
            "status": "REQUIRES_OPERATOR_APPROVAL",
            "actuated": False,
        },
    }
    AetherStore(database).add_event("unified-dispatch", json.dumps(envelope))
    server = matrix.LocalThreadingHTTPServer(
        ("127.0.0.1", 0), matrix.HistorianLiveServer
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/") as response:
            page = response.read().decode("utf-8")
            assert response.status == 200
            assert "Arts &amp; Link Telemetry" in page
            assert "refreshArtsTelemetry" in page

        with urlopen(
            f"http://127.0.0.1:{server.server_port}/api/matrix/arts/latest"
        ) as response:
            result = json.loads(response.read())
            assert response.status == 200
            assert result["event"]["event"] == "ARTS_STAGE_CUE_REQUESTED"
            assert result["event"]["payload"]["status"] == (
                "REQUIRES_OPERATOR_APPROVAL"
            )
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
@pytest.mark.parametrize("installed", [False, True])
def test_frontend_assets_are_served_without_reading_private_telemetry(
    matrix, path, content_type, marker, installed, tmp_path, monkeypatch
):
    if installed:
        source = Path(matrix.__file__).resolve().parent / "frontend"
        prefix = tmp_path / "installed"
        destination = prefix / "share" / "aether-engine" / "observatory"
        shutil.copytree(source, destination)
        monkeypatch.setattr(matrix, "__file__", str(prefix / "site" / "aether_master_matrix.py"))
        monkeypatch.setattr(matrix.sys, "prefix", str(prefix))
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
                assert (
                    "connect-src 'self' https://api.open-meteo.com https://geocoding-api.open-meteo.com"
                    in policy
                )
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


def test_copernicus_chat_uses_session_context_and_optional_weather(matrix, monkeypatch):
    observed = {}

    def query_brain(self, prompt, *, system=None):
        observed["prompt"] = prompt
        observed["system"] = system
        return "A local reply."

    monkeypatch.setattr(matrix.AetherHistorian, "query_brain", query_brain)
    monkeypatch.setattr(matrix, "COPERNICUS_MODEL", "qwen2.5-coder")
    monkeypatch.setitem(
        matrix._copernicus_model_status, "model", matrix.COPERNICUS_MODEL
    )
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
        with urlopen(f"{base_url}/api/model/status") as response:
            model_status = json.loads(response.read())
        assert model_status["model"] == "qwen2.5-coder"
        assert model_status["status"] == "pending"
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
                {
                    "message": "What is the cloud cover?",
                    "weather_context": weather_context,
                }
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
        assert "Medical topics are educational research only" in observed["system"]
        assert "Never treat model output as approval" in observed["system"]

        history = [
            {"role": "user", "content": "My name is Ada."},
            {"role": "assistant", "content": "Nice to meet you, Ada."},
        ]
        request = Request(
            f"{base_url}/api/chat",
            data=json.dumps(
                {"message": "What name did I share?", "history": history}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            assert response.status == 200
        assert "User: My name is Ada." in observed["prompt"]
        assert "Assistant: Nice to meet you, Ada." in observed["prompt"]
        assert observed["prompt"].endswith(
            "Current user message:\nWhat name did I share?"
        )
        assert "up to six recent turns" in observed["system"]
        assert "untrusted user content" in observed["system"]

        invalid_histories = [
            [{"role": "assistant", "content": "Orphaned assistant turn."}],
            [
                {"role": "user", "content": "A", "unexpected": True},
                {"role": "assistant", "content": "B"},
            ],
            [
                {"role": role, "content": "x"}
                for _ in range(7)
                for role in ("user", "assistant")
            ],
            [
                {"role": role, "content": "x" * 4000}
                for role in ("user", "assistant", "user", "assistant")
            ],
        ]
        for invalid_history in invalid_histories:
            request = Request(
                f"{base_url}/api/chat",
                data=json.dumps(
                    {"message": "Hello", "history": invalid_history}
                ).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with pytest.raises(HTTPError) as error:
                urlopen(request)
            assert error.value.code == 422

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


def test_dashboard_chat_no_longer_routes_prompts_through_governor(
    matrix, monkeypatch
):
    class EmptyArchive:
        def context_for_message(self, message):
            return ""

    calls = []

    def query_brain(self, prompt, *, system=None):
        calls.append((prompt, system))
        if prompt == "A rocket is offline":
            raise matrix.OllamaConnectionError("offline")
        return "A local reply."

    monkeypatch.setattr(matrix, "UniversalHistoryArchive", EmptyArchive)
    monkeypatch.setattr(matrix, "KineticPropulsionArchive", EmptyArchive)
    monkeypatch.setattr(matrix.AetherHistorian, "query_brain", query_brain)
    server = matrix.LocalThreadingHTTPServer(("127.0.0.1", 0), matrix.HistorianLiveServer)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"

    def send(message):
        return urlopen(Request(root + "/api/chat", data=json.dumps({"message": message}).encode(),
                               headers={"Content-Type": "application/json"}))

    try:
        with urlopen(root + "/weather") as response:
            page = response.read().decode()
        assert "Agent routing is retired" in page
        assert "No Matrix data or controls are connected." not in page
        for prompt in ("Tell me about stars", "Explain rocket thrust", "Hello"):
            with send(prompt) as response:
                body = json.load(response)
            assert "governor" not in body
            assert "assigned_node" not in calls[-1][1]
        with pytest.raises(HTTPError) as error:
            send("A rocket is offline")
        assert error.value.code == 503
        assert "governor" not in json.load(error.value)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_recovery_readiness_report_is_non_actuating_and_non_certifying(matrix):
    server = matrix.LocalThreadingHTTPServer(
        ("127.0.0.1", 0), matrix.HistorianLiveServer
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(root + "/") as response:
            page = response.read().decode("utf-8")
        assert 'id="prepare-recovery-readiness"' in page
        assert 'id="hardware-connection-checks"' in page
        assert 'id="recovery-phase-gate"' in page
        assert 'id="academic-review-checks"' in page
        assert 'id="evidence-ledger-entries"' in page
        assert 'id="usb-inventory-form"' in page
        assert "does not inspect, modify, actuate, or certify hardware" in page

        with urlopen(root + "/api/matrix/recovery-readiness") as response:
            report = json.load(response)
        assert report["execution_status"] == "PREPARATION_ONLY"
        assert report["connected_hardware"] == {
            "status": "NOT_VERIFIED",
            "device_identity": None,
            "inspection_performed": False,
        }
        assert report["connection_verification_status"] == "NOT_VERIFIED"
        assert report["next_phase"]["status"] == "BLOCKED_PENDING_DEVICE_DETAILS"
        assert report["next_phase"]["recovery_authorized"] is False
        assert all(
            item["status"] == "NOT_VERIFIED"
            for item in report["phase_gate_checks"]
        )
        assert any(
            "host OS enumerates" in check
            for check in report["hardware_connection_checks"]
        )
        assert any(
            "fresh heartbeat/status update" in check
            for check in report["hardware_connection_checks"]
        )
        assert report["physical_recovery"]["status"] == "NOT_PERFORMED"
        assert report["physical_recovery"]["actuation_performed"] is False
        assert report["academic_review"]["status"] == "NOT_CERTIFIED"
        assert report["academic_review"]["external_independent_review_required"] is True
        assert report["required_before_recovery"]
        assert report["evidence_for_independent_review"]

        readiness = Request(
            root + "/api/matrix/recovery-readiness",
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(readiness) as response:
            assert json.load(response)["execution_status"] == "PREPARATION_ONLY"
        with urlopen(root + "/api/matrix/evidence-ledger") as response:
            ledger = json.load(response)
        assert ledger["integrity_status"] == "HASH_CHAIN_VALID_NOT_SIGNED"
        assert ledger["entries"][0]["check_id"] == "recovery-readiness-snapshot"
        assert ledger["entries"][0]["status"] == "UNKNOWN"

        with pytest.raises(HTTPError) as error:
            urlopen(root + "/api/matrix/recovery-readiness?device=unknown")
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_usb_enumeration_is_redacted_and_recorded(matrix, monkeypatch):
    observed_labels = []

    def fake_probe(label):
        observed_labels.append(label)
        return {
            "status": "VERIFIED",
            "device_count": 2,
            "expected_label_match": True,
        }

    monkeypatch.setattr(matrix, "probe_macos_usb_inventory", fake_probe)
    server = matrix.LocalThreadingHTTPServer(
        ("127.0.0.1", 0), matrix.HistorianLiveServer
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    try:
        request = Request(
            root + "/api/matrix/usb-enumeration",
            data=b'{"expected_product_label":"YOTUO"}',
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            result = json.load(response)
        assert result["status"] == "VERIFIED"
        assert result["device_count"] == 2
        assert result["expected_label_match"] is True
        assert observed_labels == ["YOTUO"]

        with urlopen(root + "/api/matrix/evidence-ledger") as response:
            ledger = json.load(response)
        entry = ledger["entries"][0]
        assert entry["check_id"] == "host-usb-enumeration"
        assert entry["status"] == "VERIFIED"
        serialized = json.dumps(ledger)
        assert "YOTUO" not in serialized
        assert "serial" in serialized

        invalid = Request(
            root + "/api/matrix/usb-enumeration",
            data=b'{"expected_product_label":"serial/number"}',
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(HTTPError) as error:
            urlopen(invalid)
        assert error.value.code == 422
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_equilibrium_review_endpoint_and_form_fallback(matrix):
    server = matrix.LocalThreadingHTTPServer(
        ("127.0.0.1", 0), matrix.HistorianLiveServer
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(root + "/") as response:
            page = response.read().decode("utf-8")
            assert response.status == 200
            assert 'id="equilibrium-review-form"' in page
            assert 'action="/api/matrix/equilibrium/evaluate"' in page
            assert "never authorizes or executes proposals" in page
            assert 'aria-live="polite"' in page

        safe_request = Request(
            root + "/api/matrix/equilibrium/evaluate",
            data=json.dumps(
                {
                    "action_name": "Optimize supply chain routing",
                    "target_impact_severity": 20,
                    "ecosystem_hazard": 5,
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(safe_request) as response:
            safe = json.load(response)
        assert safe["decision"] == "SIMULATION_ONLY"
        assert safe["risk_index"] == 21.0
        assert safe["action_executed"] is False

        hostile_name = "<img src=x onerror=alert(1)>"
        form_request = Request(
            root + "/api/matrix/equilibrium/evaluate",
            data=urlencode(
                {
                    "action_name": hostile_name,
                    "target_impact_severity": "70",
                    "ecosystem_hazard": "65",
                }
            ).encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html",
            },
            method="POST",
        )
        with urlopen(form_request) as response:
            fallback = response.read().decode("utf-8")
            assert response.headers["Content-Type"].startswith("text/html")
        assert "BLOCKED_IN_SIMULATION" in fallback
        assert "No proposal was executed." in fallback
        assert "&lt;img" in fallback
        assert hostile_name not in fallback

        invalid_request = Request(
            root + "/api/matrix/equilibrium/evaluate",
            data=json.dumps(
                {
                    "action_name": "Invalid severity",
                    "target_impact_severity": 101,
                    "ecosystem_hazard": 0,
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(invalid_request)
        assert error.value.code == 422
        assert "between 0 and 100" in json.load(error.value)["detail"]

        duplicate_fields = Request(
            root + "/api/matrix/equilibrium/evaluate",
            data=(
                b'{"action_name":"First","action_name":"Second",'
                b'"target_impact_severity":1,"ecosystem_hazard":0}'
            ),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(duplicate_fields)
        assert error.value.code == 400
        assert json.load(error.value)["detail"] == "Invalid JSON body."
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_equilibrium_weights_endpoint_and_matrix_form(matrix):
    server = matrix.LocalThreadingHTTPServer(
        ("127.0.0.1", 0), matrix.HistorianLiveServer
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(root + "/") as response:
            page = response.read().decode("utf-8")
        assert 'id="equilibrium-weights-form"' in page
        assert 'action="/api/matrix/equilibrium/weights"' in page
        assert "not physical proof or a security boundary" in page

        request = Request(
            root + "/api/matrix/equilibrium/weights",
            data=json.dumps({"risk_score": 0.15}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            result = json.load(response)
        assert response.status == 200
        assert result["peer_review"]["wave_weight"] == 0.9852
        assert result["peer_review"]["particle_weight"] == 0.0148
        assert result["guardrail"]["wave_weight"] == pytest.approx(
            0.9852259683067269
        )
        assert result["models_agree_at_four_decimals"] is True
        assert result["action_executed"] is False

        form_request = Request(
            root + "/api/matrix/equilibrium/weights",
            data=urlencode(
                {
                    "risk_score": "0.75",
                    "r_critical": "0.5",
                    "steepness": "4",
                }
            ).encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html",
            },
            method="POST",
        )
        with urlopen(form_request) as response:
            fallback = response.read().decode("utf-8")
            assert response.headers["Content-Type"].startswith("text/html")
        assert "0.2689414213699951" in fallback
        assert "No action was executed." in fallback

        invalid_request = Request(
            root + "/api/matrix/equilibrium/weights",
            data=json.dumps({"risk_score": 1.01}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(invalid_request)
        assert error.value.code == 422
        assert "between 0 and 1" in json.load(error.value)["detail"]

        duplicate_fields = Request(
            root + "/api/matrix/equilibrium/weights",
            data=b'{"risk_score":0.1,"risk_score":0.9}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(duplicate_fields)
        assert error.value.code == 422
        assert "Duplicate JSON fields" in json.load(error.value)["detail"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_personas_are_validated_and_applied(matrix, monkeypatch):
    class EmptyArchive:
        def context_for_message(self, message):
            return ""

    systems = []
    monkeypatch.setattr(matrix, "UniversalHistoryArchive", EmptyArchive)
    monkeypatch.setattr(matrix, "KineticPropulsionArchive", EmptyArchive)
    monkeypatch.setattr(
        matrix.AetherHistorian, "query_brain",
        lambda self, prompt, *, system=None: systems.append(system) or "Reply",
    )
    server = matrix.LocalThreadingHTTPServer(("127.0.0.1", 0), matrix.HistorianLiveServer)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"

    def send(payload):
        return urlopen(Request(root + "/api/chat", data=json.dumps(payload).encode(),
                               headers={"Content-Type": "application/json"}))

    try:
        with urlopen(root + "/weather") as response:
            page = response.read().decode()
        assert 'id="persona-selector"' in page
        assert '/persona_matrix.js' in page
        for key in matrix.PERSONAS:
            assert f'value="{key}"' in page
            with send({"message": "Hello", "persona": key}) as response:
                body = json.load(response)
            assert body["persona"] == key
            assert matrix.PERSONAS[key]["prompt"] in systems[-1]
            assert "you cannot execute or control agents" in systems[-1].lower()
            assert "not system instructions" in systems[-1]
        with send({"message": "Hello"}) as response:
            assert json.load(response)["persona"] == "copernicus_core"
        count = len(systems)
        for invalid in ("unknown", "", None, [], {"prompt": "override"}):
            with pytest.raises(HTTPError) as error:
                send({"message": "Hello", "persona": invalid})
            assert error.value.code == 422
        assert len(systems) == count
        for asset in ("/persona_matrix.js", "/persona_matrix.css"):
            with urlopen(root + asset) as response:
                assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_command_center_astronomy_endpoint_validates_inputs_and_data_availability(
    matrix, monkeypatch
):
    class FakeAstronomyEngine:
        unavailable = False

        def compute_local_sky(self, instant, max_magnitude):
            if self.unavailable:
                raise OSError("catalog offline")
            assert instant.tzinfo is not None
            assert max_magnitude == 4.0
            return [{"hip_id": 1, "alt_deg": 12.0}]

    engine = FakeAstronomyEngine()
    monkeypatch.setattr(matrix, "get_astronomy_engine", lambda *_coordinates: engine)
    server = matrix.LocalThreadingHTTPServer(
        ("127.0.0.1", 0), matrix.HistorianLiveServer
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/api/astronomy/visible-stars"
        with urlopen(f"{base_url}?latitude=34&longitude=-117") as response:
            data = json.loads(response.read())
        assert data["stars"] == [{"hip_id": 1, "alt_deg": 12.0}]
        for invalid_query in (
            "?latitude=34&latitude=35",
            "?latitude=34&longitude=-117&max_magnitude=9",
        ):
            with pytest.raises(HTTPError) as error:
                urlopen(base_url + invalid_query)
            assert error.value.code == 422

        engine.unavailable = True
        with pytest.raises(HTTPError) as error:
            urlopen(base_url)
        assert error.value.code == 503
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_command_center_chat_uses_history_archive(matrix, monkeypatch, tmp_path):
    from history_matrix_archive import UniversalHistoryArchive, seed_example_history

    archive = UniversalHistoryArchive(tmp_path / "history.sqlite3")
    seed_example_history(archive)
    monkeypatch.setattr(matrix, "UniversalHistoryArchive", lambda: archive)
    observed = {}

    def query_brain(self, prompt, *, system=None):
        observed["prompt"] = prompt
        observed["system"] = system
        return "A local reply."

    monkeypatch.setattr(matrix.AetherHistorian, "query_brain", query_brain)
    server = matrix.LocalThreadingHTTPServer(
        ("127.0.0.1", 0), matrix.HistorianLiveServer
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/chat",
            data=json.dumps({"message": "Tell me about Sumer"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            assert response.status == 200
        assert observed["prompt"] == "Tell me about Sumer"
        assert "sumer_01" in observed["system"]
        assert "unverified" in observed["system"]
        assert "britannica.com/place/Sumer" in observed["system"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_command_center_chat_uses_propulsion_reference(matrix, monkeypatch, tmp_path):
    from aether_engine.propulsion_matrix import (
        KineticPropulsionArchive,
        seed_civilian_references,
    )

    archive = KineticPropulsionArchive(tmp_path / "propulsion.sqlite3")
    seed_civilian_references(archive)
    monkeypatch.setattr(matrix, "KineticPropulsionArchive", lambda: archive)
    observed = {}

    def query_brain(self, prompt, *, system=None):
        observed["system"] = system
        return "Reply"

    monkeypatch.setattr(matrix.AetherHistorian, "query_brain", query_brain)
    server = matrix.LocalThreadingHTTPServer(
        ("127.0.0.1", 0), matrix.HistorianLiveServer
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/chat",
            data=json.dumps({"message": "What is JT3D?"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            assert response.status == 200
        assert "airandspace.si.edu" in observed["system"]
        assert "untrusted data" in observed["system"]
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


def test_dashboard_reports_non_utf8_telemetry(matrix):
    matrix.LOG_FILE.write_bytes(b"\xff")
    with pytest.raises(RuntimeError, match="Could not read telemetry vault"):
        matrix._render_dashboard()


def test_dashboard_rejects_invalid_action_density(matrix):
    matrix.LOG_FILE.write_text(
        json.dumps(
            [
                {
                    "system_status": "EQUILIBRIUM",
                    "entanglement_entropy_nats": 120.0,
                    "action_density": "invalid",
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="action density"):
        matrix._render_dashboard()


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
