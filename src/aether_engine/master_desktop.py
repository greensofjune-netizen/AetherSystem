"""Native window and bounded loopback lifecycle for Aether Master Matrix."""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import threading
import urllib.request
from pathlib import Path
from typing import Any, Sequence


def configure_data_directory(directory: Path) -> Path:
    directory = directory.expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    for key, name in (
        ("AETHER_DATABASE_PATH", "tasks.sqlite3"),
        ("AETHER_HISTORIAN_LOG_FILE", "simulated-telemetry.json"),
        ("AETHER_HISTORY_ARCHIVE", "history.sqlite3"),
        ("AETHER_PROPULSION_ARCHIVE", "propulsion.sqlite3"),
    ):
        path = directory / name
        if path.is_symlink():
            raise ValueError(f"Desktop data file cannot be a symlink: {path}")
        os.environ[key] = str(path)
    return directory


class MasterDesktopServer:
    def __init__(self) -> None:
        self.matrix = importlib.import_module("aether_master_matrix")
        self.server = self.matrix.LocalThreadingHTTPServer(
            ("127.0.0.1", 0), self.matrix.HistorianLiveServer
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.1},
            name="master-matrix-http",
            daemon=True,
        )

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/"

    def start(self, *, preload_model: bool = True) -> None:
        self.thread.start()
        try:
            with urllib.request.urlopen(self.url + "api/clock", timeout=5) as response:
                if response.status != 200 or "utc" not in json.load(response):
                    raise RuntimeError("Master Matrix readiness check failed.")
            if preload_model:
                self.matrix._preload_copernicus_model()
        except (OSError, ValueError, RuntimeError):
            self.stop()
            raise

    def stop(self) -> None:
        if self.thread.ident is not None and self.thread.is_alive():
            self.server.shutdown()
            self.thread.join(timeout=5)
        self.server.server_close()
        if self.thread.is_alive():
            raise RuntimeError("Master Matrix server did not stop cleanly.")


def run_desktop(server: MasterDesktopServer, webview: Any) -> None:
    try:
        server.start()
        webview.create_window(
            "Aether Master Matrix — Local Release Candidate",
            server.url,
            width=1280,
            height=860,
            min_size=(800, 600),
            background_color="#120b07",
        )
        webview.start()
    finally:
        server.stop()


def smoke_test(server: MasterDesktopServer) -> None:
    try:
        server.start(preload_model=False)
        for route in (
            "", "api/clock", "api/model/status", "weather", "weather.css",
            "weather.js", "copernicus.js", "persona_matrix.js", "persona_matrix.css",
            "stargazer", "stargazer.css", "stargazer.js", "astronomy.css", "speech.js",
        ):
            with urllib.request.urlopen(server.url + route, timeout=5) as response:
                if response.status != 200 or not response.read():
                    raise RuntimeError(f"Desktop smoke check failed: /{route}")
        print("Master Matrix smoke check passed; no model or simulation requested.")
    finally:
        server.stop()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aether Master Matrix local Mac app.")
    parser.add_argument(
        "--data-directory", type=Path,
        default=Path.home() / "Library" / "Application Support" / "AetherSystem" / "MasterMatrix",
        help="Separate desktop data directory; existing project records are not imported.",
    )
    parser.add_argument(
        "--smoke-test", action="store_true",
        help="Check packaged HTTP assets and shutdown without a window, AI or simulation.",
    )
    args = parser.parse_args(argv)
    try:
        directory = configure_data_directory(args.data_directory)
        log_path = directory / "desktop.log"
        if log_path.is_symlink():
            raise ValueError("Desktop log cannot be a symlink.")
        logging.basicConfig(
            filename=log_path, level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )
        log_path.chmod(0o600)
        if args.smoke_test:
            smoke_test(MasterDesktopServer())
        else:
            webview = importlib.import_module("webview")
            run_desktop(MasterDesktopServer(), webview)
    except KeyboardInterrupt:
        return 0
    except (ImportError, OSError, RuntimeError, ValueError):
        logging.exception("Master Matrix desktop launch failed")
        print("Master Matrix could not launch. See the selected data directory's desktop.log.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
