import math

import pytest

from equilibrium_peer_review import calculate_equilibrium, calculate_state_weights, main


@pytest.mark.parametrize(
    ("risk_score", "expected"),
    [
        (0.15, (0.9852, 0.0148)),
        (0.50, (0.5, 0.5)),
        (0.85, (0.0148, 0.9852)),
    ],
)
def test_peer_review_scenarios_match_prototype(risk_score, expected):
    assert calculate_equilibrium(risk_score) == expected


def test_peer_review_weights_are_complementary_and_symmetric():
    low_wave, low_particle = calculate_equilibrium(0.15)
    high_wave, high_particle = calculate_equilibrium(0.85)

    assert low_wave + low_particle == 1.0
    assert high_wave + high_particle == 1.0
    assert low_wave == high_particle
    assert low_particle == high_wave


@pytest.mark.parametrize(
    ("risk_score", "expected"),
    [
        (0.15, (0.9852259683067269, 0.014774031693273055)),
        (0.50, (0.5, 0.5)),
        (0.85, (0.014774031693273055, 0.9852259683067269)),
    ],
)
def test_guardrail_scenarios_match_sigmoid(risk_score, expected):
    assert calculate_state_weights(risk_score) == pytest.approx(expected)


@pytest.mark.parametrize("risk_score", (0.0, 0.15, 0.5, 0.85, 1.0))
def test_guardrail_matches_peer_review_after_rounding(risk_score):
    raw_weights = calculate_state_weights(risk_score)

    assert tuple(round(weight, 4) for weight in raw_weights) == calculate_equilibrium(
        risk_score
    )
    assert sum(raw_weights) == pytest.approx(1.0)


def test_guardrail_math_invariants_on_normalized_grid():
    risk_scores = tuple(index / 1000 for index in range(1001))
    weights = tuple(calculate_state_weights(risk) for risk in risk_scores)

    assert weights[500] == (0.5, 0.5)
    for index, (wave_weight, particle_weight) in enumerate(weights):
        peer_weights = calculate_equilibrium(risk_scores[index])
        assert 0.0 <= wave_weight <= 1.0
        assert 0.0 <= particle_weight <= 1.0
        assert wave_weight + particle_weight == pytest.approx(1.0, abs=1e-15)
        assert all(0.0 <= weight <= 1.0 for weight in peer_weights)
        assert sum(peer_weights) == pytest.approx(1.0, abs=1e-15)
        assert tuple(round(weight, 4) for weight in (wave_weight, particle_weight)) == (
            peer_weights
        )
        assert wave_weight + weights[1000 - index][0] == pytest.approx(
            1.0, abs=1e-15
        )
        if index < 1000:
            assert weights[index + 1][0] < wave_weight
            assert weights[index + 1][1] > particle_weight


def test_guardrail_matches_direct_sigmoid_formula():
    for index in range(101):
        risk_score = index / 100
        expected_wave = 1.0 / (1.0 + math.exp(12.0 * (risk_score - 0.5)))

        assert calculate_state_weights(risk_score)[0] == pytest.approx(
            expected_wave, rel=1e-14
        )


def test_guardrail_supports_custom_threshold_and_steepness():
    assert calculate_state_weights(0.25, r_critical=0.25) == (0.5, 0.5)
    assert calculate_state_weights(
        0.75, r_critical=0.5, steepness=4.0
    ) == pytest.approx((0.2689414213699951, 0.7310585786300049))
    assert calculate_state_weights(0.75, r_critical=0.5, steepness=4.0)[0] + (
        calculate_state_weights(0.25, r_critical=0.5, steepness=4.0)[0]
    ) == pytest.approx(1.0)


@pytest.mark.parametrize("risk_score", [-0.01, 1.01, True, float("nan"), float("inf")])
def test_peer_review_rejects_invalid_risk_scores(risk_score):
    with pytest.raises(ValueError, match="risk_score"):
        calculate_equilibrium(risk_score)


@pytest.mark.parametrize("risk_score", [-0.01, 1.01, True, float("nan"), float("inf")])
def test_guardrail_rejects_invalid_risk_scores(risk_score):
    with pytest.raises(ValueError, match="risk_score"):
        calculate_state_weights(risk_score)


@pytest.mark.parametrize("threshold", [-0.01, 1.01, True, float("nan"), float("inf")])
def test_guardrail_rejects_invalid_thresholds(threshold):
    with pytest.raises(ValueError, match="critical_threshold"):
        calculate_state_weights(0.5, r_critical=threshold)


@pytest.mark.parametrize("steepness", [0.0, -1.0, True, float("nan"), float("inf")])
def test_guardrail_rejects_invalid_steepness(steepness):
    with pytest.raises(ValueError, match="steepness"):
        calculate_state_weights(0.5, steepness=steepness)


def test_guardrail_handles_large_finite_steepness_without_overflow():
    assert calculate_state_weights(1.0, steepness=1e308) == (0.0, 1.0)


def test_peer_review_cli_prints_disclosure(capsys):
    assert main() == 0
    output = capsys.readouterr().out

    assert "Risk Input: 0.15" in output
    assert "Risk Input: 0.50" in output
    assert "Risk Input: 0.85" in output
    assert "does not prove physical wave-particle duality" in output
