"""Real loopback HTTP readiness journey, also run by Automator's pytest action."""

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVER = """
import socket
import sys
from pathlib import Path
from threading import Thread

import uvicorn

with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    server = uvicorn.Server(uvicorn.Config(
        "aether_engine.server:app", log_level="warning", access_log=False,
    ))
    def stop_on_input():
        sys.stdin.readline()
        server.should_exit = True
    Thread(target=stop_on_input, daemon=True).start()
    port_file = Path(sys.argv[1])
    pending = port_file.with_suffix(".tmp")
    pending.write_text(str(listener.getsockname()[1]), encoding="ascii")
    pending.replace(port_file)
    server.run(sockets=[listener])
"""


@contextmanager
def running_backend(directory: Path) -> Iterator[httpx.Client]:
    port_file = directory / "port.txt"
    port_file.unlink(missing_ok=True)
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("AETHER_")
    }
    environment.update(
        AETHER_DATABASE_PATH=str(directory / "readiness.sqlite3"),
        AETHER_MODEL_PATH=str(directory / "no-model.gguf"),
        PYTHONPATH=str(ROOT / "src"),
    )
    log_path = directory / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", SERVER, str(port_file)],
            cwd=directory,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=log,
            text=True,
        )
        try:
            deadline = time.monotonic() + 20
            with httpx.Client(timeout=2, trust_env=False) as client:
                while time.monotonic() < deadline:
                    assert process.poll() is None, log_path.read_text()
                    if port_file.exists():
                        port = int(port_file.read_text(encoding="ascii"))
                        client.base_url = f"http://127.0.0.1:{port}"
                        try:
                            response = client.get("/health")
                        except httpx.TransportError:
                            time.sleep(0.05)
                            continue
                        assert response.status_code == 200, response.text
                        assert response.json()["model_available"] is False
                        break
                    time.sleep(0.05)
                else:
                    pytest.fail(f"Backend did not become ready:\n{log_path.read_text()}")
                yield client
        finally:
            try:
                process.communicate(
                    input="stop\n" if process.poll() is None else None, timeout=10
                )
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                pytest.fail(f"Backend did not stop gracefully:\n{log_path.read_text()}")
            assert process.returncode == 0, log_path.read_text()


def stream_events(response: httpx.Response) -> Iterator[dict[str, str]]:
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    fields: dict[str, str] = {}
    for line in response.iter_lines():
        if not line:
            if "data" in fields:
                yield fields
            fields = {}
        elif ":" in line:
            key, value = line.split(":", 1)
            fields[key] = value.lstrip()


def read_dispatch(client: httpx.Client, cursor: int) -> dict:
    with client.stream(
        "GET", "/api/v1/unified/stream", headers={"Last-Event-ID": str(cursor)}
    ) as response:
        for fields in stream_events(response):
            assert fields["event"] == "dispatch"
            record = json.loads(fields["data"])
            assert int(fields["id"]) == record["event_id"] > cursor
            return record
    pytest.fail("The stream closed without a dispatch event.")


def test_backend_readiness_task_dispatch_reconnect_and_restart(tmp_path: Path) -> None:
    database = tmp_path / "readiness.sqlite3"
    with running_backend(tmp_path) as client:
        created = client.post("/api/v1/tasks", json={"title": "Readiness test"})
        assert created.status_code == 201, created.text
        task = created.json()
        assert task in client.get("/api/v1/tasks").json()
        exported = subprocess.run(
            [
                sys.executable, "-m", "aether_engine",
                "--database", str(database), "export",
            ],
            cwd=tmp_path,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        assert json.loads(exported.stdout)["tasks"] == [task]

        envelope = {
            "protocol_version": "1.0.0",
            "source_lang": "python",
            "node": "ATLAS",
            "event": "READINESS_TEST",
            "timestamp": 1.0,
            "payload": {"sequence": 1},
        }
        first = client.post("/api/v1/unified/dispatch", json=envelope)
        assert first.status_code == 200, first.text
        assert first.json()["persisted"] is True
        first_id = first.json()["event_id"]
        replay = read_dispatch(client, 0)
        assert replay["event_id"] == first_id
        assert replay["envelope"] == envelope

        with client.stream("GET", "/api/v1/unified/stream") as response:
            events = stream_events(response)
            snapshot = next(events)
            assert snapshot["event"] == "snapshot"
            assert int(snapshot["id"]) == first_id
            assert json.loads(snapshot["data"]) == replay

            envelope["payload"] = {"sequence": 2}
            second = client.post("/api/v1/unified/dispatch", json=envelope)
            assert second.status_code == 200, second.text
            assert second.json()["persisted"] is True
            assert second.json()["live_subscribers_notified"] >= 1
            second_id = second.json()["event_id"]
            assert second_id > first_id
            live = next(events)
            assert live["event"] == "dispatch"
            assert int(live["id"]) == second_id
            live_record = json.loads(live["data"])
            assert live_record["event_id"] == second_id
            assert live_record["envelope"] == envelope

        replay = read_dispatch(client, first_id)
        assert replay["event_id"] == second_id
        assert replay["envelope"] == envelope
        assert replay == live_record
        assert client.get("/api/v1/unified/state").json()["last_dispatch"] == replay
        oversized = client.post(
            "/api/v1/unified/dispatch",
            content=b" " * 32_769,
            headers={"Content-Type": "application/json"},
        )
        assert oversized.status_code == 413

    with running_backend(tmp_path) as client:
        assert client.get("/api/v1/tasks").json() == [task]
        replay = read_dispatch(client, first_id)
        assert replay["event_id"] == second_id
        assert replay["envelope"] == envelope


def test_backup_recovery_preserves_records_and_refuses_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "restored"
    source.mkdir()
    destination.mkdir()
    with running_backend(source) as client:
        for title, priority in (("Pending recovery task", "low"), ("Done task", "high")):
            response = client.post(
                "/api/v1/tasks",
                json={
                    "title": title,
                    "description": "Preserve task metadata",
                    "priority": priority,
                    "due_date": "2026-12-01",
                },
            )
            assert response.status_code == 201, response.text
        completed = client.post(f"/api/v1/tasks/{response.json()['id']}/complete")
        assert completed.status_code == 200, completed.text
        for message in ("First recovery event", "Second recovery event"):
            response = client.post(
                "/api/v1/events", json={"topic": "recovery", "message": message}
            )
            assert response.status_code == 201, response.text
        exported = client.get("/api/v1/export")
        assert exported.status_code == 200, exported.text
        expected = exported.json()
        backup = client.post("/api/v1/backups", json={})
        assert backup.status_code == 201, backup.text
        backup_path = Path(backup.json()["path"])
        assert backup_path.parent == source / ".aether-backups"
        backup_bytes = backup_path.read_bytes()
        saved = json.loads(backup_bytes)
        assert saved["schema_version"] == expected["schema_version"] == 1
        assert saved["tasks"] == expected["tasks"]
        assert saved["events"] == expected["events"]

    result = subprocess.run(
        [
            sys.executable, "-m", "aether_engine",
            "--database", str(destination / "readiness.sqlite3"),
            "restore", str(backup_path),
        ],
        cwd=destination,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with running_backend(destination) as client:
        recovered = client.get("/api/v1/export")
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["tasks"] == expected["tasks"]
        assert recovered.json()["events"] == expected["events"]
        assert {task["status"] for task in expected["tasks"]} == {"pending", "done"}

        rejected = client.post("/api/v1/restore", json={"backup": saved})
        assert rejected.status_code == 422, rejected.text
        assert "use --replace" in rejected.json()["detail"]
        unchanged = client.get("/api/v1/export")
        assert unchanged.status_code == 200, unchanged.text
        assert unchanged.json()["tasks"] == expected["tasks"]
        assert unchanged.json()["events"] == expected["events"]
    assert backup_path.read_bytes() == backup_bytes
