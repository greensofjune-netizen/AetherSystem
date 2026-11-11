"""Build a macOS Galileo.app including the native window and all local assets."""

from __future__ import annotations

import argparse
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def launcher_source(root: Path, module: str, *, portable: bool) -> str:
    project = (
        "Path.home() / 'Library' / 'Application Support' / 'AetherSystem' / 'Matrix'"
        if portable else f"Path({str(root)!r})"
    )
    return (
        "from pathlib import Path\n"
        f"from aether_engine.{module} import main\n"
        "if __name__ == '__main__':\n"
        f"    raise SystemExit(main(project_directory={project}))\n"
    )


def main(*, aristotle: bool = False) -> int:
    app_name = "Matrix Aristotle" if aristotle else "Galileo"
    module = "aristotle_desktop" if aristotle else "galileo_desktop"
    parser = argparse.ArgumentParser(
        description=f"Build the macOS {app_name}.app with its native window and assets."
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).resolve().parent / "dist",
        help=f"Directory for a new {app_name}.app; existing builds are never overwritten.",
    )
    parser.add_argument(
        "--portable", action="store_true",
        help="Use a portable default project path instead of the build project's path.",
    )
    args = parser.parse_args()
    if sys.platform != "darwin":
        print("Galileo.app must be built on macOS.", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parent
    application = args.output_dir.resolve() / f"{app_name}.app"
    if application.exists() or application.is_symlink():
        print(f"Refusing to overwrite existing app: {application}", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="galileo-build-") as temporary:
        temp_root = Path(temporary)
        launcher = Path(temporary) / "galileo_entry.py"
        launcher.write_text(
            launcher_source(root, module, portable=args.portable),
            encoding="utf-8",
        )
        voice_helper = temp_root / "galileo-voice"
        try:
            subprocess.run(
                [
                    "/usr/bin/swiftc",
                    str(root / "src/aether_engine/galileo_voice.swift"),
                    "-o", str(voice_helper),
                ],
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            print(f"{app_name} native voice build failed: {error}", file=sys.stderr)
            return 1
        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--windowed",
            "--onedir",
            f"--name={app_name}",
            "--noconfirm",
            "--clean",
            f"--osx-bundle-identifier=net.aethersystem.{'aristotle' if aristotle else 'galileo'}",
            f"--paths={root / 'src'}",
            f"--paths={root}",
            f"--distpath={temp_root / 'dist'}",
            f"--workpath={temp_root / 'work'}",
            f"--specpath={temp_root}",
            "--collect-all=webview",
            "--hidden-import=uvicorn.logging",
            "--hidden-import=uvicorn.loops.auto",
            "--hidden-import=uvicorn.protocols.http.h11_impl",
            "--hidden-import=uvicorn.lifespan.on",
            "--exclude-module=torch",
            "--exclude-module=matplotlib",
            "--exclude-module=IPython",
            "--exclude-module=tkinter",
            "--exclude-module=pytest",
            f"--add-data={root / 'src/aether_engine/galileo_assets'}:aether_engine/galileo_assets",
            f"--add-data={root / 'frontend'}:aether_engine/galileo_observatory",
            f"--add-binary={voice_helper}:aether_engine",
            str(launcher),
        ]
        try:
            subprocess.run(command, cwd=root, check=True)
            built_app = temp_root / "dist" / f"{app_name}.app"
            if not (built_app / "Contents" / "MacOS" / app_name).is_file():
                raise OSError(f"Build did not produce the {app_name} executable.")
            plist_path = built_app / "Contents" / "Info.plist"
            with plist_path.open("rb") as file:
                plist = plistlib.load(file)
            plist["NSCameraUsageDescription"] = (
                f"{app_name} uses your camera only when you start camera observations."
            )
            plist["NSMicrophoneUsageDescription"] = (
                f"{app_name} records speech only when you start on-device voice input."
            )
            plist["NSSpeechRecognitionUsageDescription"] = (
                f"{app_name} transcribes your voice on this Mac without uploading audio."
            )
            with plist_path.open("wb") as file:
                plistlib.dump(plist, file)
            subprocess.run(
                ["codesign", "--force", "--deep", "--sign", "-", str(built_app)],
                check=True,
            )
            args.output_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(built_app, application, symlinks=True)
        except (OSError, subprocess.CalledProcessError) as error:
            print(f"{app_name} build failed: {error}", file=sys.stderr)
            return 1
    if not (application / "Contents" / "MacOS" / app_name).is_file():
        print(f"Build did not produce the {app_name} executable.", file=sys.stderr)
        return 1
    print(f"{app_name} ready: {application}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
