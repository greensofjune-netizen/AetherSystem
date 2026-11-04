from __future__ import annotations

import platform
import subprocess
import sys
import tempfile
from pathlib import Path


def package_production_binary() -> int:
    workspace_root = Path(__file__).resolve().parent
    source_directory = workspace_root / "src"
    dist_directory = workspace_root / "dist"
    build_directory = workspace_root / "build"
    output_name = "aether-engine"
    output_binary = dist_directory / (
        f"{output_name}.exe" if sys.platform == "win32" else output_name
    )

    print("=" * 70)
    print("AETHER APP BUNDLER: BUILDING A STANDALONE EXECUTABLE")
    print("=" * 70)
    print(f"Project: {workspace_root}")
    print(f"Target platform: {platform.system()} ({platform.machine()})")

    dist_directory.mkdir(parents=True, exist_ok=True)
    build_directory.mkdir(parents=True, exist_ok=True)

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
                sys.executable,
                "-m",
                "PyInstaller",
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
            print("\nStarting PyInstaller...")
            subprocess.run(
                command,
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
    except subprocess.CalledProcessError as error:
        print("Build failed.")
        if error.stdout:
            print(error.stdout)
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        return error.returncode or 1
    except OSError as error:
        print(f"Unable to run the build: {error}", file=sys.stderr)
        return 1

    if not output_binary.is_file():
        print(
            f"Build completed but the expected executable was not created: "
            f"{output_binary}",
            file=sys.stderr,
        )
        return 1

    print("\nBuild succeeded.")
    print(f"Executable: {output_binary}")
    print(f"Try it with: ./dist/{output_name} --help")
    return 0


if __name__ == "__main__":
    raise SystemExit(package_production_binary())
