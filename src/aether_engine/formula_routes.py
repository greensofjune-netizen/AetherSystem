from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .engine_core import EngineCapability, EngineOrchestrator
from .los_link import (
    PathProfilePoint,
    RadioLinkParameters,
    WeatherConditions,
    calculate_los_link_budget,
)
from .quantum_engine import (
    MAX_CIRCUIT_GATES,
    MAX_CIRCUIT_QUBITS,
    MAX_MEASUREMENT_SHOTS,
    QuantumGate,
    QuantumStateSimulator,
    StateCollapseAnomalyError,
)
from .spin_network_boundary import compute_spin_network_boundary

formula_router = APIRouter()
formula_engine = EngineOrchestrator()


class FormulaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuantumFormulaRequest(FormulaRequest):
    risk_coefficient: float = Field(default=0.3, ge=0, le=1, allow_inf_nan=False)
    fluctuation_velocity: float = Field(default=50, ge=0, allow_inf_nan=False)
    state_density: float = Field(default=57, ge=0, allow_inf_nan=False)


class QuantumGateRequest(FormulaRequest):
    operation: Literal["H", "X", "Y", "Z", "S", "T", "RX", "RY", "RZ", "CNOT", "CZ"]
    target: int = Field(strict=True, ge=0)
    control: int | None = Field(default=None, strict=True, ge=0)
    angle: float | None = Field(default=None, allow_inf_nan=False, strict=True)


class QuantumCircuitRequest(FormulaRequest):
    num_qubits: int = Field(strict=True, ge=1, le=MAX_CIRCUIT_QUBITS)
    gates: list[QuantumGateRequest] = Field(max_length=MAX_CIRCUIT_GATES)
    shots: int = Field(default=1000, strict=True, ge=1, le=MAX_MEASUREMENT_SHOTS)
    seed: int = Field(default=0, strict=True, ge=0, le=2**32 - 1)


class SpinNetworkFormulaRequest(FormulaRequest):
    num_links: int = Field(default=30, strict=True, ge=1, le=10_000)
    seed: int = Field(default=42, strict=True, ge=0, le=2**32 - 1)


class LosLinkFormulaRequest(FormulaRequest):
    tx_lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    tx_lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    tx_height_m: float = Field(ge=0, allow_inf_nan=False)
    rx_lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    rx_lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    rx_height_m: float = Field(ge=0, allow_inf_nan=False)
    freq_ghz: float = Field(default=5.8, gt=0, allow_inf_nan=False)
    path_profile: list[PathProfilePoint] | None = Field(default=None, max_length=512)
    weather: WeatherConditions | None = None
    radio: RadioLinkParameters | None = None


def _calculate_quantum(entry: QuantumFormulaRequest) -> dict[str, float]:
    simulator = QuantumStateSimulator(
        risk_coefficient=entry.risk_coefficient,
        fluctuation_velocity=entry.fluctuation_velocity,
    )
    try:
        entropy = simulator.calculate_entropy_index(entry.state_density)
    except StateCollapseAnomalyError as error:
        raise HTTPException(422, str(error)) from error
    return {
        "risk_coefficient": entry.risk_coefficient,
        "fluctuation_velocity": entry.fluctuation_velocity,
        "state_density": entry.state_density,
        "wave_coherence_percent": simulator.compute_wave_coherence(),
        "entropy_index": entropy,
    }


def _simulate_quantum_circuit(entry: QuantumCircuitRequest) -> dict[str, object]:
    gates = [
        QuantumGate(
            operation=gate.operation,
            target=gate.target,
            control=gate.control,
            angle=gate.angle,
        )
        for gate in entry.gates
    ]
    try:
        return QuantumStateSimulator().simulate_circuit(
            entry.num_qubits,
            gates,
            shots=entry.shots,
            seed=entry.seed,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


def _calculate_spin_network(entry: SpinNetworkFormulaRequest) -> dict[str, float | int]:
    try:
        spins, area, entropy = compute_spin_network_boundary(
            entry.num_links, entry.seed
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {
        "num_links": entry.num_links,
        "seed": entry.seed,
        "mean_spin": float(spins.mean()),
        "boundary_area_planck_squared": area,
        "entanglement_entropy_nats": entropy,
    }


def _calculate_los_link(entry: LosLinkFormulaRequest) -> dict[str, object]:
    try:
        return calculate_los_link_budget(
            tx_lat=entry.tx_lat,
            tx_lon=entry.tx_lon,
            tx_height_m=entry.tx_height_m,
            rx_lat=entry.rx_lat,
            rx_lon=entry.rx_lon,
            rx_height_m=entry.rx_height_m,
            freq_ghz=entry.freq_ghz,
            path_profile=entry.path_profile,
            weather=entry.weather,
            radio=entry.radio,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


QUANTUM_CAPABILITY = EngineCapability("formula.quantum", _calculate_quantum)
QUANTUM_CIRCUIT_CAPABILITY = EngineCapability(
    "formula.quantum-circuit", _simulate_quantum_circuit
)
SPIN_NETWORK_CAPABILITY = EngineCapability(
    "formula.spin-network", _calculate_spin_network
)
LOS_LINK_CAPABILITY = EngineCapability("formula.los-link", _calculate_los_link)
formula_engine.register(QUANTUM_CAPABILITY)
formula_engine.register(QUANTUM_CIRCUIT_CAPABILITY)
formula_engine.register(SPIN_NETWORK_CAPABILITY)
formula_engine.register(LOS_LINK_CAPABILITY)


@formula_router.post("/api/formulas/quantum")
def quantum_formula(entry: QuantumFormulaRequest, request: Request) -> dict[str, float]:
    return request.app.state.engine_runtime.execute(QUANTUM_CAPABILITY, entry)


@formula_router.post("/api/formulas/quantum-circuit")
def quantum_circuit_formula(
    entry: QuantumCircuitRequest, request: Request
) -> dict[str, object]:
    return request.app.state.engine_runtime.execute(QUANTUM_CIRCUIT_CAPABILITY, entry)


@formula_router.post("/api/formulas/spin-network")
def spin_network_formula(
    entry: SpinNetworkFormulaRequest, request: Request
) -> dict[str, float | int]:
    return request.app.state.engine_runtime.execute(SPIN_NETWORK_CAPABILITY, entry)


@formula_router.post("/api/formulas/los-link")
def los_link_formula(
    entry: LosLinkFormulaRequest, request: Request
) -> dict[str, object]:
    return request.app.state.engine_runtime.execute(LOS_LINK_CAPABILITY, entry)
