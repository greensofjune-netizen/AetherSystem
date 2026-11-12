"""Real loopback HTTP readiness journey, also run by Automator's pytest action."""

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier

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
def running_backend(
    directory: Path, *, abrupt_stop: bool = False,
) -> Iterator[httpx.Client]:
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
        killed = False
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
                if abrupt_stop:
                    assert process.poll() is None, log_path.read_text()
                    process.kill()
                    killed = True
        finally:
            try:
                process.communicate(
                    input="stop\n" if not killed and process.poll() is None else None,
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                pytest.fail(f"Backend did not stop gracefully:\n{log_path.read_text()}")
            expected_exit = (-signal.SIGKILL if os.name == "posix" else 1) if killed else 0
            assert process.returncode == expected_exit, log_path.read_text()


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


def test_acknowledged_writes_survive_abrupt_backend_stop(tmp_path: Path) -> None:
    tasks = []
    dispatches = []
    with running_backend(tmp_path, abrupt_stop=True) as client:
        for sequence in range(3):
            created = client.post(
                "/api/v1/tasks",
                json={"title": f"Crash recovery task {sequence}", "priority": "high"},
            )
            assert created.status_code == 201, created.text
            tasks.append(created.json())
            envelope = {
                "protocol_version": "1.0.0",
                "source_lang": "python",
                "node": "ATLAS",
                "event": "CRASH_RECOVERY_TEST",
                "timestamp": float(sequence),
                "payload": {"sequence": sequence, "task_id": tasks[-1]["id"]},
            }
            dispatched = client.post("/api/v1/unified/dispatch", json=envelope)
            assert dispatched.status_code == 200, dispatched.text
            assert dispatched.json()["status"] == "ACCEPTED"
            assert dispatched.json()["persisted"] is True
            dispatches.append(
                {"event_id": dispatched.json()["event_id"], "envelope": envelope}
            )

    with running_backend(tmp_path) as client:
        exported = client.get("/api/v1/export")
        assert exported.status_code == 200, exported.text
        recovered = exported.json()
        assert recovered["tasks"] == tasks
        assert len({task["id"] for task in tasks}) == 3
        assert len(recovered["events"]) == len(dispatches) == 3
        assert len({record["event_id"] for record in dispatches}) == 3
        expected_replay = []
        for event, acknowledged in zip(recovered["events"], dispatches, strict=True):
            assert event["topic"] == "unified-dispatch"
            assert event["id"] == acknowledged["event_id"]
            assert json.loads(event["message"]) == acknowledged["envelope"]
            expected_replay.append(
                {
                    "event_id": event["id"],
                    "created_at": event["created_at"],
                    "envelope": acknowledged["envelope"],
                }
            )
        with client.stream(
            "GET", "/api/v1/unified/stream", headers={"Last-Event-ID": "0"}
        ) as response:
            replay = stream_events(response)
            for record in expected_replay:
                received = next(replay)
                assert received["event"] == "dispatch"
                assert int(received["id"]) == record["event_id"]
                assert json.loads(received["data"]) == record
        state = client.get("/api/v1/unified/state")
        assert state.status_code == 200, state.text
        assert state.json()["last_dispatch"] == expected_replay[-1]
        subsequent = client.post(
            "/api/v1/tasks", json={"title": "Writable after crash recovery"}
        )
        assert subsequent.status_code == 201, subsequent.text
        assert subsequent.json()["id"] > max(task["id"] for task in tasks)
        final = client.get("/api/v1/export")
        assert final.status_code == 200, final.text
        assert final.json()["tasks"] == [*tasks, subsequent.json()]
        assert final.json()["events"] == recovered["events"]


def test_concurrent_clients_preserve_every_write_after_restart(tmp_path: Path) -> None:
    client_count = 8
    writes_per_client = 3
    start = Barrier(client_count, timeout=15)

    def write_batch(base_url: str, worker: int) -> tuple[list[dict], list[dict]]:
        with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as writer:
            tasks = []
            dispatches = []
            start.wait()
            for sequence in range(writes_per_client):
                created = writer.post(
                    "/api/v1/tasks",
                    json={
                        "title": f"Concurrent task {worker}-{sequence}",
                        "description": f"Client {worker}, write {sequence}",
                        "priority": "high" if worker % 2 else "low",
                    },
                )
                assert created.status_code == 201, created.text
                task = created.json()
                assert task["title"] == f"Concurrent task {worker}-{sequence}"
                assert task["description"] == f"Client {worker}, write {sequence}"
                assert task["priority"] == ("high" if worker % 2 else "low")
                tasks.append(task)
            start.wait()
            for sequence in range(writes_per_client):
                envelope = {
                    "protocol_version": "1.0.0",
                    "source_lang": "python",
                    "node": "ATLAS",
                    "event": "CONCURRENCY_TEST",
                    "timestamp": float(worker * writes_per_client + sequence),
                    "payload": {"client": worker, "sequence": sequence},
                }
                dispatched = writer.post("/api/v1/unified/dispatch", json=envelope)
                assert dispatched.status_code == 200, dispatched.text
                assert dispatched.json()["status"] == "ACCEPTED"
                assert dispatched.json()["persisted"] is True
                dispatches.append(
                    {"event_id": dispatched.json()["event_id"], "envelope": envelope}
                )
            return tasks, dispatches

    def verify_records(client: httpx.Client) -> dict:
        exported = client.get("/api/v1/export")
        assert exported.status_code == 200, exported.text
        snapshot = exported.json()
        assert snapshot["tasks"] == expected_tasks
        assert len(snapshot["events"]) == client_count * writes_per_client
        assert len({event["id"] for event in snapshot["events"]}) == len(dispatches)
        expected_replay = []
        for event in snapshot["events"]:
            assert event["topic"] == "unified-dispatch"
            assert json.loads(event["message"]) == dispatches[event["id"]]
            expected_replay.append(
                {
                    "event_id": event["id"],
                    "created_at": event["created_at"],
                    "envelope": dispatches[event["id"]],
                }
            )
        with client.stream(
            "GET", "/api/v1/unified/stream", headers={"Last-Event-ID": "0"}
        ) as response:
            events = stream_events(response)
            for record in expected_replay:
                replayed = next(events)
                assert replayed["event"] == "dispatch"
                assert int(replayed["id"]) == record["event_id"]
                assert json.loads(replayed["data"]) == record
        state = client.get("/api/v1/unified/state")
        assert state.status_code == 200, state.text
        assert state.json()["last_dispatch"] == expected_replay[-1]
        return snapshot

    with running_backend(tmp_path) as client:
        with ThreadPoolExecutor(max_workers=client_count) as executor:
            futures = [
                executor.submit(write_batch, str(client.base_url), worker)
                for worker in range(client_count)
            ]
            batches = [future.result(timeout=30) for future in futures]
        expected_tasks = sorted(
            (task for tasks, _ in batches for task in tasks),
            key=lambda task: task["id"],
        )
        expected_count = client_count * writes_per_client
        assert len(expected_tasks) == expected_count
        assert len({task["id"] for task in expected_tasks}) == expected_count
        assert {task["title"] for task in expected_tasks} == {
            f"Concurrent task {worker}-{sequence}"
            for worker in range(client_count)
            for sequence in range(writes_per_client)
        }
        dispatches = {
            record["event_id"]: record["envelope"]
            for _, records in batches
            for record in records
        }
        assert len(dispatches) == expected_count
        assert {
            (envelope["payload"]["client"], envelope["payload"]["sequence"])
            for envelope in dispatches.values()
        } == {
            (worker, sequence)
            for worker in range(client_count)
            for sequence in range(writes_per_client)
        }
        before_restart = verify_records(client)

    with running_backend(tmp_path) as client:
        after_restart = verify_records(client)
        assert after_restart["tasks"] == before_restart["tasks"]
        assert after_restart["events"] == before_restart["events"]


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


@pytest.mark.parametrize("surface", ["http", "cli"])
@pytest.mark.parametrize("damage", ["truncated-json", "invalid-event"])
def test_damaged_backup_rejection_and_subsequent_recovery(
    tmp_path: Path, surface: str, damage: str,
) -> None:
    with running_backend(tmp_path) as client:
        task = client.post(
            "/api/v1/tasks",
            json={"title": "Recover this task", "priority": "high"},
        )
        assert task.status_code == 201, task.text
        for message in ("First saved event", "Last saved event"):
            event = client.post(
                "/api/v1/events", json={"topic": "damaged-backup", "message": message}
            )
            assert event.status_code == 201, event.text
        backup = client.post("/api/v1/backups", json={})
        assert backup.status_code == 201, backup.text
        backup_path = Path(backup.json()["path"])
        backup_bytes = backup_path.read_bytes()
        expected = json.loads(backup_bytes)

        updated = client.patch(
            f"/api/v1/tasks/{task.json()['id']}",
            json={"title": "Keep current data until a valid restore"},
        )
        assert updated.status_code == 200, updated.text
        added = client.post(
            "/api/v1/events",
            json={"topic": "damaged-backup", "message": "Not present in the backup"},
        )
        assert added.status_code == 201, added.text
        exported = client.get("/api/v1/export")
        assert exported.status_code == 200, exported.text
        baseline = exported.json()

        damaged = json.loads(backup_bytes)
        if damage == "truncated-json":
            damaged_bytes = backup_bytes.rstrip()[:-1]
        else:
            damaged["events"][-1]["created_at"] = "not-a-timestamp"
            damaged_bytes = json.dumps(damaged).encode("utf-8")
        damaged_path = tmp_path / "damaged-backup.json"
        damaged_path.write_bytes(damaged_bytes)

        for valid in (False, True):
            if surface == "http":
                content = (
                    b'{"replace": true, "backup": '
                    + (backup_bytes if valid else damaged_bytes)
                    + b"}"
                )
                response = client.post(
                    "/api/v1/restore",
                    content=content,
                    headers={"Content-Type": "application/json"},
                )
                assert response.status_code == (200 if valid else 422), response.text
                if valid:
                    assert response.json()["tasks_restored"] == len(expected["tasks"])
                    assert response.json()["events_restored"] == len(expected["events"])
                    safety_path = Path(response.json()["safety_backup"])
                elif damage == "truncated-json":
                    assert response.json()["detail"][0]["type"] == "json_invalid"
                else:
                    assert response.json()["detail"] == (
                        "Backup event at index 1 has an invalid created_at."
                    )
            else:
                result = subprocess.run(
                    [
                        sys.executable, "-m", "aether_engine",
                        "--database", str(tmp_path / "readiness.sqlite3"),
                        "restore", str(backup_path if valid else damaged_path),
                        "--replace",
                    ],
                    cwd=tmp_path,
                    env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                assert result.returncode == (0 if valid else 1), (
                    result.stdout + result.stderr
                )
                if valid:
                    assert "Restored 1 task(s) and 2 event(s)" in result.stdout
                else:
                    assert "error:" in result.stderr
                    assert "Restored" not in result.stdout
                    if damage == "truncated-json":
                        assert "Expecting ',' delimiter" in result.stderr
                    else:
                        assert (
                            "Backup event at index 1 has an invalid created_at."
                            in result.stderr
                        )

            recovered = client.get("/api/v1/export")
            assert recovered.status_code == 200, recovered.text
            records = expected if valid else baseline
            assert recovered.json()["tasks"] == records["tasks"]
            assert recovered.json()["events"] == records["events"]
            snapshots = sorted(backup_path.parent.glob("aether-backup-*.json"))
            assert len(snapshots) == (2 if valid else 1)
            if valid:
                if surface == "cli":
                    safety_path = next(path for path in snapshots if path != backup_path)
                safety = json.loads(safety_path.read_bytes())
                assert safety["tasks"] == baseline["tasks"]
                assert safety["events"] == baseline["events"]
            assert backup_path.read_bytes() == backup_bytes
            assert damaged_path.read_bytes() == damaged_bytes

    with running_backend(tmp_path) as client:
        persisted = client.get("/api/v1/export")
        assert persisted.status_code == 200, persisted.text
        assert persisted.json()["tasks"] == expected["tasks"]
        assert persisted.json()["events"] == expected["events"]


def test_backend_failures_preserve_data_and_allow_subsequent_requests(
    tmp_path: Path,
) -> None:
    with running_backend(tmp_path) as client:
        created = client.post("/api/v1/tasks", json={"title": "Keep this task"})
        assert created.status_code == 201, created.text
        task = created.json()
        event = client.post(
            "/api/v1/events", json={"topic": "failure-drill", "message": "Keep history"}
        )
        assert event.status_code == 201, event.text
        exported = client.get("/api/v1/export")
        assert exported.status_code == 200, exported.text
        baseline = exported.json()

        unavailable = client.post(
            "/v1/chat/completions", json={"prompt": "Synthetic readiness prompt"}
        )
        assert unavailable.status_code == 503, unavailable.text
        assert unavailable.json() == {
            "detail": {
                "status": "OFFLINE_FALLBACK",
                "message": "Local model weights are missing; no inference was performed.",
            }
        }
        after_failure = client.get("/api/v1/export")
        assert after_failure.status_code == 200, after_failure.text
        assert after_failure.json()["tasks"] == baseline["tasks"]
        assert after_failure.json()["events"] == baseline["events"]

        invalid_requests = (
            ("POST", "/api/v1/tasks", {"title": ""}),
            ("PATCH", f"/api/v1/tasks/{task['id']}", {"priority": "invalid"}),
            ("POST", "/api/v1/events", {"topic": "failure-drill", "message": ""}),
            (
                "POST",
                "/api/v1/unified/dispatch",
                {
                    "protocol_version": "1.0.0",
                    "source_lang": "python",
                    "node": "ATLAS",
                    "event": "invalid-event",
                    "timestamp": 1.0,
                    "payload": {},
                },
            ),
            ("POST", "/api/v1/restore", {"backup": {"schema_version": 999}}),
        )
        for method, path, body in invalid_requests:
            rejected = client.request(method, path, json=body)
            assert rejected.status_code == 422, rejected.text
            assert rejected.json()["detail"]
            unchanged = client.get("/api/v1/export")
            assert unchanged.status_code == 200, unchanged.text
            assert unchanged.json()["tasks"] == baseline["tasks"], path
            assert unchanged.json()["events"] == baseline["events"], path

        accepted = client.post("/api/v1/tasks", json={"title": "Works after errors"})
        assert accepted.status_code == 201, accepted.text
        final = client.get("/api/v1/export")
        assert final.status_code == 200, final.text
        assert final.json()["tasks"] == [*baseline["tasks"], accepted.json()]
        assert final.json()["events"] == baseline["events"]
        assert client.get("/health").status_code == 200
