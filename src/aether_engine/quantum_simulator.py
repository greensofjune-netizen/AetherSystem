from __future__ import annotations

from typing import Final


class StateCollapseAnomalyError(Exception):
    """Raised when the simulated entropy index exceeds threshold stability boundaries."""
    pass


class QuantumStateSimulator:
    def __init__(
        self, risk_coefficient: float = 0.30, fluctuation_velocity: float = 50.0
    ) -> None:
        """Initialize the simulator engine with user-adjustable wave characteristics."""
        self.risk_coefficient: float = risk_coefficient
        self.fluctuation_velocity: float = fluctuation_velocity
        self.entropy_max: Final[float] = 100.0

    def compute_wave_coherence(self) -> float:
        """Calculate the localized phase coherence percentage of the system matrix."""
        base_coherence = 1.0 - self.risk_coefficient
        return round(base_coherence * 100.0, 1)

    def calculate_entropy_index(self, state_density: float) -> float:
        """Evaluate the structural thermal entropy metric of the fluid environment."""
        calculated_entropy = (state_density * 0.5) + (self.fluctuation_velocity * 0.77)
        bounded_entropy = min(calculated_entropy, self.entropy_max)

        if bounded_entropy > 95.0:
            raise StateCollapseAnomalyError(
                f"System critical decoherence imminent at entropy: {bounded_entropy}"
            )

        return round(bounded_entropy, 1)

    def render_operator_card(self, state_density: float = 57.0) -> None:
        """Render a stylized, high-impact telemetry reporting card to the system console."""
        coherence = self.compute_wave_coherence()
        entropy = self.calculate_entropy_index(state_density)

        print("\n" + "=" * 55)
        print(" 🌌 AETHER COHERENT SUPERPOSITION STATUS ENGINE 🌌")
        print("=" * 55)
        print(f"  • Wave Coherence   : {coherence}%  [TARGET MATCH]")
        print(f"  • State Density    : {state_density}ψ")
        print(f"  • Entropy Index    : {entropy}   (Stability Threshold: 95.0)")
        print("-" * 55)
        print(
            f"  • Risk Coefficient : {int(self.risk_coefficient * 100)}% "
            "(Wave Collapse Rate)"
        )
        print(
            f"  • System Velocity  : {int(self.fluctuation_velocity)}Hz "
            "(Fluctuation Cycle)"
        )
        print("  • Strategy Pattern : DYNAMIC BALANCE CONFIGURATION")
        print("=" * 55 + "\n")


if __name__ == "__main__":
    simulator = QuantumStateSimulator(risk_coefficient=0.30, fluctuation_velocity=50.0)
    simulator.render_operator_card(state_density=57.0)
