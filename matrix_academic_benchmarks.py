"""Reproducible local policy checks and a synthetic CPU timing benchmark.

Passing results are software-test evidence only; this module does not certify
physical, scientific, medical, ecological, or ethical outcomes.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from typing import Any

from aether_engine.autonomy_policy import (
    AUTONOMY_POLICY_VERSION,
    AutonomyAction,
    AutonomyStatus,
    authorize_agent_capability,
    evaluate_autonomy,
)

BENCHMARK_VERSION = "2026.11-OPEN"
DEFAULT_NODE_ID = "LOCAL-ACADEMIC-BENCHMARK"
MAX_SIM_CYCLES = 100_000
_POLICY_CASES = (
    (
        "known_local_read",
        lambda: authorize_agent_capability("matrix_snapshot").status,
        AutonomyStatus.ALLOWED,
    ),
    (
        "configured_public_read",
        lambda: authorize_agent_capability("visible_stars").status,
        AutonomyStatus.ALLOWED,
    ),
    (
        "archive_without_opt_in",
        lambda: authorize_agent_capability("search_history").status,
        AutonomyStatus.REQUIRES_USER_SCOPE,
    ),
    (
        "archive_with_opt_in",
        lambda: authorize_agent_capability(
            "search_history", scope_opted_in=True
        ).status,
        AutonomyStatus.ALLOWED,
    ),
    (
        "unknown_capability",
        lambda: authorize_agent_capability("device.control").status,
        AutonomyStatus.BLOCKED,
    ),
    (
        "local_mutation_without_approval",
        lambda: evaluate_autonomy(AutonomyAction.LOCAL_MUTATION).status,
        AutonomyStatus.REQUIRES_HUMAN_APPROVAL,
    ),
    (
        "external_write_without_approval",
        lambda: evaluate_autonomy(AutonomyAction.EXTERNAL_WRITE).status,
        AutonomyStatus.REQUIRES_HUMAN_APPROVAL,
    ),
    (
        "physical_action_without_interlock",
        lambda: evaluate_autonomy(
            AutonomyAction.PHYSICAL_ACTUATION,
            human_approved=True,
            hardware_interlocks_verified=False,
        ).status,
        AutonomyStatus.BLOCKED,
    ),
    (
        "medical_decision_even_with_approval",
        lambda: evaluate_autonomy(
            AutonomyAction.MEDICAL_DECISION, human_approved=True
        ).status,
        AutonomyStatus.BLOCKED,
    ),
    (
        "harmful_action_even_with_approval",
        lambda: evaluate_autonomy(
            AutonomyAction.HARMFUL_ACTION, human_approved=True
        ).status,
        AutonomyStatus.BLOCKED,
    ),
)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class MatrixAcademicBenchmarkSuite:
    """Run bounded, local-only academic policy and synthetic CPU checks."""

    def __init__(
        self, node_id: str = DEFAULT_NODE_ID, benchmark_version: str = BENCHMARK_VERSION
    ) -> None:
        if not isinstance(node_id, str) or not node_id.strip() or len(node_id) > 100:
            raise ValueError("node_id must contain 1 to 100 characters.")
        if (
            not isinstance(benchmark_version, str)
            or not benchmark_version.strip()
            or len(benchmark_version) > 40
        ):
            raise ValueError("benchmark_version must contain 1 to 40 characters.")
        self.node_id = node_id.strip()
        self.version = benchmark_version.strip()
        self.audit_logs: list[dict[str, Any]] = []

    def run(
        self, *, sim_cycles: int = 1000, target_latency_ms: float = 1.5
    ) -> dict[str, Any]:
        if type(sim_cycles) is not int or not 1 <= sim_cycles <= MAX_SIM_CYCLES:
            raise ValueError(f"sim_cycles must be between 1 and {MAX_SIM_CYCLES}.")
        if (
            isinstance(target_latency_ms, bool)
            or not isinstance(target_latency_ms, (int, float))
            or not math.isfinite(target_latency_ms)
            or target_latency_ms <= 0
        ):
            raise ValueError("target_latency_ms must be a finite positive number.")

        policy_results = []
        for case_name, check, expected in _POLICY_CASES:
            observed = check().value
            policy_results.append({
                "case": case_name,
                "expected": expected.value,
                "observed": observed,
                "passed": observed == expected.value,
            })
        latencies_ms: list[float] = []
        workload_digest = hashlib.sha256()
        for cycle in range(sim_cycles):
            payload = f"{self.node_id}:{cycle}".encode("utf-8")
            started_ns = time.perf_counter_ns()
            workload_digest.update(hashlib.sha256(payload).digest())
            latencies_ms.append((time.perf_counter_ns() - started_ns) / 1_000_000)

        ordered_latencies = sorted(latencies_ms)
        p99_index = max(0, math.ceil(sim_cycles * 0.99) - 1)
        mean_latency = statistics.fmean(latencies_ms)
        p99_latency = ordered_latencies[p99_index]
        policy_passed = all(item["passed"] for item in policy_results)
        deterministic_evidence = {
            "benchmark_version": self.version,
            "autonomy_policy_version": AUTONOMY_POLICY_VERSION,
            "node_id": self.node_id,
            "node_id_status": "UNVERIFIED_LABEL",
            "cycles_executed": sim_cycles,
            "workload": "synthetic SHA-256 operations; no physical system measured",
            "workload_digest_sha256": workload_digest.hexdigest(),
            "policy_cases": policy_results,
        }
        report: dict[str, Any] = {
            **deterministic_evidence,
            "mean_workload_latency_ms": round(mean_latency, 6),
            "p99_workload_latency_ms": round(p99_latency, 6),
            "target_latency_ms": float(target_latency_ms),
            "latency_target_met": p99_latency <= target_latency_ms,
            "policy_cases_passed": sum(item["passed"] for item in policy_results),
            "policy_case_count": len(policy_results),
            "policy_tests_passed": policy_passed,
            "closed_loop_recovery": {
                "status": "NOT_MEASURED",
                "value_pct": None,
                "reason": (
                    "No thermodynamic, material-recovery, or laboratory apparatus "
                    "is connected to this software benchmark."
                ),
            },
            "hardware_measurements": "NOT_PERFORMED",
            "public_certification_status": "NOT_A_CERTIFICATION",
            "benchmark_status": (
                "LOCAL_POLICY_TESTS_PASS_NOT_CERTIFICATION"
                if policy_passed
                else "LOCAL_POLICY_TESTS_FAILED"
            ),
            "reproducibility_sha256": _canonical_sha256(deterministic_evidence),
            "report_integrity_sha256": "",
            "integrity_note": (
                "SHA-256 detects report-byte changes; it is not a signature, "
                "identity proof, independent replication, or truth guarantee."
            ),
        }
        report["report_integrity_sha256"] = _canonical_sha256(
            {key: value for key, value in report.items() if key != "report_integrity_sha256"}
        )
        self.audit_logs.append(report)
        del self.audit_logs[:-200]
        return report
