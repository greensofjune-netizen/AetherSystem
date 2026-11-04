from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

_LOGGER = logging.getLogger(__name__)
_COMMAND_TIMEOUT_SECONDS = 600


class EngineCoreUpdater:
    """Upgrade local build tools and rebuild the Aether executable."""

    def __init__(self, current_version: str = "13.0.0") -> None:
        self.workspace_root = Path(__file__).resolve().parents[2]
        self.current_version = current_version
        self.dist_dir = self.workspace_root / "dist"

    @staticmethod
    def _is_virtual_environment() -> bool:
        return sys.prefix != sys.base_prefix

    def scan_and_upgrade_software_packages(self) -> bool:
        """Upgrade build and test tools in the active virtual environment."""
        if not self._is_virtual_environment():
            _LOGGER.error(
                "Refusing to upgrade packages outside a virtual environment."
            )
            return False

        _LOGGER.info("Upgrading pip, Ruff, PyInstaller, and pytest.")
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "ruff",
            "pyinstaller",
            "pytest",
        ]
        try:
            subprocess.run(
                command,
                cwd=self.workspace_root,
                check=True,
                capture_output=True,
                text=True,
                timeout=_COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.CalledProcessError as error:
            _LOGGER.error("Package upgrade failed: %s", error.stderr or error)
            return False
        except subprocess.TimeoutExpired:
            _LOGGER.error("Package upgrade timed out.")
            return False
        except OSError:
            _LOGGER.exception("Unable to start the package upgrade.")
            return False

        _LOGGER.info("Build and test tool upgrades completed.")
        return True

    def trigger_binary_recompilation(self) -> bool:
        """Run the project's build script using the active Python interpreter."""
        build_script = self.workspace_root / "build_app.py"
        if not build_script.is_file():
            _LOGGER.warning("Build script not found; skipping executable rebuild.")
            return False
        if not self._is_virtual_environment():
            _LOGGER.error(
                "Refusing to rebuild outside a virtual environment."
            )
            return False

        _LOGGER.info("Rebuilding the standalone executable.")
        try:
            result = subprocess.run(
                [sys.executable, str(build_script)],
                cwd=self.workspace_root,
                check=True,
                capture_output=True,
                text=True,
                timeout=_COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.CalledProcessError as error:
            _LOGGER.error("Executable rebuild failed: %s", error.stderr or error)
            return False
        except subprocess.TimeoutExpired:
            _LOGGER.error("Executable rebuild timed out.")
            return False
        except OSError:
            _LOGGER.exception("Unable to start the executable rebuild.")
            return False

        if result.stdout.strip():
            _LOGGER.info("%s", result.stdout.strip())
        _LOGGER.info("Standalone executable rebuild completed.")
        return True

    def execute_complete_core_maintenance_cycle(self) -> str:
        """Upgrade local tools and rebuild the standalone executable."""
        _LOGGER.info("Starting Aether updater maintenance cycle.")
        if not self._is_virtual_environment():
            _LOGGER.error(
                "Virtual environment required; refusing to run maintenance."
            )
            return "VULNERABLE"

        software_updated = self.scan_and_upgrade_software_packages()
        binary_compiled = self.trigger_binary_recompilation()
        cycle_succeeded = software_updated and binary_compiled
        next_version = (
            "13.1.0" if cycle_succeeded else self.current_version
        )
        status = "NOMINAL" if cycle_succeeded else "DEGRADED"

        _LOGGER.info(
            "Maintenance cycle %s; version trajectory: v%s.",
            status.lower(),
            next_version,
        )
        return status


if __name__ == "__main__":
    EngineCoreUpdater().execute_complete_core_maintenance_cycle()
