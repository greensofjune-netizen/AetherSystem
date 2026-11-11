"""Calculate a seeded spin-network boundary area and entropy."""

import argparse
from collections.abc import Sequence

import numpy as np


def compute_spin_network_boundary(
    num_links: int = 30,
    seed: int = 42,
) -> tuple[np.ndarray, float, float]:
    """Return seeded boundary spins, quantized area, and entropy without output."""
    if num_links < 1:
        raise ValueError("num_links must be at least 1")
    if seed < 0 or seed > 2**32 - 1:
        raise ValueError("seed must be between 0 and 4294967295")

    gamma = 0.2375
    allowed_spins = np.array([0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
    j_punctures = np.random.RandomState(seed).choice(allowed_spins, size=num_links)

    area_quanta = np.sqrt(j_punctures * (j_punctures + 1))
    total_area_planck = float(8 * np.pi * gamma * np.sum(area_quanta))
    entanglement_entropy_nats = total_area_planck / 4.0
    return j_punctures, total_area_planck, entanglement_entropy_nats


def calculate_spin_network_boundary(
    num_links: int = 30,
    seed: int = 42,
) -> tuple[np.ndarray, float, float]:
    """Compute quantized area and entropy for randomly selected boundary spins."""
    j_punctures, total_area_planck, entanglement_entropy_nats = (
        compute_spin_network_boundary(num_links, seed)
    )

    print("=== SYSTEM CORE: SPIN NETWORK QUANTIZATION ===")
    print(f"Total Active Boundary Punctures  : {num_links}")
    print(f"Mean Spin Magnitude ⟨j⟩          : {np.mean(j_punctures):.2f}")
    print(f"Quantized Boundary Area (A)      : {total_area_planck:.4f} ℓ_P²")
    print(f"Entanglement Entropy (S_vN)     : {entanglement_entropy_nats:.4f} Nats")
    print("==============================================")

    return j_punctures, total_area_planck, entanglement_entropy_nats


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num-links", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    try:
        calculate_spin_network_boundary(args.num_links, args.seed)
    except ValueError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
