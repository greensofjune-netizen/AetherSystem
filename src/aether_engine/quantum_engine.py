from __future__ import annotations

import cmath
import random
from bisect import bisect_left
from dataclasses import dataclass
from math import cos, isfinite, pi, sin, sqrt
from typing import Final, Sequence


class StateCollapseAnomalyError(Exception):
    """Raised when the simulated entropy index exceeds stability boundaries."""


MAX_CIRCUIT_QUBITS = 12
MAX_CIRCUIT_GATES = 256
MAX_MEASUREMENT_SHOTS = 10_000


@dataclass(frozen=True)
class QuantumGate:
    """A single-qubit gate or a controlled two-qubit gate."""

    operation: str
    target: int
    control: int | None = None
    angle: float | None = None


class QuantumStateSimulator:
    def __init__(
        self, risk_coefficient: float = 0.30, fluctuation_velocity: float = 50.0
    ) -> None:
        """Initialize the simulator with user-adjustable wave characteristics."""
        self.risk_coefficient: float = risk_coefficient
        self.fluctuation_velocity: float = fluctuation_velocity
        self.entropy_max: Final[float] = 100.0

    def simulate_circuit(
        self,
        num_qubits: int,
        gates: Sequence[QuantumGate],
        *,
        shots: int = 1000,
        seed: int = 0,
    ) -> dict[str, object]:
        """Simulate a bounded state-vector circuit and seeded computational-basis shots.

        Qubit 0 is the least-significant state-vector bit. Output labels are
        displayed most-significant bit first, as conventional bit strings.
        """
        if type(num_qubits) is not int or not 1 <= num_qubits <= MAX_CIRCUIT_QUBITS:
            raise ValueError(f"num_qubits must be between 1 and {MAX_CIRCUIT_QUBITS}.")
        if not isinstance(gates, Sequence) or isinstance(gates, (str, bytes)):
            raise ValueError("gates must be a sequence of QuantumGate values.")
        if len(gates) > MAX_CIRCUIT_GATES:
            raise ValueError(
                f"gates cannot contain more than {MAX_CIRCUIT_GATES} items."
            )
        if type(shots) is not int or not 1 <= shots <= MAX_MEASUREMENT_SHOTS:
            raise ValueError(f"shots must be between 1 and {MAX_MEASUREMENT_SHOTS}.")
        if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
            raise ValueError("seed must be between 0 and 4294967295.")

        dimension = 1 << num_qubits
        amplitudes = [0j] * dimension
        amplitudes[0] = 1 + 0j

        fixed_gates = {"H", "X", "Y", "Z", "S", "T"}
        rotation_gates = {"RX", "RY", "RZ"}
        controlled_gates = {"CNOT", "CZ"}
        for gate in gates:
            if not isinstance(gate, QuantumGate):
                raise ValueError("Each circuit gate must be a QuantumGate value.")
            if not isinstance(gate.operation, str):
                raise ValueError("Gate operation must be text.")
            operation = gate.operation.upper()
            if operation not in fixed_gates | rotation_gates | controlled_gates:
                raise ValueError(f"Unsupported gate operation: {gate.operation!r}.")
            if type(gate.target) is not int or not 0 <= gate.target < num_qubits:
                raise ValueError("Gate target must be a valid qubit index.")

            if operation in controlled_gates:
                control = gate.control
                if (
                    control is None
                    or type(control) is not int
                    or not 0 <= control < num_qubits
                    or control == gate.target
                    or gate.angle is not None
                ):
                    raise ValueError(
                        f"{operation} requires a distinct valid control qubit "
                        "and no angle."
                    )
            elif gate.control is not None:
                raise ValueError(f"{operation} does not accept a control qubit.")

            if operation in rotation_gates:
                if (
                    isinstance(gate.angle, bool)
                    or not isinstance(gate.angle, (int, float))
                    or not isfinite(gate.angle)
                ):
                    raise ValueError(f"{operation} requires a finite angle in radians.")
            elif operation in fixed_gates and gate.angle is not None:
                raise ValueError(f"{operation} does not accept an angle.")

            if operation in controlled_gates:
                control = gate.control
                if control is None:
                    raise ValueError(f"{operation} requires a control qubit.")
                control_mask = 1 << control
                target_mask = 1 << gate.target
                if operation == "CNOT":
                    for index in range(dimension):
                        if index & control_mask and not index & target_mask:
                            partner = index | target_mask
                            amplitudes[index], amplitudes[partner] = (
                                amplitudes[partner],
                                amplitudes[index],
                            )
                else:
                    for index in range(dimension):
                        if index & control_mask and index & target_mask:
                            amplitudes[index] = -amplitudes[index]
                continue

            if operation == "H":
                scale = 1 / sqrt(2)
                matrix: tuple[complex, complex, complex, complex] = (
                    scale,
                    scale,
                    scale,
                    -scale,
                )
            elif operation == "X":
                matrix = (0j, 1 + 0j, 1 + 0j, 0j)
            elif operation == "Y":
                matrix = (0j, -1j, 1j, 0j)
            elif operation == "Z":
                matrix = (1 + 0j, 0j, 0j, -1 + 0j)
            elif operation == "S":
                matrix = (1 + 0j, 0j, 0j, 1j)
            elif operation == "T":
                matrix = (1 + 0j, 0j, 0j, cmath.exp(1j * pi / 4))
            else:
                angle = gate.angle
                if (
                    angle is None
                    or isinstance(angle, bool)
                    or not isinstance(angle, (int, float))
                    or not isfinite(angle)
                ):
                    raise ValueError(f"{operation} requires a finite angle in radians.")
                angle = float(angle)
                half_angle = angle / 2
                if operation == "RX":
                    diagonal = cos(half_angle)
                    off_diagonal = -1j * sin(half_angle)
                    matrix = (diagonal, off_diagonal, off_diagonal, diagonal)
                elif operation == "RY":
                    diagonal = cos(half_angle)
                    matrix = (
                        diagonal,
                        -sin(half_angle),
                        sin(half_angle),
                        diagonal,
                    )
                else:
                    matrix = (
                        cmath.exp(-1j * half_angle),
                        0j,
                        0j,
                        cmath.exp(1j * half_angle),
                    )

            stride = 1 << gate.target
            for block in range(0, dimension, stride * 2):
                for offset in range(stride):
                    zero_index = block + offset
                    one_index = zero_index + stride
                    zero_amplitude = amplitudes[zero_index]
                    one_amplitude = amplitudes[one_index]
                    amplitudes[zero_index] = (
                        matrix[0] * zero_amplitude + matrix[1] * one_amplitude
                    )
                    amplitudes[one_index] = (
                        matrix[2] * zero_amplitude + matrix[3] * one_amplitude
                    )

        probabilities = [
            amplitude.real**2 + amplitude.imag**2 for amplitude in amplitudes
        ]
        total_probability = sum(probabilities)
        if not isfinite(total_probability) or abs(total_probability - 1.0) > 1e-9:
            raise ArithmeticError(
                "Circuit simulation produced an invalid state vector."
            )
        probabilities = [
            probability / total_probability for probability in probabilities
        ]

        cumulative: list[float] = []
        running_probability = 0.0
        for probability in probabilities:
            running_probability += probability
            cumulative.append(running_probability)
        cumulative[-1] = 1.0
        rng = random.Random(seed)
        counts: dict[str, int] = {}
        for _ in range(shots):
            outcome = min(
                bisect_left(cumulative, rng.random()),
                dimension - 1,
            )
            label = format(outcome, f"0{num_qubits}b")
            counts[label] = counts.get(label, 0) + 1

        state_vector = [
            {
                "state": format(index, f"0{num_qubits}b"),
                "real": round(amplitude.real, 12),
                "imaginary": round(amplitude.imag, 12),
                "probability": round(probabilities[index], 12),
            }
            for index, amplitude in enumerate(amplitudes)
        ]
        return {
            "num_qubits": num_qubits,
            "gate_count": len(gates),
            "shots": shots,
            "seed": seed,
            "state_vector": state_vector,
            "measurement_counts": dict(sorted(counts.items())),
        }

    def compute_wave_coherence(self) -> float:
        """Calculate the localized phase coherence percentage."""
        base_coherence = 1.0 - self.risk_coefficient
        return round(base_coherence * 100.0, 1)

    def calculate_entropy_index(self, state_density: float) -> float:
        """Evaluate the structural thermal entropy metric."""
        calculated_entropy = (state_density * 0.5) + (self.fluctuation_velocity * 0.77)
        bounded_entropy = min(calculated_entropy, self.entropy_max)

        if bounded_entropy > 95.0:
            raise StateCollapseAnomalyError(
                f"System critical decoherence imminent at entropy: {bounded_entropy}"
            )

        return round(bounded_entropy, 1)

    def render_operator_card(self, state_density: float = 57.0) -> None:
        """Render a telemetry card for the current simulated state."""
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
