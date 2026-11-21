from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

MAX_LEDGER_ENTRIES = 1_000
MAX_LEDGER_BYTES = 2_000_000
_LEDGER_LOCK = RLock()
_ENTRY_STATUSES = {
    "VERIFIED",
    "PARTIALLY_VERIFIED",
    "NOT_VERIFIED",
    "UNKNOWN",
    "NOT_MEASURED",
    "PREPARATION_ONLY",
    "FAILED",
}
_CHECK_IDS = {
    "matrix-policy-benchmark",
    "recovery-readiness-snapshot",
    "host-usb-enumeration",
}
_USB_NODE_PATTERN = re.compile(
    r"^\s*\+-o\s+(.+?)\s+<class IOUSBHostDevice,[^\n]*",
    re.MULTILINE,
)


class EvidenceLedgerError(RuntimeError):
    pass


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def evidence_ledger_path() -> Path:
    configured = os.environ.get("AETHER_MATRIX_EVIDENCE_LEDGER_FILE")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".aether-engine" / "matrix-evidence-ledger.json"


class MatrixEvidenceLedger:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = (
            Path(path).expanduser() if path is not None else evidence_ledger_path()
        )

    def snapshot(self, *, limit: int = 50) -> dict[str, object]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100.")
        with _LEDGER_LOCK:
            entries = self._read_entries()
        return {
            "integrity_status": ("HASH_CHAIN_VALID_NOT_SIGNED" if entries else "EMPTY"),
            "entries": entries[-limit:],
        }

    def record_benchmark(self, report: Mapping[str, object]) -> dict[str, object]:
        benchmark_status = report.get("benchmark_status")
        passed = report.get("policy_cases_passed")
        case_count = report.get("policy_case_count")
        report_digest = report.get("reproducibility_sha256")
        recovery = report.get("closed_loop_recovery")
        if (
            not isinstance(benchmark_status, str)
            or benchmark_status
            not in {
                "LOCAL_POLICY_TESTS_PASS_NOT_CERTIFICATION",
                "LOCAL_POLICY_TESTS_FAILED",
            }
            or type(passed) is not int
            or type(case_count) is not int
            or not 0 <= passed <= case_count
            or case_count < 1
            or not isinstance(report_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", report_digest) is None
            or report.get("hardware_measurements") != "NOT_PERFORMED"
            or report.get("public_certification_status") != "NOT_A_CERTIFICATION"
            or not isinstance(recovery, dict)
            or recovery.get("status") != "NOT_MEASURED"
        ):
            raise ValueError("Benchmark report does not match the evidence schema.")

        passed_all = (
            benchmark_status == "LOCAL_POLICY_TESTS_PASS_NOT_CERTIFICATION"
            and passed == case_count
        )
        return self._append(
            check_id="matrix-policy-benchmark",
            status="VERIFIED" if passed_all else "FAILED",
            summary=f"{passed}/{case_count} configured policy cases passed.",
            proves=(
                "This local run matched the configured software-policy outcomes "
                "and completed its synthetic workload."
            ),
            limitations=[
                "Does not verify physical hardware, recovery, scientific or medical performance.",
                "Does not constitute independent replication or academic certification.",
            ],
            source="MatrixAcademicBenchmarkSuite.run",
            evidence_sha256=report_digest,
        )

    def record_readiness_snapshot(self) -> dict[str, object]:
        return self._append(
            check_id="recovery-readiness-snapshot",
            status="UNKNOWN",
            summary=(
                "Device-specific identity, health, safety interlocks, and recovery "
                "authorization remain unverified; no physical action was performed."
            ),
            proves="Records the Matrix readiness state at the time of this snapshot.",
            limitations=[
                "A checklist is not a hardware inspection or repair.",
                "Academic certification requires an independent external reviewer.",
            ],
            source="Matrix recovery-readiness report",
            evidence_sha256=None,
        )

    def record_usb_inventory(
        self,
        *,
        device_count: int,
        expected_label_match: bool | None,
        probe_status: str,
    ) -> dict[str, object]:
        if type(device_count) is not int or not 0 <= device_count <= 10_000:
            raise ValueError("device_count must be a non-negative integer.")
        if expected_label_match is not None and type(expected_label_match) is not bool:
            raise ValueError("expected_label_match must be a boolean or None.")
        if not isinstance(probe_status, str) or probe_status not in {
            "VERIFIED",
            "NOT_VERIFIED",
            "PARTIALLY_VERIFIED",
            "UNKNOWN",
            "NOT_MEASURED",
        }:
            raise ValueError("probe_status is not recognized.")
        if expected_label_match is True and device_count == 0:
            raise ValueError(
                "A product-label match requires at least one enumerated device."
            )

        if probe_status == "NOT_MEASURED":
            status = "NOT_MEASURED"
            match_text = "the host OS does not support this USB probe"
        elif expected_label_match is True:
            status = "VERIFIED"
            match_text = "the expected product label matched"
        elif expected_label_match is False:
            status = "NOT_VERIFIED"
            match_text = "the expected product label did not match"
        elif device_count:
            status = "PARTIALLY_VERIFIED"
            match_text = "no target label was supplied"
        else:
            status = "UNKNOWN"
            match_text = "no USB device nodes were enumerated"

        return self._append(
            check_id="host-usb-enumeration",
            status=status,
            summary=(
                f"{device_count} active USB device node(s) enumerated; "
                f"{match_text}. Product labels, hardware IDs, serials, and raw "
                "device output were not retained."
            ),
            proves=(
                "The host OS enumerated USB nodes at capture time; a supplied "
                "product-label match identifies enumeration only."
            ),
            limitations=[
                "Does not verify device health, protocol communication, safety, or interlocks.",
                "Does not authorize or perform physical recovery.",
            ],
            source=(
                "macOS ioreg USB tree"
                if status != "NOT_MEASURED"
                else "Host platform capability check"
            ),
            evidence_sha256=None,
        )

    def _append(
        self,
        *,
        check_id: str,
        status: str,
        summary: str,
        proves: str,
        limitations: list[str],
        source: str,
        evidence_sha256: str | None,
    ) -> dict[str, object]:
        if not isinstance(status, str) or status not in _ENTRY_STATUSES:
            raise ValueError("Evidence status is not recognized.")
        if not isinstance(check_id, str) or check_id not in _CHECK_IDS:
            raise ValueError("Evidence check identifier is not recognized.")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (check_id, summary, proves, source)
        ):
            raise ValueError("Evidence text fields must be non-empty strings.")
        with _LEDGER_LOCK:
            entries = self._read_entries()
            if len(entries) >= MAX_LEDGER_ENTRIES:
                raise EvidenceLedgerError("Evidence ledger capacity has been reached.")
            record: dict[str, object] = {
                "sequence": len(entries) + 1,
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "check_id": check_id,
                "status": status,
                "summary": summary,
                "proves": proves,
                "limitations": limitations,
                "source": source,
                "evidence_sha256": evidence_sha256,
                "previous_entry_sha256": (
                    entries[-1]["entry_sha256"] if entries else None
                ),
            }
            record["entry_sha256"] = hashlib.sha256(_canonical_json(record)).hexdigest()
            entries.append(record)
            self._write_entries(entries)
            return record

    def _read_entries(self) -> list[dict[str, object]]:
        if self.path.is_symlink():
            raise EvidenceLedgerError("Evidence ledger cannot be a symbolic link.")
        if not self.path.exists():
            return []
        try:
            if self.path.stat().st_size > MAX_LEDGER_BYTES:
                raise EvidenceLedgerError("Evidence ledger exceeds the size limit.")
            ledger = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
            raise EvidenceLedgerError("Evidence ledger JSON is invalid.") from error
        except OSError as error:
            raise EvidenceLedgerError("Evidence ledger could not be read.") from error

        if (
            not isinstance(ledger, dict)
            or ledger.get("ledger_version") != 1
            or not isinstance(ledger.get("entries"), list)
            or len(ledger["entries"]) > MAX_LEDGER_ENTRIES
        ):
            raise EvidenceLedgerError("Evidence ledger structure is invalid.")

        entries: list[dict[str, object]] = []
        expected_previous: str | None = None
        required_keys = {
            "sequence",
            "recorded_at_utc",
            "check_id",
            "status",
            "summary",
            "proves",
            "limitations",
            "source",
            "evidence_sha256",
            "previous_entry_sha256",
            "entry_sha256",
        }
        for expected_sequence, candidate in enumerate(ledger["entries"], start=1):
            if not isinstance(candidate, dict) or set(candidate) != required_keys:
                raise EvidenceLedgerError("Evidence ledger entry structure is invalid.")
            entry = dict(candidate)
            entry_hash = entry.pop("entry_sha256")
            timestamp = entry.get("recorded_at_utc")
            limitations = entry.get("limitations")
            evidence_digest = entry.get("evidence_sha256")
            if (
                type(entry.get("sequence")) is not int
                or not isinstance(entry.get("check_id"), str)
                or entry.get("check_id") not in _CHECK_IDS
                or not isinstance(entry.get("status"), str)
                or not isinstance(entry.get("summary"), str)
                or not isinstance(entry.get("proves"), str)
                or not isinstance(entry.get("source"), str)
                or not isinstance(limitations, list)
                or any(not isinstance(item, str) for item in limitations)
                or (
                    evidence_digest is not None
                    and (
                        not isinstance(evidence_digest, str)
                        or re.fullmatch(r"[0-9a-f]{64}", evidence_digest) is None
                    )
                )
                or not isinstance(timestamp, str)
            ):
                raise EvidenceLedgerError("Evidence ledger entry fields are invalid.")
            try:
                parsed_timestamp = datetime.fromisoformat(timestamp)
            except ValueError as error:
                raise EvidenceLedgerError(
                    "Evidence ledger timestamp is invalid."
                ) from error
            if parsed_timestamp.utcoffset() != timezone.utc.utcoffset(parsed_timestamp):
                raise EvidenceLedgerError("Evidence ledger timestamp is not UTC.")
            if (
                entry.get("sequence") != expected_sequence
                or entry.get("status") not in _ENTRY_STATUSES
                or entry.get("previous_entry_sha256") != expected_previous
                or not isinstance(entry_hash, str)
                or re.fullmatch(r"[0-9a-f]{64}", entry_hash) is None
                or hashlib.sha256(_canonical_json(entry)).hexdigest() != entry_hash
            ):
                raise EvidenceLedgerError(
                    f"Evidence ledger integrity check failed at entry {expected_sequence}."
                )
            entry["entry_sha256"] = entry_hash
            entries.append(entry)
            expected_previous = entry_hash
        return entries

    def _write_entries(self, entries: list[dict[str, object]]) -> None:
        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.path.is_symlink():
                raise EvidenceLedgerError("Evidence ledger cannot be a symbolic link.")
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temp_path = Path(file.name)
                temporary_path = temp_path
                json.dump(
                    {"ledger_version": 1, "entries": entries},
                    file,
                    ensure_ascii=True,
                    indent=2,
                )
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            if os.name != "nt":
                temp_path.chmod(0o600)
            os.replace(temp_path, self.path)
        except OSError as error:
            raise EvidenceLedgerError(
                "Evidence ledger could not be written."
            ) from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def probe_macos_usb_inventory(
    expected_product_label: str | None,
) -> dict[str, object]:
    if expected_product_label is not None and (
        not isinstance(expected_product_label, str)
        or not 1 <= len(expected_product_label) <= 64
        or not expected_product_label.strip()
        or re.fullmatch(r"[A-Za-z0-9 ._-]+", expected_product_label) is None
    ):
        raise ValueError("Expected product label must be 1–64 safe characters.")
    if sys.platform != "darwin":
        return {
            "status": "NOT_MEASURED",
            "device_count": 0,
            "expected_label_match": None,
        }

    try:
        result = subprocess.run(
            ["ioreg", "-p", "IOUSB", "-w0"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except FileNotFoundError as error:
        raise EvidenceLedgerError(
            "macOS USB inventory utility is unavailable."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise EvidenceLedgerError("macOS USB inventory timed out.") from error
    except OSError as error:
        raise EvidenceLedgerError("macOS USB inventory could not run.") from error
    if result.returncode != 0:
        raise EvidenceLedgerError("macOS USB inventory returned an error.")

    labels = [
        match.group(1).partition("@")[0].strip()
        for match in _USB_NODE_PATTERN.finditer(result.stdout)
        if re.search(r"(?:^|[,\s])active(?:[,\s]|$)", match.group(0))
    ]
    expected_match = (
        any(label.casefold() == expected_product_label.casefold() for label in labels)
        if expected_product_label is not None
        else None
    )
    if expected_product_label is not None:
        status = "VERIFIED" if expected_match else "NOT_VERIFIED"
    else:
        status = "PARTIALLY_VERIFIED" if labels else "UNKNOWN"
    return {
        "status": status,
        "device_count": len(labels),
        "expected_label_match": expected_match,
    }
