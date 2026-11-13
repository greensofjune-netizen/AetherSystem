import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from aether_engine.master_desktop import configure_data_directory, run_desktop


def test_desktop_window_closes_backend_on_exit_and_failure():
    for failure in (False, True):
        server = Mock()
        server.url = "http://127.0.0.1:12345/"
        webview = Mock()
        if failure:
            webview.start.side_effect = RuntimeError("Window failed")
            with pytest.raises(RuntimeError, match="Window failed"):
                run_desktop(server, webview)
        else:
            run_desktop(server, webview)
        server.start.assert_called_once_with()
        server.stop.assert_called_once_with()
        assert webview.create_window.call_args.args[1] == server.url
        assert "js_api" not in webview.create_window.call_args.kwargs


def test_desktop_rejects_symlinked_data_file(tmp_path, monkeypatch):
    for key in ("AETHER_DATABASE_PATH", "AETHER_HISTORIAN_LOG_FILE",
                "AETHER_HISTORY_ARCHIVE", "AETHER_PROPULSION_ARCHIVE"):
        monkeypatch.delenv(key, raising=False)
    target = tmp_path / "outside"
    target.write_text("untouched")
    directory = tmp_path / "desktop"
    directory.mkdir()
    (directory / "tasks.sqlite3").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        configure_data_directory(directory)
    assert target.read_text() == "untouched"


def test_desktop_source_smoke_and_private_paths(tmp_path):
    root = Path(__file__).resolve().parents[1]
    directory = tmp_path / "data"
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("AETHER_")}
    environment["PYTHONPATH"] = str(root / "src") + os.pathsep + str(root)
    result = subprocess.run(
        [sys.executable, "-m", "aether_engine.master_desktop",
         "--smoke-test", "--data-directory", str(directory)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "smoke check passed" in result.stdout
    assert not (directory / "simulated-telemetry.json").exists()
    assert not (directory / "history.sqlite3").exists()
    assert not (directory / "propulsion.sqlite3").exists()
    if os.name == "posix":
        assert directory.stat().st_mode & 0o077 == 0
        assert (directory / "desktop.log").stat().st_mode & 0o077 == 0


def test_desktop_real_restart_persistence_origin_checks_and_shutdown(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = """
import sys
import urllib.error
import urllib.request
from pathlib import Path
from aether_engine.master_desktop import configure_data_directory, MasterDesktopServer

directory = configure_data_directory(Path(sys.argv[1]))
server = MasterDesktopServer()
matrix = server.matrix
assert matrix.LOG_FILE == directory / "simulated-telemetry.json"
assert matrix._aether_database_path() == directory / "tasks.sqlite3"
history = matrix.UniversalHistoryArchive()
propulsion = matrix.KineticPropulsionArchive()
assert history.db_path == directory / "history.sqlite3"
assert propulsion.db_path == directory / "propulsion.sqlite3"
if sys.argv[2] == "write":
    matrix.log_telemetry_event(1, 1.0, 2.0, 3.0, "DISPOSABLE DESKTOP TEST")
else:
    assert matrix._read_telemetry()[-1]["system_status"] == "DISPOSABLE DESKTOP TEST"
    assert history.db_path.is_file() and propulsion.db_path.is_file()
try:
    server.start(preload_model=False)
    assert server.server.server_address[0] == "127.0.0.1"
    assert server.matrix._copernicus_model_status["status"] == "pending"
    for headers in ({"Host": "untrusted.example"}, {"Origin": "https://untrusted.example"}):
        request = urllib.request.Request(server.url + "api/clock", headers=headers)
        try:
            urllib.request.urlopen(request, timeout=2)
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("Unexpected cross-origin access")
    with urllib.request.urlopen(server.url, timeout=2) as response:
        assert b"DISPOSABLE DESKTOP TEST" in response.read()
finally:
    server.stop()
assert not server.thread.is_alive()
try:
    urllib.request.urlopen(server.url, timeout=1)
except urllib.error.URLError:
    pass
else:
    raise AssertionError("Listener survived shutdown")
"""
    environment = dict(os.environ, PYTHONPATH=str(root / "src") + os.pathsep + str(root))
    for mode in ("write", "read"):
        result = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path / "desktop"), mode],
            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
