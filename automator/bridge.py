"""Narrow, local-only commands used by the macOS Automator workflows."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from urllib.parse import quote

from aether_engine.backups import secure_backup_directory, write_backup
from aether_engine.database import AetherStore
from aether_engine.historian_behavior import AetherHistorian, OllamaConnectionError

PROJECT = Path(__file__).resolve().parents[1]
MODEL = "atlas-qwen-coder:latest"


def dialog(message: str, *, prompt: bool = False, confirm: bool = False) -> str:
    # Text travels through an owner-only file, never shell syntax or process arguments.
    with tempfile.TemporaryDirectory(prefix="galileo-dialog-") as directory:
        path = Path(directory) / "message.txt"
        path.write_text(message, encoding="utf-8")
        path.chmod(0o600)
        if prompt:
            action = (
                'text returned of (display dialog messageText default answer "" '
                'buttons {"Cancel", "Send"} default button "Send")'
            )
        elif confirm:
            action = (
                "button returned of (display dialog messageText "
                'buttons {"Cancel", "Continue"} default button "Cancel")'
            )
        else:
            action = (
                "button returned of (display dialog messageText "
                'buttons {"OK"} default button "OK")'
            )
        script = (
            "on run argv\n"
            "set messageText to read POSIX file (item 1 of argv) as «class utf8»\n"
            f"return {action}\n"
            "end run"
        )
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", script, str(path)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            if "(-128)" in result.stderr:
                raise InterruptedError("Cancelled by user.")
            raise RuntimeError(
                f"Could not show Automator dialog: {result.stderr.strip()}"
            )
        return result.stdout.rstrip("\n")


def read_prompt() -> str:
    raw = sys.stdin.buffer.read(32001)
    if len(raw) > 32000:
        raise ValueError("Selected text exceeds the 32,000-byte limit.")
    try:
        selected = raw.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise ValueError("Selected text must be UTF-8.") from error
    if selected:
        dialog(
            "Send the selected text to the local Ollama model "
            f"{MODEL}? Do not send sensitive information.",
            confirm=True,
        )
        return selected
    message = dialog(
        f"Enter a prompt for the local Ollama model {MODEL}. "
        "Do not enter sensitive information.",
        prompt=True,
    ).strip()
    if not message or len(message.encode("utf-8")) > 32000:
        raise ValueError("The prompt must contain 1 to 32,000 UTF-8 bytes.")
    return message


def ask_model(prompt: str) -> str:
    return AetherHistorian(host="127.0.0.1", model=MODEL, timeout=120).query_brain(
        prompt,
        system=(
            "You are Galileo, a practical local assistant. "
            "Only the user's current prompt is provided. "
            "Do not claim access to files, tools, or conversation history."
        ),
    )


def snapshot_sqlite(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise FileNotFoundError(f"Database is missing or is a symlink: {source}")
    uri = f"file:{quote(str(source.resolve()))}?mode=ro"
    with sqlite3.connect(uri, uri=True) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
        result = dst.execute("PRAGMA quick_check").fetchone()
        if result != ("ok",):
            raise ValueError(f"Database snapshot failed integrity check: {source}")
    destination.chmod(0o600)


def backup_databases(project: Path, galileo_directory: Path) -> tuple[Path, Path]:
    if galileo_directory.is_symlink():
        raise ValueError(
            f"Galileo data directory cannot be a symlink: {galileo_directory}"
        )
    aether_source = project / ".aether-engine.sqlite3"
    galileo_source = galileo_directory / "conversations.sqlite3"
    for source in (aether_source, galileo_source):
        if source.is_symlink() or not source.is_file():
            raise FileNotFoundError(f"Database is missing or is a symlink: {source}")
    aether_directory = project / ".aether-backups"
    galileo_backups = galileo_directory / "Backups"
    secure_backup_directory(aether_directory)
    secure_backup_directory(galileo_backups)
    with tempfile.TemporaryDirectory(prefix=".automator-", dir=galileo_backups) as tmp:
        temp = Path(tmp)
        aether_snapshot = temp / "aether.sqlite3"
        galileo_snapshot = temp / "galileo.sqlite3"
        snapshot_sqlite(aether_source, aether_snapshot)
        snapshot_sqlite(galileo_source, galileo_snapshot)
        with sqlite3.connect(aether_snapshot) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if not {"tasks", "events"} <= tables:
                raise ValueError("Aether database does not contain expected tables.")
        with sqlite3.connect(galileo_snapshot) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if not {"conversations", "messages"} <= tables:
                raise ValueError("Galileo database does not contain expected tables.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        galileo_path = galileo_backups / f"galileo-backup-{stamp}.sqlite3"
        os.link(galileo_snapshot, galileo_path)
        try:
            aether_path, _ = write_backup(
                AetherStore(aether_snapshot), directory=aether_directory
            )
        except (OSError, sqlite3.Error, ValueError):
            galileo_path.unlink()
            raise
    return aether_path, galileo_path


def run(
    action: str, *, project: Path = PROJECT, galileo_directory: Path | None = None
) -> None:
    if action == "launch":
        app = project / "dist" / "Galileo.app"
        if not (app / "Contents" / "MacOS" / "Galileo").is_file():
            raise FileNotFoundError(
                f"Build Galileo first; application not found: {app}"
            )
        subprocess.run(["/usr/bin/open", str(app)], check=True)
    elif action == "prompt":
        response = ask_model(read_prompt())
        dialog(f"Galileo response:\n\n{response}")
    elif action == "test":
        dialog(
            "Run the complete Python project test suite, including isolated "
            "backend readiness (task persistence, dispatch, SSE reconnect/restart, "
            "and clean shutdown)? No model server is required.",
            confirm=True,
        )
        interpreter = (
            project / ".venv" / "bin" / "python"
            if getattr(sys, "frozen", False)
            else Path(sys.executable)
        )
        if not interpreter.is_file():
            raise FileNotFoundError(
                "Project test interpreter is missing; prepare the project's .venv."
            )
        result = subprocess.run(
            [str(interpreter), "-m", "pytest", "-q"],
            cwd=project,
            text=True,
            capture_output=True,
            check=False,
        )
        output = (result.stdout + "\n" + result.stderr).strip()
        message = f"Tests exited with code {result.returncode}.\n\n{output[-8000:]}"
        dialog(message)
        if result.returncode:
            raise RuntimeError("Project tests failed; see the result dialog.")
    elif action == "backup":
        galileo_dir = (
            galileo_directory
            or Path(
                os.environ.get(
                    "GALILEO_DATA_DIR",
                    str(Path.home() / "Library" / "Application Support" / "Galileo"),
                )
            ).expanduser()
        )
        dialog(
            "Create local backups of the project task/event database and "
            f"Galileo conversations in {galileo_dir}? Backups are not encrypted.",
            confirm=True,
        )
        aether, galileo = backup_databases(project, galileo_dir)
        dialog(f"Backups created:\n\n{aether}\n\n{galileo}")
    else:
        raise ValueError(f"Unknown action: {action}")


def run_reported(
    action: str, *, project: Path = PROJECT, galileo_directory: Path | None = None
) -> None:
    """Record action metadata in Matrix without storing prompts or responses."""
    if action not in {"launch", "prompt", "test", "backup"}:
        raise ValueError(f"Unknown action: {action}")
    database = Path(
        os.environ.get("AETHER_DATABASE_PATH", str(project / ".aether-engine.sqlite3"))
    ).expanduser()
    store = AetherStore(database)
    started = perf_counter()

    def report(outcome: str) -> None:
        store.add_event(
            "automator",
            json.dumps(
                {
                    "node": "MATRIX",
                    "component": "automator",
                    "action": action,
                    "outcome": outcome,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                    "model": MODEL if action == "prompt" else None,
                },
                separators=(",", ":"),
            ),
        )

    report("started")
    try:
        run(action, project=project, galileo_directory=galileo_directory)
    except InterruptedError:
        report("cancelled")
        raise
    except (
        OSError,
        sqlite3.Error,
        ValueError,
        RuntimeError,
        subprocess.CalledProcessError,
        OllamaConnectionError,
    ):
        report("failed")
        raise
    report("succeeded")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "prompt", "test", "backup"))
    args = parser.parse_args()
    try:
        run_reported(args.action)
    except InterruptedError:
        return 0
    except (
        OSError,
        ValueError,
        RuntimeError,
        sqlite3.Error,
        subprocess.SubprocessError,
        OllamaConnectionError,
    ) as error:
        print(f"Automator action failed: {error}", file=sys.stderr)
        try:
            dialog(f"Automator action failed:\n\n{error}")
        except (OSError, RuntimeError, InterruptedError) as dialog_error:
            print(f"Could not display error: {dialog_error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
