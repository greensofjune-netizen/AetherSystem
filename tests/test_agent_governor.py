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


def test_standalone_demo_reports_routing_and_chart():
    result = subprocess.run(
        [sys.executable, "-m", "agent_governor"],
        text=True,
        capture_output=True,
        check=True,
    )
    lines = result.stdout.splitlines()
    assert lines[0].startswith("SIMULATED -> astro_agent")
    assert lines[1].startswith("REJECTED -> governor_core")
    encoded = lines[2].removeprefix('chartjs_spec: "').removesuffix('"')
    assert json.loads(base64.b64decode(encoded))["metadata"]["estimated_total_gb"] == 4.1


def test_matrix_governor_endpoints_and_dashboard(tmp_path, monkeypatch):
    import aether_master_matrix as matrix

    monkeypatch.setattr(matrix, "LOG_FILE", tmp_path / "telemetry.json")
    monkeypatch.setattr(matrix, "agent_governor", AgentGovernor())
    server = matrix.LocalThreadingHTTPServer(("127.0.0.1", 0), matrix.HistorianLiveServer)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(root + "/") as response:
            page = response.read().decode()
        assert "Agent Governor" in page
        assert "Estimated total: 4.1 GB" in page
        assert "no tasks are executed or memory measured" in page
        with urlopen(root + "/api/matrix/governor/allocations") as response:
            result = json.load(response)
        assert json.loads(base64.b64decode(result["chartjs_spec"])) == result["chart"]
        body = json.dumps({
            "task_description": "Compute sky position",
            "domain": "Astronomy",
            "execution_payload": {"latitude": 34.0975, "longitude": -117.6484},
        }).encode()
        route = Request(root + "/api/matrix/governor/route", data=body,
                        headers={"Content-Type": "application/json"})
        with urlopen(route) as response:
            assert json.load(response)["status"] == "SIMULATED"
        invalid = Request(root + "/api/matrix/governor/route", data=b'{}',
                          headers={"Content-Type": "application/json"})
        with pytest.raises(HTTPError) as error:
            urlopen(invalid)
        assert error.value.code == 422
        foreign = Request(root + "/api/matrix/governor/route", data=body,
                          headers={"Content-Type": "application/json", "Origin": "http://example.com"})
        with pytest.raises(HTTPError) as error:
            urlopen(foreign)
        assert error.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
