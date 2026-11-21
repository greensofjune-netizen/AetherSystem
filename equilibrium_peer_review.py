"""Normalized, simulation-only peer-review weights for equilibrium scoring."""

from __future__ import annotations

import math


def _validate_fraction(value: object, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise ValueError(f"{name} must be a finite number between 0 and 1.")
    try:
        normalized = float(value)
    except OverflowError as error:
        raise ValueError(
            f"{name} must be a finite number between 0 and 1."
        ) from error
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{name} must be a finite number between 0 and 1.")
    return normalized


def _validate_steepness(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise ValueError("steepness must be a finite number greater than 0.")
    try:
        slope = float(value)
    except OverflowError as error:
        raise ValueError(
            "steepness must be a finite number greater than 0."
        ) from error
    if not math.isfinite(slope) or slope <= 0.0:
        raise ValueError("steepness must be a finite number greater than 0.")
    return slope


def _calculate_weights(
    risk_score: object,
    critical_threshold: object,
    steepness: object,
) -> tuple[float, float]:
    risk = _validate_fraction(risk_score, "risk_score")
    threshold = _validate_fraction(critical_threshold, "critical_threshold")
    slope = _validate_steepness(steepness)
    exponent = slope * (risk - threshold)

    if exponent >= 0.0:
        exp_negative = math.exp(-exponent)
        wave_weight = exp_negative / (1.0 + exp_negative)
    else:
        exp_positive = math.exp(exponent)
        wave_weight = 1.0 / (1.0 + exp_positive)

    return wave_weight, 1.0 - wave_weight


def calculate_equilibrium(risk_score: float) -> tuple[float, float]:
    """Return rounded complementary weights for a normalized risk score."""
    wave_weight, particle_weight = _calculate_weights(
        risk_score,
        critical_threshold=0.5,
        steepness=12.0,
    )
    return round(wave_weight, 4), round(particle_weight, 4)


def calculate_state_weights(
    risk_score: float,
    r_critical: float = 0.5,
    steepness: float = 12.0,
) -> tuple[float, float]:
    """Return unrounded normalized-risk weights for configurable guardrail parameters."""
    return _calculate_weights(risk_score, r_critical, steepness)


def main() -> int:
    """Print the prototype's three normalized demonstration scenarios."""
    print("=" * 60)
    print("  EQUILIBRIUM PEER-REVIEW WEIGHT SIMULATION")
    print("=" * 60)
    for risk_score in (0.15, 0.50, 0.85):
        wave_weight, particle_weight = calculate_equilibrium(risk_score)
        print(
            f"Risk Input: {risk_score:.2f} | Wave: {wave_weight:<6} "
            f"| Particle: {particle_weight:<6}"
        )
    print("Illustrative weights only; this does not prove physical wave-particle duality.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
