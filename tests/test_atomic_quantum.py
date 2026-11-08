import numpy as np

from aether_engine.atomic_quantum import AtomicQuantumBoundary


def test_spin_link_coupling_matches_quantized_area_entropy():
    boundary = AtomicQuantumBoundary()

    result = boundary.compute_spin_link_coupling(num_links=30, mean_j=1.5)

    expected = 8 * np.pi * 0.2375 * 30 * np.sqrt(1.5 * (1.5 + 1)) / 4
    assert result == float(expected)


def test_boundary_stores_custom_baseline_entropy():
    boundary = AtomicQuantumBoundary(baseline_entropy=123.4)

    assert boundary.baseline == 123.4


def test_zero_links_produce_zero_coupling():
    result = AtomicQuantumBoundary().compute_spin_link_coupling(
        num_links=0,
        mean_j=1.5,
    )

    assert result == 0.0
