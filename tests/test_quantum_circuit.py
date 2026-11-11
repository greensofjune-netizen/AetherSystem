import asyncio
import json
import math

import httpx
import pytest

from aether_engine.formula_routes import QuantumCircuitRequest
from aether_engine.quantum_engine import (
    MAX_CIRCUIT_GATES,
    MAX_CIRCUIT_QUBITS,
    MAX_MEASUREMENT_SHOTS,
    QuantumGate,
    QuantumStateSimulator,
)
from aether_engine.quantum_simulator import simulate_main


def states_by_label(result):
    return {state["state"]: state for state in result["state_vector"]}


def test_hadamard_and_cnot_create_a_bell_state():
    result = QuantumStateSimulator().simulate_circuit(
        2,
        [
            QuantumGate("H", target=0),
            QuantumGate("CNOT", target=1, control=0),
        ],
        shots=1000,
        seed=11,
    )

    states = states_by_label(result)
    assert states["00"]["probability"] == pytest.approx(0.5)
    assert states["11"]["probability"] == pytest.approx(0.5)
    assert states["01"]["probability"] == pytest.approx(0)
    assert states["10"]["probability"] == pytest.approx(0)
    assert sum(result["measurement_counts"].values()) == 1000
    assert set(result["measurement_counts"]) <= {"00", "11"}


def test_single_qubit_gates_and_rotation_follow_expected_state():
    simulator = QuantumStateSimulator()
    flipped = simulator.simulate_circuit(1, [QuantumGate("X", target=0)], shots=1)
    rotated = simulator.simulate_circuit(
        1, [QuantumGate("RY", target=0, angle=math.pi)], shots=1
    )

    assert states_by_label(flipped)["1"]["probability"] == pytest.approx(1)
    assert states_by_label(rotated)["1"]["probability"] == pytest.approx(1)
    assert states_by_label(rotated)["0"]["probability"] == pytest.approx(0)


@pytest.mark.parametrize(
    ("gates", "state", "amplitude"),
    [
        ([QuantumGate("Y", target=0)], "1", 1j),
        ([QuantumGate("X", target=0), QuantumGate("Z", target=0)], "1", -1 + 0j),
        ([QuantumGate("X", target=0), QuantumGate("S", target=0)], "1", 1j),
        (
            [QuantumGate("X", target=0), QuantumGate("T", target=0)],
            "1",
            complex(math.cos(math.pi / 4), math.sin(math.pi / 4)),
        ),
        ([QuantumGate("RX", target=0, angle=math.pi)], "1", -1j),
        ([QuantumGate("RY", target=0, angle=math.pi)], "1", 1 + 0j),
        (
            [QuantumGate("X", target=0), QuantumGate("RZ", target=0, angle=math.pi)],
            "1",
            1j,
        ),
    ],
)
def test_supported_single_qubit_gates_have_expected_amplitudes(gates, state, amplitude):
    result = QuantumStateSimulator().simulate_circuit(1, gates, shots=1)
    actual = states_by_label(result)[state]

    assert actual["real"] == pytest.approx(amplitude.real)
    assert actual["imaginary"] == pytest.approx(amplitude.imag)


def test_controlled_z_applies_phase_only_to_joint_one_state():
    result = QuantumStateSimulator().simulate_circuit(
        2,
        [
            QuantumGate("H", target=0),
            QuantumGate("H", target=1),
            QuantumGate("CZ", target=1, control=0),
        ],
        shots=1,
    )

    states = states_by_label(result)
    assert states["00"]["real"] == pytest.approx(0.5)
    assert states["01"]["real"] == pytest.approx(0.5)
    assert states["10"]["real"] == pytest.approx(0.5)
    assert states["11"]["real"] == pytest.approx(-0.5)


def test_measurement_is_reproducible_from_seed():
    simulator = QuantumStateSimulator()
    gates = [QuantumGate("H", target=0)]

    first = simulator.simulate_circuit(1, gates, shots=500, seed=27)
    second = simulator.simulate_circuit(1, gates, shots=500, seed=27)

    assert first["measurement_counts"] == second["measurement_counts"]
    assert first["measurement_counts"]["0"] + first["measurement_counts"]["1"] == 500


def test_maximum_supported_circuit_and_request_bounds_are_accepted():
    simulator = QuantumStateSimulator()
    max_qubit_result = simulator.simulate_circuit(MAX_CIRCUIT_QUBITS, [], shots=1)
    max_gate_result = simulator.simulate_circuit(
        1, [QuantumGate("Z", target=0)] * MAX_CIRCUIT_GATES, shots=1
    )
    max_shot_result = simulator.simulate_circuit(1, [], shots=MAX_MEASUREMENT_SHOTS)

    assert len(max_qubit_result["state_vector"]) == 2**MAX_CIRCUIT_QUBITS
    assert sum(
        state["probability"] for state in max_qubit_result["state_vector"]
    ) == pytest.approx(1)
    assert max_gate_result["gate_count"] == MAX_CIRCUIT_GATES
    assert sum(max_shot_result["measurement_counts"].values()) == MAX_MEASUREMENT_SHOTS


@pytest.mark.parametrize(
    ("qubits", "gates", "kwargs", "message"),
    [
        (MAX_CIRCUIT_QUBITS + 1, [], {}, "num_qubits"),
        (1, [QuantumGate("CNOT", target=0, control=0)], {}, "control qubit"),
        (1, [QuantumGate("H", target=0, angle=1)], {}, "does not accept an angle"),
        (1, [QuantumGate("RX", target=0)], {}, "requires a finite angle"),
        (1, [QuantumGate("Z", target=0)] * (MAX_CIRCUIT_GATES + 1), {}, "gates"),
        (1, [], {"shots": MAX_MEASUREMENT_SHOTS + 1}, "shots"),
        (1, [], {"seed": -1}, "seed"),
    ],
)
def test_invalid_circuit_inputs_are_rejected(qubits, gates, kwargs, message):
    with pytest.raises(ValueError, match=message):
        QuantumStateSimulator().simulate_circuit(qubits, gates, **kwargs)


def test_cli_emits_json_statevector(capsys):
    assert (
        simulate_main(
            [
                "--qubits",
                "1",
                "--gates",
                '[{"operation":"H","target":0}]',
                "--shots",
                "10",
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["num_qubits"] == 1
    assert output["gate_count"] == 1
    assert sum(output["measurement_counts"].values()) == 10


def test_api_model_rejects_boolean_rotation_angles():
    with pytest.raises(ValueError):
        QuantumCircuitRequest(
            num_qubits=1,
            gates=[{"operation": "RX", "target": 0, "angle": True}],
        )


def test_quantum_circuit_endpoint_and_formula_lab_are_available(tmp_path):
    from aether_engine.calculator_api import create_app
    from aether_engine.galileo import create_app as create_galileo_app

    app = create_app(token="test-token")
    galileo_app = create_galileo_app(tmp_path / "galileo", token="test")

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
            base_url="http://127.0.0.1",
        ) as client:
            response = await client.post(
                "/api/formulas/quantum-circuit",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "num_qubits": 2,
                    "gates": [
                        {"operation": "H", "target": 0},
                        {"operation": "CNOT", "target": 1, "control": 0},
                    ],
                    "shots": 64,
                    "seed": 3,
                },
            )
            assert response.status_code == 200
            data = response.json()
            states = {item["state"]: item for item in data["state_vector"]}
            assert states["00"]["probability"] == pytest.approx(0.5)
            assert states["11"]["probability"] == pytest.approx(0.5)
            assert sum(data["measurement_counts"].values()) == 64

            invalid = await client.post(
                "/api/formulas/quantum-circuit",
                headers={"Authorization": "Bearer test-token"},
                json={"num_qubits": MAX_CIRCUIT_QUBITS + 1, "gates": []},
            )
            assert invalid.status_code == 422

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=galileo_app, client=("127.0.0.1", 1)),
            base_url="http://127.0.0.1",
            cookies={"galileo_session": "test"},
        ) as client:
            page = await client.get("/")
            assert page.status_code == 200
            assert 'id="quantum-circuit-form"' in page.text
            assert "/api/formulas/quantum-circuit" in page.text

    asyncio.run(check())
