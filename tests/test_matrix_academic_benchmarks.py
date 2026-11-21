from __future__ import annotations

import hashlib
import json

import pytest

from matrix_academic_benchmarks import MatrixAcademicBenchmarkSuite


def test_benchmark_reports_policy_cases_without_claiming_certification() -> None:
    report = MatrixAcademicBenchmarkSuite().run(sim_cycles=25)

    assert report["policy_tests_passed"] is True
    assert report["policy_cases_passed"] == report["policy_case_count"] == 10
    assert report["benchmark_status"] == "LOCAL_POLICY_TESTS_PASS_NOT_CERTIFICATION"
    assert report["public_certification_status"] == "NOT_A_CERTIFICATION"
    assert report["closed_loop_recovery"] == {
        "status": "NOT_MEASURED",
        "value_pct": None,
        "reason": (
            "No thermodynamic, material-recovery, or laboratory apparatus "
            "is connected to this software benchmark."
        ),
    }
    assert report["hardware_measurements"] == "NOT_PERFORMED"
    assert len(report["reproducibility_sha256"]) == 64
    assert len(report["report_integrity_sha256"]) == 64
    expected_integrity = hashlib.sha256(
        json.dumps(
            {key: value for key, value in report.items()
             if key != "report_integrity_sha256"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert report["report_integrity_sha256"] == expected_integrity


def test_deterministic_evidence_repeats_and_report_integrity_is_recomputable() -> None:
    suite = MatrixAcademicBenchmarkSuite(node_id="RESEARCH-NODE")
    first = suite.run(sim_cycles=12)
    second = suite.run(sim_cycles=12)

    assert first["reproducibility_sha256"] == second["reproducibility_sha256"]
    assert first["workload_digest_sha256"] == second["workload_digest_sha256"]
    assert first["policy_cases"] == second["policy_cases"]
    assert first["report_integrity_sha256"] != ""
    assert second["report_integrity_sha256"] != ""
    assert suite.audit_logs == [first, second]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sim_cycles": 0},
        {"sim_cycles": 100_001},
        {"sim_cycles": True},
        {"target_latency_ms": 0},
        {"target_latency_ms": float("inf")},
        {"target_latency_ms": True},
    ],
)
def test_benchmark_rejects_invalid_or_unbounded_inputs(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        MatrixAcademicBenchmarkSuite().run(**kwargs)


@pytest.mark.parametrize(
    ("node_id", "version"),
    [("", "v1"), ("x" * 101, "v1"), ("node", ""), ("node", "x" * 41)],
)
def test_benchmark_rejects_invalid_identity_metadata(node_id: str, version: str) -> None:
    with pytest.raises(ValueError):
        MatrixAcademicBenchmarkSuite(node_id, version)
