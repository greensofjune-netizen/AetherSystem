"""AetherSystem macro cosmic action engine.

Implements unified gravitational metrics with quantum bounce boundaries.
"""

from math import isfinite
from typing import Literal, TypedDict

import numpy as np


class MacroActionResult(TypedDict):
    """Result fields returned by :meth:`AetherQuantumEngine.evaluate_macro_action`."""

    bounce_active: bool
    total_action_density: float
    metric_status: Literal["EQUILIBRIUM", "CRITICAL_PRESSURE"]


class AetherQuantumEngine:
    """Evaluate macro action density and quantum bounce boundary conditions."""

    def __init__(self, alpha: float = 0.5, gamma_bounce: float = 0.2375) -> None:
        if not isfinite(alpha):
            raise ValueError("alpha must be finite")
        if not isfinite(gamma_bounce):
            raise ValueError("gamma_bounce must be finite")

        self.alpha = alpha
        self.gamma_bounce = gamma_bounce
        self.system_stable = True

    def evaluate_macro_action(
        self,
        scale_factor: float,
        scalar_density: float,
        curvature_r: float,
    ) -> MacroActionResult:
        """Calculate unified action density and whether a bounce is triggered."""
        if not isfinite(scale_factor) or scale_factor <= 0.0:
            raise ValueError("scale_factor must be finite and greater than zero")
        if not isfinite(scalar_density):
            raise ValueError("scalar_density must be finite")
        if not isfinite(curvature_r):
            raise ValueError("curvature_r must be finite")

        base_eh = curvature_r / (16.0 * np.pi)
        quadratic_guardrail = self.alpha * curvature_r**2

        if scale_factor <= 0.1:
            bounce_inversion = (self.gamma_bounce * 100.0) / (scale_factor + 1e-5)
            bounce_triggered = True
        else:
            bounce_inversion = self.gamma_bounce / scale_factor**2
            bounce_triggered = False

        total_action = base_eh + quadratic_guardrail + bounce_inversion + scalar_density
        if not isfinite(total_action):
            raise ValueError("calculated action density is not finite")

        return {
            "bounce_active": bounce_triggered,
            "total_action_density": float(total_action),
            "metric_status": (
                "EQUILIBRIUM" if total_action < 1e6 else "CRITICAL_PRESSURE"
            ),
        }
