"""Native Galileo window and a bounded, loopback-only backend lifecycle."""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import uvicorn

from aether_engine.desktop_voice import DesktopVoice, VoiceResult
from aether_engine.galileo import (
    DEFAULT_MODEL,
    create_app,
    default_data_directory,
)
from automator import bridge


class DesktopActions:
    """Expose only voice and manually confirmed, allowlisted Matrix actions."""

    def __init__(self, data_directory: Path, project_directory: Path):
        self.voice = DesktopVoice()
        self.data_directory = data_directory
        self.project_directory = project_directory
        self._action_lock = threading.Lock()

    def dictation(self) -> VoiceResult:
        return self.voice.dictation()

    def stop_dictation(self) -> VoiceResult:
        return self.voice.stop_dictation()

    def speak(self, text: str) -> VoiceResult:
        return self.voice.speak(text)

    def stop_speaking(self) -> VoiceResult:
        return self.voice.stop_speaking()

    def matrix_status(self) -> dict[str, Any]:
        return {
            "available": (self.project_directory / "pyproject.toml").is_file(),
            "project": str(self.project_directory),
            "actions": ["test", "backup"],
            "node": "MATRIX",
        }

    def run_matrix_action(self, action: str) -> dict[str, Any]:
        if action not in {"test", "backup"}:
            return {"ok": False, "error": "This desktop action is not allowed."}
        if not self.matrix_status()["available"]:
            return {"ok": False, "error": "The linked project is unavailable."}
        if not self._action_lock.acquire(blocking=False):
            return {"ok": False, "error": "Another Matrix action is still running."}
        try:
            bridge.run_reported(
                action,
                project=self.project_directory,
                galileo_directory=self.data_directory,
            )
        except InterruptedError:
            return {"ok": False, "error": "Action cancelled; nothing was requested."}
        except (
            OSError,
            sqlite3.Error,
            ValueError,
            RuntimeError,
            subprocess.CalledProcessError,
            bridge.OllamaConnectionError,
        ) as error:
            logging.exception("Galileo Matrix action failed")
            return {"ok": False, "error": str(error)}
        finally:
            self._action_lock.release()
        return {"ok": True, "action": action}


class DesktopServer:
    def __init__(
        self, data_directory: Path, model: str = DEFAULT_MODEL, *,
        aristotle_project: Path | None = None,
    ):
        self.data_directory = data_directory
        self.aristotle = aristotle_project is not None
        self.app = create_app(
            data_directory, default_model=model, aristotle_project=aristotle_project
        )
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(128)
        self.port = self.socket.getsockname()[1]
        self.server = uvicorn.Server(
            uvicorn.Config(
                self.app,
                host="127.0.0.1",
                port=self.port,
                log_level="warning",
                access_log=False,
                timeout_graceful_shutdown=5,
            )
        )
        self.thread = threading.Thread(
            target=self.server.run,
            kwargs={"sockets": [self.socket]},
            name="galileo-http",
            daemon=True,
        )

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?token={self.app.state.token}"

    def start(self) -> None:
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                self.stop()
                raise RuntimeError("Galileo's local server failed to start.")
            time.sleep(0.02)

    def stop(self) -> None:
        try:
            self.app.state.engine_runtime.stop()
        finally:
            self.server.should_exit = True
            if self.thread.ident is not None:
                self.thread.join(timeout=8)
                if self.thread.is_alive():
                    self.server.force_exit = True
                    self.thread.join(timeout=2)
            self.socket.close()
        if self.thread.is_alive():
            raise RuntimeError("Galileo's local server did not stop cleanly.")


def run_desktop(
    server: DesktopServer, webview: Any, project_directory: Path | None = None
) -> None:
    actions = DesktopActions(
        server.data_directory,
        project_directory or Path(__file__).resolve().parents[2],
    )
    try:
        server.start()
        webview.create_window(
            "Matrix Aristotle" if server.aristotle else "Galileo",
            server.url,
            width=1080,
            height=680,
            min_size=(760, 520),
            background_color="#120b07",
            js_api=actions,
        )
        webview.start()
    finally:
        try:
            actions.voice.close()
        finally:
            server.stop()


def main(*, project_directory: Path | None = None, aristotle: bool = False) -> int:
    app_name = "Matrix Aristotle" if aristotle else "Galileo"
    parser = argparse.ArgumentParser(description=f"{app_name} local desktop companion.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--project-directory",
        type=Path,
        default=Path(
            os.environ.get(
                "AETHER_PROJECT_PATH",
                str(project_directory or Path(__file__).resolve().parents[2]),
            )
        ),
    )
    parser.add_argument("--data-directory", type=Path, default=default_data_directory())
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Run a development browser preview instead of the native window.",
    )
    args = parser.parse_args()
    server = DesktopServer(
        args.data_directory, args.model,
        aristotle_project=args.project_directory if aristotle else None,
    )
    log_path = args.data_directory / "galileo.log"
    if log_path.is_symlink():
        server.stop()
        parser.error("Galileo log file cannot be a symlink.")
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    log_path.chmod(0o600)
    try:
        if args.browser:
            server.start()
            print(f"{app_name} browser preview: {server.url}", flush=True)
            try:
                while server.thread.is_alive():
                    time.sleep(0.2)
            finally:
                server.stop()
        else:
            run_desktop(
                server, importlib.import_module("webview"), args.project_directory
            )
    except KeyboardInterrupt:
        return 0
    except (ImportError, OSError, RuntimeError, ValueError):
        logging.exception("%s could not run", app_name)
        print(
            f"{app_name} could not run. See {args.data_directory / 'galileo.log'}.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
