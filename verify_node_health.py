"""Read-only local host diagnostics with an optional, bounded TCP reachability check."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import platform
import plistlib
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from aether_engine.system_diagnostics import (
    SystemDiagnosticCheck,
    SystemDiagnosticScanner,
)

PROJECT_ROOT = Path(__file__).resolve().parent


class DiagnosticError(RuntimeError):
    pass


def _run_read_only(command: Sequence[str], *, timeout: float = 5.0) -> bytes:
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise DiagnosticError(f"{command[0]} is unavailable.") from error
    except subprocess.TimeoutExpired as error:
        raise DiagnosticError(f"{command[0]} timed out.") from error
    except OSError as error:
        raise DiagnosticError(f"{command[0]} could not run.") from error
    if result.returncode != 0:
        raise DiagnosticError(f"{command[0]} exited with code {result.returncode}.")
    return result.stdout


def get_storage_and_smart_health(mount_path: str = "/") -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(mount_path)
    except OSError as error:
        raise DiagnosticError("Storage capacity could not be read.") from error

    report: dict[str, Any] = {
        "status": "MEASURED",
        "total_storage_gb": round(usage.total / (1024**3), 2),
        "free_storage_gb": round(usage.free / (1024**3), 2),
        "smart_status": "NOT_APPLICABLE",
        "scope": "selected mounted volume capacity; no filesystem scan performed",
    }
    if platform.system() != "Darwin":
        return report

    output = _run_read_only(["diskutil", "info", "-plist", mount_path])
    try:
        disk_info = plistlib.loads(output)
    except plistlib.InvalidFileException as error:
        raise DiagnosticError(
            "diskutil returned invalid property-list data."
        ) from error
    smart_status = disk_info.get("SMARTStatus")
    report["smart_status"] = (
        smart_status if isinstance(smart_status, str) else "NOT_REPORTED"
    )
    return report


def check_remote_yotuo_node(yotuo_ip: str | None) -> dict[str, Any]:
    if yotuo_ip is None:
        return {
            "status": "NOT_REQUESTED",
            "detail": "No remote host supplied; no network connections were attempted.",
            "probes": {},
        }

    try:
        address = ipaddress.ip_address(yotuo_ip)
    except ValueError as error:
        raise ValueError("Remote target must be a private IP address.") from error
    if (
        not address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    ):
        raise ValueError("Remote target must be a private IP address for your node.")

    probes: dict[str, dict[str, object]] = {}
    for port, service in ((22, "ssh_tcp"), (11434, "ollama_tcp")):
        started = time.perf_counter()
        try:
            with socket.create_connection((str(address), port), timeout=1.5):
                probes[service] = {
                    "status": "TCP_CONNECTED",
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                }
        except OSError as error:
            probes[service] = {
                "status": "CONNECTION_FAILED",
                "error_type": type(error).__name__,
            }
    return {
        "status": "PORT_REACHABILITY_ONLY",
        "target_ip": str(address),
        "probes": probes,
        "limitation": (
            "TCP reachability does not verify node identity, service health, "
            "hardware health, or authorization."
        ),
    }


def _load_average() -> dict[str, object]:
    if not hasattr(os, "getloadavg"):
        return {"status": "NOT_MEASURED"}
    try:
        values = os.getloadavg()
    except OSError as error:
        return {"status": "ERROR", "error_type": type(error).__name__}
    return {
        "status": "MEASURED",
        "one_minute": round(values[0], 2),
        "five_minutes": round(values[1], 2),
        "fifteen_minutes": round(values[2], 2),
    }


def _check_result(check: SystemDiagnosticCheck) -> dict[str, str]:
    return {
        "category": check.category,
        "status": check.status,
        "detail": check.detail,
    }


def run_verifiable_diagnostic(
    yotuo_ip: str | None = None,
    *,
    mount_path: str = "/",
) -> dict[str, Any]:
    checks = SystemDiagnosticScanner(PROJECT_ROOT).scan()
    try:
        storage = get_storage_and_smart_health(mount_path)
    except DiagnosticError as error:
        storage = {"status": "ERROR", "error": str(error)}
    statuses = [check.status for check in checks]
    if "FAIL" in statuses or storage["status"] == "ERROR":
        local_status = "FAIL"
    elif "WARN" in statuses or storage.get("smart_status") in {
        "NOT_REPORTED",
        "NOT_SUPPORTED",
        "Not Supported",
        "UNAVAILABLE",
    }:
        local_status = "WARN"
    else:
        local_status = "PASS"
    telemetry: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "local_status": local_status,
        "host_node": {
            "os": f"{platform.system()} {platform.release()}",
            "architecture": platform.machine(),
            "logical_cores": os.cpu_count(),
            "load_average": _load_average(),
            "system_diagnostics": [_check_result(check) for check in checks],
            "storage": storage,
        },
        "paired_yotuo_node": check_remote_yotuo_node(yotuo_ip),
        "integrity_note": (
            "SHA-256 identifies this report's contents; it is not a signature, "
            "device identity proof, independent verification, or certification."
        ),
    }
    canonical_json = json.dumps(
        telemetry,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    telemetry["report_sha256"] = hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()
    return telemetry


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run read-only local diagnostics. A remote check is opt-in and only "
            "tests two TCP ports on an explicitly supplied private IP."
        )
    )
    parser.add_argument(
        "--mount-path",
        default="/",
        help="Mounted volume for capacity/SMART metadata (default: local root volume).",
    )
    parser.add_argument(
        "--remote-host",
        help="Optional private IP of a networked node you own; omitted means no network access.",
    )
    arguments = parser.parse_args(argv)
    try:
        report = run_verifiable_diagnostic(
            arguments.remote_host,
            mount_path=arguments.mount_path,
        )
    except (DiagnosticError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return int(report["local_status"] == "FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
