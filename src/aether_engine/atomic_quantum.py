"""Atomic quantum boundary calculations."""

import numpy as np


class AtomicQuantumBoundary:
    def __init__(self, baseline_entropy: float = 145.2586) -> None:
        self.baseline = baseline_entropy

    def compute_spin_link_coupling(self, num_links: int, mean_j: float) -> float:
        """Return the localized entropy bound for the spin-link boundary."""
        gamma = 0.2375
        quantized_area = (
            8 * np.pi * gamma * num_links * np.sqrt(mean_j * (mean_j + 1))
        )
        return float(quantized_area / 4.0)
