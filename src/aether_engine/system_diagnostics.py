from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, Sequence

from .quantum_engine import QuantumStateSimulator, StateCollapseAnomalyError

DiagnosticStatus = Literal["OK", "WARN", "FAIL"]
LOW_MEMORY_BYTES: Final[int] = 512 * 1024**2
LOW_DISK_BYTES: Final[int] = 1024**3
CRITICAL_DISK_BYTES: Final[int] = 128 * 1024**2


@dataclass(frozen=True)
class SystemDiagnosticCheck:
    category: str
    status: DiagnosticStatus
    detail: str


class SystemDiagnosticScanner:
    """Run read-only diagnostics for the local AetherSystem project and host."""

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace_root = (
            Path(workspace_root).expanduser().resolve()
            if workspace_root is not None
            else self._discover_workspace_root()
        )

    @staticmethod
    def _discover_workspace_root() -> Path:
        module_root = Path(__file__).resolve().parents[2]
        for start in (Path.cwd().resolve(), module_root):
            for candidate in (start, *start.parents):
                if (candidate / "pyproject.toml").is_file():
                    return candidate
        return Path.cwd().resolve()

    def scan(self) -> tuple[SystemDiagnosticCheck, ...]:
        return (
            self._check_runtime(),
            self._check_host(),
            self._check_memory(),
            self._check_storage(),
            self._check_project(),
            self._check_simulator(),
        )

    def render_report(
        self,
        checks: Sequence[SystemDiagnosticCheck],
        checked_at: datetime | None = None,
    ) -> str:
        timestamp = (checked_at or datetime.now().astimezone()).isoformat(
            timespec="seconds"
        )
        lines = [
            "AETHER SYSTEM DIAGNOSTICS",
            f"Checked: {timestamp}",
            f"Workspace: {self.workspace_root}",
            "",
        ]
        lines.extend(
            f"[{check.status}] {check.category}: {check.detail}" for check in checks
        )
        counts = {
            status: sum(check.status == status for check in checks)
            for status in ("OK", "WARN", "FAIL")
        }
        lines.extend(
            [
                "",
                "Summary: "
                f"{len(checks)} checks; {counts['OK']} OK, "
                f"{counts['WARN']} warnings, {counts['FAIL']} failures.",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _check_runtime() -> SystemDiagnosticCheck:
        version = sys.version_info
        version_text = f"{version.major}.{version.minor}.{version.micro}"
        if version < (3, 11):
            return SystemDiagnosticCheck(
                "Python runtime",
                "FAIL",
                f"Python {version_text} detected; AetherSystem requires Python 3.11 or newer.",
            )
        return SystemDiagnosticCheck(
            "Python runtime",
            "OK",
            f"Python {version_text}; executable: {sys.executable}",
        )

    @staticmethod
    def _check_host() -> SystemDiagnosticCheck:
        cpu_count = os.cpu_count()
        detail = f"{platform.system()} {platform.release()} ({platform.machine()}); "
        if cpu_count is None:
            return SystemDiagnosticCheck(
                "Host", "WARN", detail + "logical CPU count is unavailable."
            )
        return SystemDiagnosticCheck(
            "Host", "OK", detail + f"{cpu_count} logical CPU(s)."
        )

    @staticmethod
    def _check_memory() -> SystemDiagnosticCheck:
        try:
            total_bytes, available_bytes = _read_memory_stats()
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            return SystemDiagnosticCheck(
                "Memory", "WARN", f"Could not read memory metrics: {error}"
            )
        if total_bytes is None:
            return SystemDiagnosticCheck(
                "Memory", "WARN", "Memory metrics are unavailable on this platform."
            )
        if available_bytes is None:
            return SystemDiagnosticCheck(
                "Memory",
                "OK",
                f"{_format_bytes(total_bytes)} total; available amount unavailable.",
            )
        status: DiagnosticStatus = (
            "WARN" if available_bytes < LOW_MEMORY_BYTES else "OK"
        )
        detail = (
            f"{_format_bytes(available_bytes)} available"
            f"{' (estimated)' if sys.platform == 'darwin' else ''}; "
            f"{_format_bytes(total_bytes)} total."
        )
        if status == "WARN":
            detail += " Available memory is below 512 MiB."
        return SystemDiagnosticCheck("Memory", status, detail)

    def _check_storage(self) -> SystemDiagnosticCheck:
        try:
            usage = shutil.disk_usage(self.workspace_root)
        except OSError as error:
            return SystemDiagnosticCheck(
                "Workspace storage",
                "FAIL",
                f"Could not inspect workspace disk capacity: {error}",
            )
        detail = (
            f"{_format_bytes(usage.free)} free of {_format_bytes(usage.total)}."
        )
        if usage.free < CRITICAL_DISK_BYTES:
            return SystemDiagnosticCheck(
                "Workspace storage", "FAIL", detail + " Less than 128 MiB is free."
            )
        if usage.free < LOW_DISK_BYTES:
            return SystemDiagnosticCheck(
                "Workspace storage", "WARN", detail + " Less than 1 GiB is free."
            )
        return SystemDiagnosticCheck("Workspace storage", "OK", detail)

    def _check_project(self) -> SystemDiagnosticCheck:
        pyproject = self.workspace_root / "pyproject.toml"
        try:
            project_data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
            return SystemDiagnosticCheck(
                "AetherSystem project",
                "FAIL",
                f"Could not read a valid pyproject.toml: {error}",
            )
        project = project_data.get("project")
        package_dir = self.workspace_root / "src" / "aether_engine"
        if not isinstance(project, dict) or project.get("name") != "aether-engine":
            return SystemDiagnosticCheck(
                "AetherSystem project",
                "FAIL",
                "pyproject.toml does not identify the aether-engine project.",
            )
        if not package_dir.is_dir():
            return SystemDiagnosticCheck(
                "AetherSystem project",
                "FAIL",
                f"Package source directory is missing: {package_dir}",
            )
        return SystemDiagnosticCheck(
            "AetherSystem project",
            "OK",
            "Project metadata is valid and the package source directory is present.",
        )

    @staticmethod
    def _check_simulator() -> SystemDiagnosticCheck:
        simulator = QuantumStateSimulator()
        try:
            coherence = simulator.compute_wave_coherence()
            entropy = simulator.calculate_entropy_index(57.0)
        except (StateCollapseAnomalyError, ValueError) as error:
            return SystemDiagnosticCheck(
                "Quantum simulator", "FAIL", f"Normal-state check failed: {error}"
            )
        if coherence != 70.0 or entropy != 67.0:
            return SystemDiagnosticCheck(
                "Quantum simulator",
                "FAIL",
                f"Unexpected baseline metrics: coherence={coherence}, entropy={entropy}.",
            )
        try:
            simulator.calculate_entropy_index(120.0)
        except StateCollapseAnomalyError:
            return SystemDiagnosticCheck(
                "Quantum simulator",
                "OK",
                "Baseline metrics are valid and the collapse guard is active.",
            )
        return SystemDiagnosticCheck(
            "Quantum simulator",
            "FAIL",
            "The entropy threshold did not trigger the collapse guard.",
        )


def _read_memory_stats() -> tuple[int | None, int | None]:
    system_name = platform.system()
    if system_name == "Linux":
        memory_values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            name, separator, value = line.partition(":")
            if separator and name in ("MemTotal", "MemAvailable"):
                memory_values[name] = int(value.strip().split()[0]) * 1024
        return memory_values.get("MemTotal"), memory_values.get("MemAvailable")

    if system_name == "Darwin":
        if "SC_PHYS_PAGES" not in os.sysconf_names:
            return None, None
        total_bytes = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        try:
            result = subprocess.run(
                ["vm_stat"], capture_output=True, check=True, text=True, timeout=2
            )
        except (OSError, subprocess.SubprocessError):
            return total_bytes, None
        page_size_match = re.search(r"page size of (\d+) bytes", result.stdout)
        page_counts = dict(
            re.findall(
                r"^Pages (free|inactive|speculative):\s+([\d,]+)\.$",
                result.stdout,
                re.MULTILINE,
            )
        )
        if page_size_match is None or len(page_counts) != 3:
            return total_bytes, None
        available_pages = sum(int(count.replace(",", "")) for count in page_counts.values())
        return total_bytes, available_pages * int(page_size_match.group(1))

    if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names:
        page_size = os.sysconf("SC_PAGE_SIZE")
        total_bytes = os.sysconf("SC_PHYS_PAGES") * page_size
        available_bytes = None
        if "SC_AVPHYS_PAGES" in os.sysconf_names:
            available_bytes = os.sysconf("SC_AVPHYS_PAGES") * page_size
        return total_bytes, available_bytes
    return None, None


def _format_bytes(value: int) -> str:
    size = float(value)
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.1f} {units[unit_index]}"


def diagnostics_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aether-quantum-diagnostics",
        description="Run read-only local AetherSystem and host diagnostics.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="AetherSystem project directory (auto-detected by default).",
    )
    arguments = parser.parse_args(argv)
    scanner = SystemDiagnosticScanner(arguments.workspace)
    checks = scanner.scan()
    print(scanner.render_report(checks))
    return int(any(check.status == "FAIL" for check in checks))
