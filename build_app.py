from __future__ import annotations

import platform
import subprocess
import sys
import tempfile
from pathlib import Path


def run_cookie_cutter_build() -> int:
    workspace_root = Path(__file__).resolve().parent
    source_directory = workspace_root / "src"
    dist_directory = workspace_root / "dist"
    build_directory = workspace_root / "build"
    output_name = "aether-engine"
    entry_script = source_directory / "aether_engine" / "cli.py"
    output_binary = dist_directory / (
        f"{output_name}.exe" if sys.platform == "win32" else output_name
    )

    print("=" * 70)
    print("AETHER CORE BUNDLER: BUILDING A STANDALONE EXECUTABLE")
    print("=" * 70)

    if not entry_script.is_file():
        print(f"Entry script not found: {entry_script}", file=sys.stderr)
        return 1

    print(f"Packaging entry point: {entry_script}")
    print(f"Build platform: {platform.system()} ({platform.machine()})")

    dist_directory.mkdir(parents=True, exist_ok=True)
    build_directory.mkdir(parents=True, exist_ok=True)

    # Import the CLI as a package; executing cli.py directly breaks relative imports.
    launcher_source = (
        "from aether_engine.cli import main\n\n"
        'if __name__ == "__main__":\n'
        "    raise SystemExit(main())\n"
    )

    try:
        with tempfile.TemporaryDirectory(prefix="aether-build-") as temp_dir:
            launcher = Path(temp_dir) / "aether_engine_entry.py"
            launcher.write_text(launcher_source, encoding="utf-8")
            command = [
                sys.executable, "-m", "PyInstaller",
                "--onefile",
                f"--name={output_name}",
                "--clean",
                "--noconfirm",
                f"--paths={source_directory}",
                f"--distpath={dist_directory}",
                f"--workpath={build_directory}",
                f"--specpath={build_directory}",
                str(launcher),
            ]
            print("\nExecuting PyInstaller...")
            subprocess.run(
                command,
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
    except subprocess.CalledProcessError as error:
        print("Executable build failed.", file=sys.stderr)
        if error.stdout:
            print(error.stdout)
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        return error.returncode or 1
    except OSError as error:
        print(f"Unable to run PyInstaller: {error}", file=sys.stderr)
        return 1

    if not output_binary.is_file():
        print(
            f"Build completed without producing the expected executable: {output_binary}",
            file=sys.stderr,
        )
        return 1

    print("\nStandalone executable built successfully.")
    print(f"Binary: {output_binary}")
    print(f"Verify with: ./dist/{output_name} --help")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cookie_cutter_build())
