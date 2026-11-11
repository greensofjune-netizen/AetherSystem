from __future__ import annotations

import argparse
import json
from typing import Sequence

from .quantum_engine import (
    MAX_CIRCUIT_GATES,
    MAX_CIRCUIT_QUBITS,
    MAX_MEASUREMENT_SHOTS,
    QuantumGate,
    QuantumStateSimulator,
    StateCollapseAnomalyError,
)
from .system_diagnostics import (
    DiagnosticStatus,
    SystemDiagnosticCheck,
    SystemDiagnosticScanner,
    diagnostics_main,
)

__all__ = [
    "DiagnosticStatus",
    "MAX_CIRCUIT_GATES",
    "MAX_CIRCUIT_QUBITS",
    "MAX_MEASUREMENT_SHOTS",
    "QuantumGate",
    "QuantumStateSimulator",
    "StateCollapseAnomalyError",
    "SystemDiagnosticCheck",
    "SystemDiagnosticScanner",
    "diagnostics_main",
    "simulate_main",
]


def simulate_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aether-quantum-simulate",
        description="Simulate a bounded local state-vector quantum circuit.",
    )
    parser.add_argument("--qubits", type=int, required=True, help="Qubit count (1-12).")
    parser.add_argument(
        "--gates",
        required=True,
        metavar="JSON",
        help='Gate list, e.g. \'[{"operation":"H","target":0}]\'',
    )
    parser.add_argument(
        "--shots", type=int, default=1000, help="Measurements (1-10000)."
    )
    parser.add_argument("--seed", type=int, default=0, help="Reproducible shot seed.")
    arguments = parser.parse_args(argv)

    try:
        gate_data = json.loads(arguments.gates)
        if not isinstance(gate_data, list):
            raise ValueError("--gates must be a JSON array.")
        gates: list[QuantumGate] = []
        for item in gate_data:
            if not isinstance(item, dict):
                raise ValueError("Each gate must be a JSON object.")
            if set(item) - {"operation", "target", "control", "angle"}:
                raise ValueError("A gate contains an unsupported field.")
            gates.append(QuantumGate(**item))
        result = QuantumStateSimulator().simulate_circuit(
            arguments.qubits,
            gates,
            shots=arguments.shots,
            seed=arguments.seed,
        )
    except (TypeError, ValueError) as error:
        parser.error(str(error))

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    simulator = QuantumStateSimulator(risk_coefficient=0.30, fluctuation_velocity=50.0)
    simulator.render_operator_card(state_density=57.0)
