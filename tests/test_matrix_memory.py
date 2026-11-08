from __future__ import annotations

import asyncio
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


@pytest.fixture
def matrix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module_path = Path(__file__).resolve().parents[1] / "aether_master_matrix.py"
    spec = importlib.util.spec_from_file_location("matrix_memory_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "LOG_FILE", tmp_path / "historian.json")
    return module


def test_concurrent_telemetry_writes_preserve_every_event(matrix):
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(
                matrix.log_telemetry_event,
                epoch,
                1.0,
                120.0,
                35.0,
                "EQUILIBRIUM",
            )
            for epoch in range(1, 41)
        ]
        for future in futures:
            future.result()

    entries = json.loads(matrix.LOG_FILE.read_text(encoding="utf-8"))
    assert len(entries) == 40
    assert {entry["epoch"] for entry in entries} == set(range(1, 41))


def test_full_test_drive_records_all_epochs(matrix):
    asyncio.run(
        matrix.run_master_matrix_test_drive(steps=30, interval_seconds=0)
    )

    entries = json.loads(matrix.LOG_FILE.read_text(encoding="utf-8"))
    assert len(entries) == 30
    assert entries[0]["scale_factor"] == 1.2
    assert entries[-1]["scale_factor"] == 0.03
    assert entries[-1]["system_status"] == "BOUNCE_ACTIVE"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.0.2.1", "::1", "localhost"])
def test_server_refuses_non_explicit_loopback_hosts(matrix, host):
    with pytest.raises(ValueError, match="loopback"):
        matrix.run_web_server(host=host, port=8000)


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_server_refuses_invalid_ports(matrix, port):
    with pytest.raises(ValueError, match="port"):
        matrix.run_web_server(port=port)
