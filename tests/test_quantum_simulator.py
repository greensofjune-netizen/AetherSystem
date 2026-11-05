from __future__ import annotations

import pytest

from aether_engine.quantum_simulator import (
    QuantumStateSimulator,
    StateCollapseAnomalyError,
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
