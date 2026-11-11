import numpy as np
import pytest

from aether_engine.spin_network_boundary import (
    calculate_spin_network_boundary,
    compute_spin_network_boundary,
    main,
)


def test_boundary_compute_helper_returns_results_without_console_output(capsys):
    spins, area, entropy = compute_spin_network_boundary(num_links=4, seed=7)

    assert len(spins) == 4
    assert area > 0
    assert entropy == area / 4
    assert capsys.readouterr().out == ""


def test_boundary_calculation_is_seeded_and_returns_expected_values(capsys):
    spins, area, entropy = calculate_spin_network_boundary(num_links=30, seed=42)
    repeated_spins, repeated_area, repeated_entropy = calculate_spin_network_boundary(
        num_links=30,
        seed=42,
    )

    np.testing.assert_array_equal(spins, repeated_spins)
    assert area == repeated_area
    assert entropy == repeated_entropy
    assert len(spins) == 30
    expected_area = 8 * np.pi * 0.2375 * np.sum(np.sqrt(spins * (spins + 1)))
    np.testing.assert_allclose(area, expected_area)
    assert np.isclose(entropy, area / 4)
    assert "Total Active Boundary Punctures  : 30" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("num_links", "seed"),
    [(0, 42), (-1, 42), (1, -1), (1, 2**32)],
)
def test_boundary_calculation_rejects_invalid_parameters(num_links, seed):
    with pytest.raises(ValueError):
        calculate_spin_network_boundary(num_links, seed)


def test_cli_runs_with_custom_parameters(capsys):
    assert main(["--num-links", "4", "--seed", "7"]) == 0
    assert "Total Active Boundary Punctures  : 4" in capsys.readouterr().out
