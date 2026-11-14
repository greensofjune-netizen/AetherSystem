from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from aether_engine import system_diagnostics
from aether_engine.quantum_simulator import (
    QuantumStateSimulator,
    StateCollapseAnomalyError,
    SystemDiagnosticScanner,
    diagnostics_main,
)


def test_compute_wave_coherence_returns_expected_percentage() -> None:
    simulator = QuantumStateSimulator(risk_coefficient=0.30)

    assert simulator.compute_wave_coherence() == 70.0


def test_calculate_entropy_index_returns_value_and_detects_collapse() -> None:
    simulator = QuantumStateSimulator(fluctuation_velocity=50.0)

    assert simulator.calculate_entropy_index(state_density=57.0) == 67.0
    with pytest.raises(StateCollapseAnomalyError, match="decoherence imminent"):
        simulator.calculate_entropy_index(state_density=120.0)


def test_render_operator_card_reports_simulator_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    simulator = QuantumStateSimulator()

    simulator.render_operator_card()

    output = capsys.readouterr().out
    assert "AETHER COHERENT SUPERPOSITION STATUS ENGINE" in output
    assert "Wave Coherence   : 70.0%" in output
    assert "State Density    : 57.0ψ" in output
    assert "Entropy Index    : 67.0" in output


def _make_project(path: Path) -> Path:
    (path / "pyproject.toml").write_text(
        '[project]\nname = "aether-engine"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (path / "src" / "aether_engine").mkdir(parents=True)
    return path


def _stub_host_metrics(
    monkeypatch: pytest.MonkeyPatch,
    *,
    available_memory: int = 4 * 1024**3,
    free_disk: int = 20 * 1024**3,
) -> None:
    monkeypatch.setattr(
        system_diagnostics,
        "_read_memory_stats",
        lambda: (8 * 1024**3, available_memory),
    )
    monkeypatch.setattr(
        system_diagnostics.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(
            total=100 * 1024**3,
            used=100 * 1024**3 - free_disk,
            free=free_disk,
        ),
    )


def test_system_diagnostic_scanner_reports_local_app_and_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _make_project(tmp_path)
    _stub_host_metrics(monkeypatch)

    scanner = SystemDiagnosticScanner(workspace)
    before = {path.relative_to(workspace) for path in workspace.rglob("*")}
    checks = scanner.scan()
    after = {path.relative_to(workspace) for path in workspace.rglob("*")}
    results = {check.category: check for check in checks}

    assert after == before
    assert set(results) == {
        "Python runtime",
        "Host",
        "Memory",
        "Workspace storage",
        "AetherSystem project",
        "Quantum simulator",
        "Symbiotic equilibrium",
    }
    assert all(check.status == "OK" for check in checks)
    assert "collapse guard is active" in results["Quantum simulator"].detail
    assert "zero-harm" in results["Symbiotic equilibrium"].detail

    report = scanner.render_report(checks)
    assert "AETHER SYSTEM DIAGNOSTICS" in report
    assert "7 checks; 7 OK, 0 warnings, 0 failures." in report


def test_system_diagnostic_scanner_surfaces_low_resources_and_bad_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_host_metrics(
        monkeypatch,
        available_memory=128 * 1024**2,
        free_disk=64 * 1024**2,
    )

    checks = SystemDiagnosticScanner(tmp_path).scan()
    results = {check.category: check for check in checks}

    assert results["Memory"].status == "WARN"
    assert results["Workspace storage"].status == "FAIL"
    assert results["AetherSystem project"].status == "FAIL"
    assert diagnostics_main(["--workspace", str(tmp_path)]) == 1


def test_diagnostics_main_prints_report_and_returns_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = _make_project(tmp_path)
    _stub_host_metrics(monkeypatch)

    result = diagnostics_main(["--workspace", str(workspace)])

    assert result == 0
    assert "AETHER SYSTEM DIAGNOSTICS" in capsys.readouterr().out
