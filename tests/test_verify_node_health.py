import hashlib
import json
import plistlib
from types import SimpleNamespace

import pytest

import verify_node_health as diagnostics
from aether_engine.system_diagnostics import SystemDiagnosticCheck


def test_remote_probe_makes_no_connection_without_explicit_target(monkeypatch):
    def unexpected_connection(*args, **kwargs):
        raise AssertionError("A remote connection was not explicitly requested.")

    monkeypatch.setattr(diagnostics.socket, "create_connection", unexpected_connection)

    result = diagnostics.check_remote_yotuo_node(None)

    assert result["status"] == "NOT_REQUESTED"
    assert result["probes"] == {}


def test_remote_probe_rejects_non_private_ip_before_connecting(monkeypatch):
    def unexpected_connection(*args, **kwargs):
        raise AssertionError("Public IPs must be rejected before connecting.")

    monkeypatch.setattr(diagnostics.socket, "create_connection", unexpected_connection)

    with pytest.raises(ValueError, match="private IP"):
        diagnostics.check_remote_yotuo_node("8.8.8.8")


def test_remote_probe_tests_only_fixed_tcp_ports(monkeypatch):
    calls = []

    class ConnectedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_connection(address, *, timeout):
        calls.append((address, timeout))
        if address[1] == 11434:
            raise ConnectionRefusedError
        return ConnectedSocket()

    monkeypatch.setattr(diagnostics.socket, "create_connection", fake_connection)

    result = diagnostics.check_remote_yotuo_node("192.168.1.50")

    assert [address[1] for address, _ in calls] == [22, 11434]
    assert result["status"] == "PORT_REACHABILITY_ONLY"
    assert result["probes"]["ssh_tcp"]["status"] == "TCP_CONNECTED"
    assert result["probes"]["ollama_tcp"]["status"] == "CONNECTION_FAILED"
    assert "hardware health" in result["limitation"]


def test_storage_check_reports_smart_metadata_without_scanning(monkeypatch):
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        diagnostics.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(total=10 * 1024**3, free=4 * 1024**3),
    )
    commands = []

    def fake_command(command, *, timeout=5.0):
        commands.append((command, timeout))
        return plistlib.dumps({"SMARTStatus": "Not Supported"})

    monkeypatch.setattr(diagnostics, "_run_read_only", fake_command)

    result = diagnostics.get_storage_and_smart_health("/")

    assert result["total_storage_gb"] == 10.0
    assert result["free_storage_gb"] == 4.0
    assert result["smart_status"] == "Not Supported"
    assert commands == [(["diskutil", "info", "-plist", "/"], 5.0)]
    assert "no filesystem scan" in result["scope"]


def test_report_hash_covers_report_and_disclaims_authority(monkeypatch):
    class FakeScanner:
        def __init__(self, workspace_root):
            pass

        def scan(self):
            return (SystemDiagnosticCheck("Host", "OK", "Local checks passed."),)

    monkeypatch.setattr(diagnostics, "SystemDiagnosticScanner", FakeScanner)
    monkeypatch.setattr(
        diagnostics,
        "get_storage_and_smart_health",
        lambda path: {"status": "MEASURED", "smart_status": "Not Supported"},
    )
    monkeypatch.setattr(
        diagnostics, "_load_average", lambda: {"status": "NOT_MEASURED"}
    )

    report = diagnostics.run_verifiable_diagnostic()
    canonical = json.dumps(
        {key: value for key, value in report.items() if key != "report_sha256"},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

    assert report["local_status"] == "WARN"
    assert report["paired_yotuo_node"]["status"] == "NOT_REQUESTED"
    assert "hostname" not in report["host_node"]
    assert (
        report["report_sha256"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    )
    assert "not a signature" in report["integrity_note"]
