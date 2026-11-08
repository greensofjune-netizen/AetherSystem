from math import pi

import pytest

from aether_engine.aether_quantum import AetherQuantumEngine


def test_macro_action_returns_expected_values():
    engine = AetherQuantumEngine(alpha=0.5, gamma_bounce=0.2375)

    result = engine.evaluate_macro_action(
        scale_factor=0.5,
        scalar_density=2.5,
        curvature_r=2.0,
    )

    expected_action = (
        2.0 / (16.0 * pi)
        + 0.5 * 2.0**2
        + 0.2375 / 0.5**2
        + 2.5
    )
    assert result == {
        "bounce_active": False,
        "total_action_density": expected_action,
        "metric_status": "EQUILIBRIUM",
    }


def test_macro_action_triggers_bounce_at_planckian_scale_factor():
    result = AetherQuantumEngine().evaluate_macro_action(
        scale_factor=0.1,
        scalar_density=0.0,
        curvature_r=2.0,
    )

    assert result["bounce_active"] is True
    assert result["total_action_density"] > 200.0


def test_macro_action_does_not_trigger_bounce_above_scale_threshold():
    result = AetherQuantumEngine().evaluate_macro_action(
        scale_factor=0.100001,
        scalar_density=0.0,
        curvature_r=2.0,
    )

    assert result["bounce_active"] is False


def test_macro_action_marks_critical_pressure_at_action_threshold():
    result = AetherQuantumEngine(alpha=0.0, gamma_bounce=0.0).evaluate_macro_action(
        scale_factor=1.0,
        scalar_density=1_000_000.0,
        curvature_r=0.0,
    )

    assert result["metric_status"] == "CRITICAL_PRESSURE"


def test_macro_action_rejects_nonpositive_scale_factor():
    engine = AetherQuantumEngine()

    for scale_factor in (0.0, -0.1):
        with pytest.raises(ValueError, match="scale_factor"):
            engine.evaluate_macro_action(scale_factor, 0.0, 0.0)
