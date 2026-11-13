"""Build a portable, locally ad-hoc-signed macOS Master Matrix release candidate."""

from __future__ import annotations

import argparse
import plistlib
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

APP_NAME = "Aether Master Matrix"


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Build a new {APP_NAME}.app locally.")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "dist")
    args = parser.parse_args()
    if sys.platform != "darwin":
        print("This app must be built on macOS.", file=sys.stderr)
        return 1
    application = args.output_dir.resolve() / f"{APP_NAME}.app"
    if application.exists() or application.is_symlink():
        print(f"Refusing to overwrite existing app: {application}", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parent
    try:
        with tempfile.TemporaryDirectory(prefix="master-matrix-build-") as temporary:
            work = Path(temporary)
            launcher = work / "master_entry.py"
            launcher.write_text(
                "from aether_engine.master_desktop import main\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(main())\n", encoding="utf-8",
            )
            command = [
                sys.executable, "-m", "PyInstaller", "--windowed", "--onedir",
                f"--name={APP_NAME}", "--clean", "--noconfirm",
                "--osx-bundle-identifier=net.aethersystem.mastermatrix",
                f"--paths={root / 'src'}", f"--paths={root}",
                f"--distpath={work / 'dist'}", f"--workpath={work / 'work'}",
                f"--specpath={work}", "--collect-all=webview",
                "--hidden-import=aether_master_matrix",
                "--hidden-import=webview.platforms.cocoa",
                "--exclude-module=torch", "--exclude-module=matplotlib",
                "--exclude-module=IPython", "--exclude-module=pytest",
                "--exclude-module=tkinter",
                f"--add-data={root / 'frontend'}:frontend",
                f"--add-data={root / 'LICENSE'}:.",
                f"--add-data={root / 'THIRD_PARTY_NOTICES.md'}:.",
                str(launcher),
            ]
            subprocess.run(command, cwd=root, check=True)
            built = work / "dist" / f"{APP_NAME}.app"
            executable = built / "Contents" / "MacOS" / APP_NAME
            if not executable.is_file():
                raise OSError("Build did not produce the expected app executable.")
            plist_path = built / "Contents" / "Info.plist"
            with plist_path.open("rb") as stream:
                plist = plistlib.load(stream)
            with (root / "pyproject.toml").open("rb") as stream:
                plist["CFBundleShortVersionString"] = tomllib.load(stream)["project"]["version"]
            plist["CFBundleVersion"] = "1"
            plist["NSCameraUsageDescription"] = "Camera is used only when you start a local observation."
            plist["NSMicrophoneUsageDescription"] = "Microphone is used only when you request speech input."
            with plist_path.open("wb") as stream:
                plistlib.dump(plist, stream)
            subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(built)], check=True)
            args.output_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(built, application, symlinks=True)
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(application)], check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Master Matrix build failed: {error}", file=sys.stderr)
        return 1
    print(f"Local release candidate: {application}")
    print("Ad-hoc signed only; not notarized or approved for public distribution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
