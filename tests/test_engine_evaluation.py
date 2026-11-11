from aether_engine.engine_core import EngineOrchestrator
from aether_engine.engine_runtime import EngineRuntime
from aether_engine.formula_routes import (
    QUANTUM_CAPABILITY,
    SPIN_NETWORK_CAPABILITY,
    QuantumFormulaRequest,
    SpinNetworkFormulaRequest,
)


def test_deterministic_formula_evaluation_regression():
    runtime = EngineRuntime(EngineOrchestrator())
    runtime.orchestrator.register(QUANTUM_CAPABILITY)
    runtime.orchestrator.register(SPIN_NETWORK_CAPABILITY)
    runtime.start()

    quantum = runtime.execute(
        QUANTUM_CAPABILITY,
        QuantumFormulaRequest(
            risk_coefficient=0.3,
            fluctuation_velocity=50,
            state_density=57,
        ),
    )
    spin_network = runtime.execute(
        SPIN_NETWORK_CAPABILITY,
        SpinNetworkFormulaRequest(num_links=12, seed=7),
    )

    assert quantum["wave_coherence_percent"] == 70.0
    assert quantum["entropy_index"] == 67.0
    assert spin_network["num_links"] == 12
    assert spin_network["seed"] == 7
    assert spin_network["mean_spin"] == 1.5416666666666667
    assert runtime.status()["metrics"]["total_operations"] == 2
    runtime.stop()
