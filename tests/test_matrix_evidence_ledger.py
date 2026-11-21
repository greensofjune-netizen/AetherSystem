import json
import os
from types import SimpleNamespace

import pytest

from aether_engine import matrix_evidence_ledger as ledger_module
from aether_engine.matrix_evidence_ledger import (
    EvidenceLedgerError,
    MatrixEvidenceLedger,
    probe_macos_usb_inventory,
)
from matrix_academic_benchmarks import MatrixAcademicBenchmarkSuite


def test_ledger_records_redacted_evidence_and_verifies_hash_chain(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = MatrixEvidenceLedger(path)
    benchmark = MatrixAcademicBenchmarkSuite().run(sim_cycles=2)

    benchmark_entry = ledger.record_benchmark(benchmark)
    readiness_entry = ledger.record_readiness_snapshot()
    usb_entry = ledger.record_usb_inventory(
        device_count=2,
        expected_label_match=True,
        probe_status="VERIFIED",
    )
    snapshot = ledger.snapshot()

    assert snapshot["integrity_status"] == "HASH_CHAIN_VALID_NOT_SIGNED"
    entries = snapshot["entries"]
    assert [entry["sequence"] for entry in entries] == [1, 2, 3]
    assert entries[0]["status"] == "VERIFIED"
    assert entries[1]["status"] == "UNKNOWN"
    assert entries[2]["status"] == "VERIFIED"
    assert usb_entry["previous_entry_sha256"] == readiness_entry["entry_sha256"]
    assert benchmark_entry["recorded_at_utc"].endswith("+00:00")
    assert "serials" in usb_entry["summary"]
    assert "YOTUO" not in path.read_text(encoding="utf-8")
    assert "academic certification" in " ".join(entries[0]["limitations"])
    if os.name == "posix":
        assert path.stat().st_mode & 0o077 == 0


def test_ledger_rejects_tampering_without_rewriting_original(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = MatrixEvidenceLedger(path)
    ledger.record_readiness_snapshot()
    original = path.read_text(encoding="utf-8")
    altered = json.loads(original)
    altered["entries"][0]["summary"] = "Changed evidence"
    path.write_text(json.dumps(altered), encoding="utf-8")

    with pytest.raises(EvidenceLedgerError, match="integrity check failed"):
        ledger.snapshot()


def test_ledger_rejects_symlinked_path(tmp_path):
    target = tmp_path / "target.json"
    target.write_text("untouched", encoding="utf-8")
    path = tmp_path / "ledger.json"
    path.symlink_to(target)

    with pytest.raises(EvidenceLedgerError, match="symbolic link"):
        MatrixEvidenceLedger(path).snapshot()
    assert target.read_text(encoding="utf-8") == "untouched"


def test_macos_usb_probe_exposes_only_count_and_match(monkeypatch):
    def fake_run(command, **kwargs):
        assert command == ["ioreg", "-p", "IOUSB", "-w0"]
        assert kwargs["timeout"] == 10
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "+-o YOTUO Receiver@02000000 <class IOUSBHostDevice, id 0x11, "
                "registered, matched, active, busy 0>\n"
                "+-o USB Hub@01000000 <class IOUSBHostDevice, id 0x22, "
                "registered, matched, active, busy 0>\n"
                "+-o Inactive Device@03000000 <class IOUSBHostDevice, id 0x33, "
                "registered, matched, inactive, busy 0>\n"
            ),
        )

    monkeypatch.setattr(ledger_module.sys, "platform", "darwin")
    monkeypatch.setattr(ledger_module.subprocess, "run", fake_run)

    result = probe_macos_usb_inventory("YOTUO Receiver")

    assert result == {
        "status": "VERIFIED",
        "device_count": 2,
        "expected_label_match": True,
    }


def test_usb_probe_does_not_claim_hardware_on_unsupported_platform(monkeypatch):
    monkeypatch.setattr(ledger_module.sys, "platform", "linux")

    assert probe_macos_usb_inventory(None) == {
        "status": "NOT_MEASURED",
        "device_count": 0,
        "expected_label_match": None,
    }


def test_usb_probe_rejects_invalid_expected_label(monkeypatch):
    monkeypatch.setattr(ledger_module.sys, "platform", "darwin")

    with pytest.raises(ValueError, match="safe characters"):
        probe_macos_usb_inventory("serial/number")
