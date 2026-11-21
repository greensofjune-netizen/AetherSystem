import base64
import json
import subprocess
import sys
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from agent_governor import AgentGovernor


@pytest.mark.parametrize(
    ("domain", "node"),
    [
        (" Astronomy ", "astro_agent"),
        ("PROPULSION", "kinetic_agent"),
        ("history", "history_agent"),
    ],
)
def test_routes_each_agent_as_simulation(domain, node):
    governor = AgentGovernor()
    payload = {"target": "Rigel"}
    result = governor.route_task("Examine the observation", domain, payload)
    assert result["status"] == "SIMULATED"
    assert result["assigned_node"] == node
    assert result["output_data"] == payload
    assert "No task was executed" in result["message"]
    assert result["timestamp"].endswith("Z")


@pytest.mark.parametrize(
    ("description", "domain", "payload"),
    [
        ("Deploy EXPLOIT", "History", {}),
        ("Test", "Astronomy", {"nested": ["Unauthorized_Tracking_pixel"]}),
        ("Test", "exploit", {}),
    ],
)
def test_keyword_screen_checks_all_input_without_logging_content(description, domain, payload):
    governor = AgentGovernor()
    result = governor.route_task(description, domain, payload)
    assert result["status"] == "REJECTED"
    assert result["assigned_node"] == "governor_core"
    assert "output_data" not in result
    assert "tracking" not in governor.orchestration_log[-1].lower()


def test_unroutable_inactive_agent_and_bounded_log():
    governor = AgentGovernor()
    governor.registry["astro_agent"].active_status = False
    for _ in range(205):
        assert governor.route_task("test", "Astronomy", {})["status"] == "UNROUTABLE"
    assert len(governor.orchestration_log) == 200
    assert governor.allocation_chart()["metadata"]["estimated_total_gb"] == 2.9


@pytest.mark.parametrize(
    ("description", "domain", "payload"),
    [("", "Astronomy", {}), ("test", "", {}), ("test", "Astronomy", []),
     ("test", "Astronomy", {"invalid": float("nan")}),
     ("test", "Astronomy", {"large": "a" * 32000})],
)
def test_invalid_requests_are_rejected(description, domain, payload):
    with pytest.raises(ValueError):
        AgentGovernor().route_task(description, domain, payload)


def test_chart_is_complete_and_base64_roundtrips():
    governor = AgentGovernor()
    chart = governor.allocation_chart()
    assert chart["metadata"]["orientation"] == "horizontal"
    assert chart["metadata"]["estimated_total_gb"] == 4.1
    assert chart["metadata"]["reference_threshold_gb"] == 5.3
    assert chart["metadata"]["measured"] is False
    assert chart["metadata"]["estimated_total_gb"] < 5.3
    assert chart["labels"] == [
        "Astronomy Node (Skyfield)",
        "Propulsion Node (Kinetics)",
        "History Node (Ledger Archive)",
        "Governor Overhead",
    ]
    assert [entry["value_raw"] for entry in chart["datasets"][0]["data"]] == [
        1.2, 1.5, 0.8, 0.6
    ]
    assert json.loads(base64.b64decode(governor.encoded_chart())) == chart


def test_standalone_entry_point_reports_retirement_without_routing():
    result = subprocess.run(
        [sys.executable, "-m", "agent_governor"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout.strip() == (
        "Agent Governor is retired; no tasks were routed or executed."
    )


def test_retired_governor_endpoints_and_academic_dashboard(tmp_path, monkeypatch):
    import aether_master_matrix as matrix

    monkeypatch.setattr(matrix, "LOG_FILE", tmp_path / "telemetry.json")
    monkeypatch.setenv(
        "AETHER_MATRIX_EVIDENCE_LEDGER_FILE",
        str(tmp_path / "matrix-evidence-ledger.json"),
    )
    server = matrix.LocalThreadingHTTPServer(("127.0.0.1", 0), matrix.HistorianLiveServer)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(root + "/") as response:
            page = response.read().decode()
        assert "Agent Governor" not in page
        assert "Matrix Ethics &amp; Academic Benchmarks" in page
        assert "Run local benchmark" in page
        assert "not a public certification" in page.lower()
        for path in ("/api/matrix/governor/allocations",):
            with pytest.raises(HTTPError) as error:
                urlopen(root + path)
            assert error.value.code == 410

        route = Request(root + "/api/matrix/governor/route", data=b"{}",
                        headers={"Content-Type": "application/json"})
        with pytest.raises(HTTPError) as error:
            urlopen(route)
        assert error.value.code == 410

        benchmark = Request(
            root + "/api/matrix/ethics-benchmarks",
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(benchmark) as response:
            result = json.load(response)
        assert result["policy_tests_passed"] is True
        assert result["benchmark_status"] == "LOCAL_POLICY_TESTS_PASS_NOT_CERTIFICATION"
        assert result["closed_loop_recovery"]["status"] == "NOT_MEASURED"
        with urlopen(root + "/api/matrix/evidence-ledger") as response:
            ledger = json.load(response)
        assert ledger["entries"][0]["check_id"] == "matrix-policy-benchmark"
        assert ledger["entries"][0]["status"] == "VERIFIED"

        invalid = Request(
            root + "/api/matrix/ethics-benchmarks",
            data=b'{"node_id":"spoofed"}',
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(HTTPError) as error:
            urlopen(invalid)
        assert error.value.code == 422

        foreign = Request(root + "/api/matrix/ethics-benchmarks", data=b"{}",
                          headers={"Content-Type": "application/json", "Origin": "http://example.com"})
        with pytest.raises(HTTPError) as error:
            urlopen(foreign)
        assert error.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
