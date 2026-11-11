"""Install Galileo Quick Actions or an Aristotle app launcher without overwriting."""

from __future__ import annotations

import argparse
import copy
import os
import plistlib
import shlex
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = Path(
    "/System/Library/Services/Show Map.workflow/Contents/Resources/document.wflow"
)
ACTIONS = {
    "Galileo - Launch": ("launch", False),
    "Galileo - Ask Local LLM": ("prompt", False),
    "Galileo - Ask About Selected Text": ("prompt", True),
    "Galileo - Run Project Tests": ("test", False),
    "Galileo - Back Up Local Data": ("backup", False),
}


def create_workflow(
    destination: Path, name: str, action: str, selected: bool, interpreter: Path,
    *, app_bundle: Path | None = None,
) -> None:
    with SAMPLE.open("rb") as source:
        template = plistlib.load(source)
    shell = next(
        entry
        for entry in template["actions"]
        if entry["action"].get("BundleIdentifier") == "com.apple.RunShellScript"
    )
    shell = copy.deepcopy(shell)
    item = shell["action"]
    for key in ("UUID", "InputUUID", "OutputUUID"):
        item[key] = str(uuid.uuid4()).upper()
    bridge = ROOT / "automator" / "bridge.py"
    command = (
        f"export PYTHONPATH={shlex.quote(str(ROOT / 'src'))}\n"
        f"exec {shlex.quote(str(interpreter))} {shlex.quote(str(bridge))} {action}"
    )
    if not selected:
        command += " </dev/null"
    if app_bundle is not None:
        command = f"exec /usr/bin/open {shlex.quote(str(app_bundle))} </dev/null"
    item["ActionParameters"]["COMMAND_STRING"] = command
    item["ActionParameters"]["shell"] = "/bin/sh"
    item["ActionParameters"]["inputMethod"] = 0
    template["actions"] = [shell]
    template["connectors"] = {}
    template["workflowMetaData"] = {
        "serviceApplicationBundleID": "",
        "serviceApplicationPath": "",
        "serviceInputTypeIdentifier": (
            "com.apple.Automator.text" if selected else "com.apple.Automator.nothing"
        ),
        "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
        "serviceProcessesInput": 0,
        "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
    }
    service = {
        "NSMenuItem": {"default": name},
        "NSMessage": "runWorkflowAsService",
    }
    if selected:
        service["NSSendTypes"] = ["public.utf8-plain-text"]
    info = {
        "CFBundleDevelopmentRegion": "en_US",
        "CFBundleIdentifier": (
            f"net.aethersystem.{'aristotle' if app_bundle else 'galileo'}.automator.{action}"
        )
        + (".selection" if selected else ""),
        "CFBundleName": name,
        "CFBundleShortVersionString": "1.0",
        "NSServices": [service],
    }
    destination.mkdir(mode=0o700)
    contents = destination / "Contents"
    resources = contents / "Resources"
    resources.mkdir(parents=True, mode=0o700)
    for path, data in (
        (contents / "Info.plist", info),
        (contents / "document.wflow", template),
        (resources / "document.wflow", template),
    ):
        with path.open("xb") as output:
            plistlib.dump(data, output)
        path.chmod(0o600)


def install(
    directory: Path, interpreter: Path, *, app_bundle: Path | None = None
) -> list[Path]:
    if sys.platform != "darwin":
        raise RuntimeError("Automator workflows require macOS.")
    if app_bundle is not None:
        app_bundle = app_bundle.expanduser().resolve()
        executable = app_bundle / "Contents" / "MacOS" / "Matrix Aristotle"
        if app_bundle.name != "Matrix Aristotle.app" or not executable.is_file() \
                or not os.access(executable, os.X_OK):
            raise ValueError(f"An executable Matrix Aristotle.app is required: {app_bundle}")
    if not SAMPLE.is_file() or (app_bundle is None and not interpreter.is_file()):
        raise FileNotFoundError("Automator template or Python interpreter not found.")
    if directory.is_symlink():
        raise ValueError(f"Refusing a symlinked Services directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    actions = {"Aristotle - Launch": ("launch", False)} if app_bundle else ACTIONS
    destinations = [directory / f"{name}.workflow" for name in actions]
    existing = [path for path in destinations if os.path.lexists(path)]
    if existing:
        raise FileExistsError(
            "Will not overwrite existing workflows: "
            + ", ".join(str(path) for path in existing)
        )
    for (name, (action, selected)), destination in zip(actions.items(), destinations):
        create_workflow(
            destination, name, action, selected, interpreter, app_bundle=app_bundle
        )
    return destinations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory", type=Path, default=Path.home() / "Library" / "Services"
    )
    parser.add_argument(
        "--app-bundle", type=Path,
        help="Install only Aristotle - Launch, opening this Matrix Aristotle.app directly.",
    )
    args = parser.parse_args()
    try:
        paths = install(
            args.directory, Path(sys.executable).absolute(), app_bundle=args.app_bundle
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Automator installation failed: {error}", file=sys.stderr)
        return 1
    for path in paths:
        print(f"Installed: {path}")
    print("Enable or find the Quick Actions in macOS Services settings if needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
