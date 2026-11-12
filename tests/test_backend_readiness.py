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
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", int(sys.argv[2])))
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
    directory: Path, *, abrupt_stop: bool = False, port: int = 0,
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
            [sys.executable, "-c", SERVER, str(port_file), str(port)],
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


def test_monitor_task_creation_restart_and_outage_recovery(tmp_path: Path) -> None:
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright, playwright.chromium.launch() as browser:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page_errors = []
        task_posts = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "request",
            lambda request: task_posts.append(request)
            if request.method == "POST" and request.url.endswith("/api/v1/tasks")
            else None,
        )
        with running_backend(tmp_path) as client:
            port = client.base_url.port
            assert port is not None
            page.goto(f"{client.base_url}/monitor")
            expect(page.locator("#task-connection")).to_contain_text("connected.")
            title = page.get_by_label("Task title (required)")
            title.fill("Browser-created persistent task")
            title.press("Enter")
            expect(page.locator("#task-notice")).to_contain_text("Saved task #")
            expect(page.locator("#task-list li")).to_have_count(1)
            saved = client.get("/api/v1/export")
            assert saved.status_code == 200, saved.text
            original = saved.json()["tasks"]
            assert len(original) == 1
            assert original[0]["title"] == "Browser-created persistent task"
            expect(page.locator("#task-list li")).to_have_attribute(
                "data-task-id", str(original[0]["id"])
            )
            assert len(task_posts) == 1
            title.fill("   ")
            page.get_by_role("button", name="Add task", exact=True).click()
            expect(page.get_by_role("alert")).to_contain_text("Task title")
            expect(title).to_have_value("   ")
            expect(page.locator("#task-list li")).to_have_count(1)
            assert len(task_posts) == 2

        page.get_by_role("button", name="Refresh tasks", exact=True).click()
        expect(page.locator("#task-connection")).to_contain_text("unavailable", timeout=10000)
        expect(page.locator("#task-list li")).to_have_count(1)
        title.fill("Draft retained during outage")
        page.get_by_role("button", name="Add task", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("Save not confirmed")
        expect(title).to_have_value("Draft retained during outage")
        expect(page.locator("#task-notice")).to_be_empty()
        expect(page.locator("#task-list li")).to_have_count(1)

        with running_backend(tmp_path, port=port) as client:
            expect(page.locator("#task-connection")).to_contain_text("connected.", timeout=15000)
            expect(page.locator("#task-list li")).to_have_count(1)
            recovered = client.get("/api/v1/export")
            assert recovered.status_code == 200, recovered.text
            assert recovered.json()["tasks"] == original
            assert len(task_posts) == 3, "Outage saves must not be retried automatically"
            expect(title).to_have_value("Draft retained during outage")
            page.get_by_role("button", name="Refresh tasks", exact=True).click()
            expect(page.locator("#task-connection")).to_contain_text("connected.")
            expect(page.locator("#task-list li")).to_have_count(1)
            page.get_by_role("button", name="Add task", exact=True).click()
            expect(page.locator("#task-notice")).to_contain_text("Saved task #")
            expect(page.get_by_role("alert")).to_be_empty()
            expect(title).to_have_value("")
            expect(page.locator("#task-list li")).to_have_count(2)
            final = client.get("/api/v1/export")
            assert final.status_code == 200, final.text
            assert final.json()["tasks"][:1] == original
            assert len(final.json()["tasks"]) == 2
            assert final.json()["tasks"][1]["title"] == "Draft retained during outage"
            assert len(task_posts) == 4
            page.reload()
            expect(page.locator("#task-list li")).to_have_count(2)
            assert not page_errors
        page.close()


def test_monitor_task_status_lifecycle_and_outage_recovery(tmp_path: Path) -> None:
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright, playwright.chromium.launch() as browser:
        page = browser.new_page()
        updates = []
        page.on(
            "request",
            lambda request: updates.append(request.url)
            if request.method == "POST"
            and request.url.endswith(("/complete", "/reopen")) else None,
        )
        with running_backend(tmp_path) as client:
            port = client.base_url.port
            assert port is not None
            page.goto(f"{client.base_url}/monitor")
            page.get_by_label("Task title (required)").fill("Lifecycle task")
            page.get_by_role("button", name="Add task", exact=True).click()
            expect(page.locator("#task-list li")).to_have_count(1)
            exported = client.get("/api/v1/export")
            assert exported.status_code == 200, exported.text
            original = exported.json()["tasks"][0]
            task_id = original["id"]
            row = page.locator(f'[data-task-id="{task_id}"]')
            complete = page.get_by_role("button", name=f"Complete task #{task_id}", exact=True)
            complete.focus()
            complete.press("Enter")
            expect(row).to_contain_text(" - done")
            expect(page.locator("#task-notice")).to_have_text(f"Task #{task_id} completed.")
            expect(page.get_by_role("button", name=f"Reopen task #{task_id}", exact=True)).to_be_focused()
            exported = client.get("/api/v1/export")
            assert exported.status_code == 200, exported.text
            completed = exported.json()["tasks"]
            assert len(completed) == 1
            assert completed[0] == {**original, "status": "done", "updated_at": completed[0]["updated_at"]}
            page.reload()
            expect(row).to_contain_text(" - done")

        with running_backend(tmp_path, port=port) as client:
            page.get_by_role("button", name="Refresh tasks", exact=True).click()
            expect(page.locator("#task-connection")).to_contain_text("connected.")
            expect(row).to_contain_text(" - done")
            exported = client.get("/api/v1/export")
            assert exported.status_code == 200, exported.text
            assert exported.json()["tasks"] == completed
            page.get_by_role("button", name=f"Reopen task #{task_id}", exact=True).click()
            expect(row).to_contain_text(" - pending")
            expect(page.locator("#task-notice")).to_have_text(f"Task #{task_id} reopened.")
            exported = client.get("/api/v1/export")
            assert exported.status_code == 200, exported.text
            reopened = exported.json()["tasks"]
            assert len(reopened) == 1
            assert reopened[0] == {**original, "updated_at": reopened[0]["updated_at"]}
            page.reload()
            expect(row).to_contain_text(" - pending")

        page.get_by_role("button", name=f"Complete task #{task_id}", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("Update not confirmed")
        expect(page.locator("#task-connection")).to_contain_text("unavailable", timeout=10000)
        expect(row).to_contain_text(" - pending")
        expect(page.locator("#task-list li")).to_have_count(1)
        expect(page.locator("#task-notice")).to_be_empty()
        assert len(updates) == 3

        with running_backend(tmp_path, port=port) as client:
            expect(page.locator("#task-connection")).to_contain_text("connected.", timeout=15000)
            expect(row).to_contain_text(" - pending")
            exported = client.get("/api/v1/export")
            assert exported.status_code == 200, exported.text
            assert exported.json()["tasks"] == reopened
            assert len(updates) == 3, "Failed updates must not be retried automatically"
            page.get_by_role("button", name=f"Complete task #{task_id}", exact=True).click()
            expect(row).to_contain_text(" - done")
            expect(page.get_by_role("alert")).to_be_empty()
            assert len(updates) == 4
            exported = client.get("/api/v1/export")
            assert exported.status_code == 200, exported.text
            final = exported.json()["tasks"]
            assert len(final) == 1
            assert final[0] == {**completed[0], "updated_at": final[0]["updated_at"]}

        with running_backend(tmp_path, port=port) as client:
            page.reload()
            expect(row).to_contain_text(" - done")
            page.get_by_role("button", name=f"Reopen task #{task_id}", exact=True).click()
            expect(row).to_contain_text(" - pending")
            exported = client.get("/api/v1/export")
            assert exported.status_code == 200, exported.text
            final = exported.json()["tasks"]
            assert len(final) == 1
            assert final[0] == {**original, "updated_at": final[0]["updated_at"]}
        with running_backend(tmp_path, port=port) as client:
            page.reload()
            expect(row).to_contain_text(" - pending")
            expect(page.locator("#task-list li")).to_have_count(1)
            exported = client.get("/api/v1/export")
            assert exported.status_code == 200, exported.text
            assert exported.json()["tasks"] == final
            # Commit the real update, but drop its response to simulate a lost
            # acknowledgement. The UI must reconcile, not repeat the write.
            def drop_acknowledgement(route):
                response = route.fetch()
                assert response.status == 200
                route.abort("connectionfailed")

            page.route(f"**/api/v1/tasks/{task_id}/complete", drop_acknowledgement, times=1)
            page.get_by_role("button", name=f"Complete task #{task_id}", exact=True).click()
            expect(page.get_by_role("alert")).to_contain_text("Update not confirmed")
            expect(row).to_contain_text(" - done")
            expect(page.locator("#task-notice")).to_be_empty()
            assert len(updates) == 6
            exported = client.get("/api/v1/export")
            assert exported.status_code == 200, exported.text
            reconciled = exported.json()["tasks"]
            assert len(reconciled) == 1
            assert reconciled[0] == {
                **completed[0], "updated_at": reconciled[0]["updated_at"]
            }
        page.close()


@pytest.mark.parametrize("field,original_value,first_value,second_value", [
    ("title", "Concurrent task", "First title", "Second title"),
    ("description", "", "First description", "Second description"),
    ("priority", "normal", "low", "high"),
    ("due_date", None, "2027-01-02", "2027-03-04"),
])
def test_concurrent_field_edits_have_one_winner(
    tmp_path: Path, field: str, original_value: str | None,
    first_value: str, second_value: str,
) -> None:
    with running_backend(tmp_path) as client:
        created = client.post("/api/v1/tasks", json={"title": "Concurrent task"})
        assert created.status_code == 201, created.text
        original = created.json()
        path = f"/api/v1/tasks/{original['id']}"
        baseline = client.get("/api/v1/export").json()
        barrier = Barrier(2)

        def edit(value: str) -> httpx.Response:
            with httpx.Client(base_url=str(client.base_url), trust_env=False) as independent:
                barrier.wait(timeout=10)
                return independent.patch(path, json={
                    field: value, "expected_values": {field: original_value},
                })

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(edit, (first_value, second_value)))
        assert sorted(result.status_code for result in results) == [200, 409]
        winner = next(result.json() for result in results if result.status_code == 200)
        loser = next(result.json()["detail"] for result in results if result.status_code == 409)
        assert loser == {
            "code": "task_edit_conflict",
            "message": f"Task fields changed since editing began: {field}",
            "fields": [field], "current": winner,
        }
        assert winner == {
            **original, field: winner[field], "updated_at": winner["updated_at"],
        }
        assert winner[field] in (first_value, second_value)
        assert client.get("/api/v1/tasks").json() == [winner]
        # A stale multi-field edit must reject the entire write.
        other = "description" if field != "description" else "title"
        rejected = client.patch(path, json={
            field: second_value, other: "Must not partially save",
            "expected_values": {field: original_value, other: original[other]},
        })
        assert rejected.status_code == 409, rejected.text
        assert client.get("/api/v1/tasks").json() == [winner]
        assert client.get("/api/v1/export").json()["events"] == baseline["events"]
        missing = client.patch("/api/v1/tasks/999999", json={
            field: first_value, "expected_values": {field: original_value},
        })
        assert missing.status_code == 404, missing.text
    with running_backend(tmp_path) as client:
        assert client.get("/api/v1/tasks").json() == [winner]
        # Explicit review of the winner permits a subsequent valid edit.
        reviewed = client.patch(path, json={
            field: original_value if original_value is not None else "2028-01-01",
            "expected_values": {field: winner[field]},
        })
        assert reviewed.status_code == 200, reviewed.text


def test_concurrent_unrelated_fields_merge_and_invalid_guards_fail(tmp_path: Path) -> None:
    with running_backend(tmp_path) as client:
        created = client.post("/api/v1/tasks", json={"title": "Unrelated task"})
        assert created.status_code == 201, created.text
        original = created.json()
        path = f"/api/v1/tasks/{original['id']}"
        barrier = Barrier(2)

        def edit(field: str) -> httpx.Response:
            with httpx.Client(base_url=str(client.base_url), trust_env=False) as independent:
                barrier.wait(timeout=10)
                return independent.patch(path, json={
                    field: f"Edited {field}", "expected_values": {field: original[field]},
                })

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(edit, ("title", "description")))
        assert [result.status_code for result in results] == [200, 200]
        merged = client.get("/api/v1/tasks").json()[0]
        assert merged == {
            **original, "title": "Edited title", "description": "Edited description",
            "updated_at": merged["updated_at"],
        }
        for expected, status in (
            ({}, 422),
            ({"priority": "normal"}, 422),
            ({"title": None}, 422),
            ({"title": 12}, 422),
            ({"title": merged["title"], "status": "pending"}, 422),
            ({"title": merged["title"], "description": merged["description"]}, 422),
        ):
            rejected = client.patch(path, json={
                "title": "Invalid guard must not write", "expected_values": expected,
            })
            assert rejected.status_code == status, rejected.text
            assert client.get("/api/v1/tasks").json() == [merged]
        # Legacy clients retain unguarded behavior.
        legacy = client.patch(path, json={"priority": "high"})
        assert legacy.status_code == 200, legacy.text
        dated = client.patch(path, json={
            "due_date": "2027-01-02", "expected_values": {"due_date": None},
        })
        assert dated.status_code == 200, dated.text
        rejected = client.patch(path, json={
            "clear_due_date": True, "expected_values": {"due_date": None},
        })
        assert rejected.status_code == 409, rejected.text
        assert client.get("/api/v1/tasks").json() == [dated.json()]
        cleared = client.patch(path, json={
            "clear_due_date": True, "expected_values": {"due_date": "2027-01-02"},
        })
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["due_date"] is None


def test_monitor_two_editors_conflict_review_and_recovery(tmp_path: Path) -> None:
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright, playwright.chromium.launch() as browser:
        first = browser.new_page()
        second = browser.new_page()
        writes = []
        second.on("request", lambda request: writes.append(request.post_data_json)
                  if request.method == "PATCH" else None)
        with running_backend(tmp_path) as client:
            port = client.base_url.port
            assert port is not None
            created = client.post("/api/v1/tasks", json={"title": "Shared original"})
            assert created.status_code == 201, created.text
            original = created.json()
            task_id = original["id"]
            path = f"/api/v1/tasks/{task_id}"
            for page in (first, second):
                page.goto(f"{client.base_url}/monitor")
                page.get_by_role("button", name=f"Edit task #{task_id}", exact=True).click()
            first.get_by_label("Edit title (required)", exact=True).fill("First editor wins")
            second.get_by_label("Edit title (required)", exact=True).fill("Second editor draft")
            second.get_by_label("Edit description", exact=True).fill("Independent local draft")
            second.get_by_label("Task title (required)", exact=True).fill("Creation retained")
            search = second.get_by_label("Search tasks", exact=True)
            search.fill("Shared original")
            search.press("Enter")
            first.get_by_role("button", name="Save changes", exact=True).click()
            expect(first.locator("#task-editor")).to_be_hidden()
            winner = client.get("/api/v1/tasks").json()[0]
            assert winner["title"] == "First editor wins"
            second.get_by_role("button", name="Save changes", exact=True).click()
            expect(second.get_by_role("alert")).to_contain_text("Edit conflict:")
            expect(second.get_by_role("alert")).to_contain_text("Nothing from this edit was saved")
            expect(second.locator("#task-edit-conflict")).to_be_visible()
            expect(second.locator("#task-conflict-values")).to_contain_text("First editor wins")
            expect(second.get_by_label("Edit title (required)", exact=True)).to_have_value("Second editor draft")
            expect(second.get_by_label("Edit description", exact=True)).to_have_value("Independent local draft")
            expect(second.locator("#task-empty")).to_be_visible()
            assert client.get("/api/v1/tasks").json() == [winner]
            assert len(writes) == 1
            # Repeated Save without explicit review remains a conflict.
            second.get_by_role("button", name="Save changes", exact=True).click()
            expect(second.get_by_role("alert")).to_contain_text("Edit conflict:")
            assert len(writes) == 2
            assert client.get("/api/v1/tasks").json() == [winner]
        expect(second.locator("#task-connection")).to_contain_text("unavailable", timeout=15000)
        expect(second.locator("#task-edit-conflict")).to_be_visible()
        with running_backend(tmp_path, port=port) as client:
            expect(second.locator("#task-connection")).to_contain_text("connected.", timeout=15000)
            assert len(writes) == 2, "Restart/reconnect must not retry a conflict"
            expect(second.get_by_label("Task title (required)", exact=True)).to_have_value("Creation retained")
            expect(search).to_have_value("Shared original")
            review = second.get_by_role("button", name="Keep draft against reviewed values", exact=True)
            review.click()
            expect(second.get_by_label("Edit title (required)", exact=True)).to_be_focused()
            expect(second.locator("#task-edit-conflict")).to_be_hidden()
            assert len(writes) == 2, "Review must not write"
            # A change after review must still be rejected atomically.
            external = client.patch(path, json={"title": "Changed after review", "priority": "high"})
            assert external.status_code == 200, external.text
            second.get_by_role("button", name="Save changes", exact=True).click()
            expect(second.get_by_role("alert")).to_contain_text("Edit conflict:")
            expect(second.locator("#task-conflict-values")).to_contain_text("Changed after review")
            assert client.get("/api/v1/tasks").json() == [external.json()]
            review.click()
            expect(second.get_by_role("radio", name="High", exact=True)).to_be_checked()
            expect(second.get_by_label("Edit title (required)", exact=True)).to_have_value("Second editor draft")
            second.get_by_role("button", name="Save changes", exact=True).click()
            expect(second.locator("#task-editor")).to_be_hidden()
            expect(second.get_by_role("alert")).to_be_empty()
            expect(second.get_by_role("button", name="Refresh tasks", exact=True)).to_be_focused()
            assert len(writes) == 4
            assert writes[-1] == {
                "title": "Second editor draft", "description": "Independent local draft",
                "expected_values": {"title": "Changed after review", "description": ""},
            }
            final = client.get("/api/v1/tasks").json()[0]
            assert final == {
                **original, "title": "Second editor draft", "description": "Independent local draft",
                "priority": "high", "updated_at": final["updated_at"],
            }
        with running_backend(tmp_path, port=port) as client:
            second.reload()
            expect(second.locator("#task-list")).to_contain_text("Second editor draft")
            assert client.get("/api/v1/tasks").json() == [final]
            assert len(writes) == 4
        first.close()
        second.close()


def test_monitor_task_details_editing_and_restart(tmp_path: Path) -> None:
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright, playwright.chromium.launch() as browser:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        patches = []
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda request: patches.append(request.post_data_json)
            if request.method == "PATCH" else None,
        )
        with running_backend(tmp_path) as client:
            port = client.base_url.port
            assert port is not None
            response = client.post("/api/v1/tasks", json={
                "title": "Editable task", "description": "Original description",
                "priority": "low", "due_date": "2027-01-02",
            })
            assert response.status_code == 201, response.text
            task_id = response.json()["id"]
            response = client.post(f"/api/v1/tasks/{task_id}/complete")
            assert response.status_code == 200, response.text
            original = response.json()
            page.goto(f"{client.base_url}/monitor")
            row = page.locator(f'[data-task-id="{task_id}"]')
            expect(row).to_contain_text("Original description")
            expect(row).to_contain_text("Priority: low. Due date: 2027-01-02.")
            creation = page.get_by_label("Task title (required)", exact=True)
            creation.fill("Independent creation draft")
            editor = page.locator("#task-editor")
            title = page.get_by_label("Edit title (required)", exact=True)
            description = page.get_by_label("Edit description", exact=True)
            due = page.get_by_label("Edit due date (optional)", exact=True)
            edit = page.get_by_role("button", name=f"Edit task #{task_id}", exact=True)
            edit.focus()
            edit.press("Enter")
            expect(title).to_be_focused()
            expect(title).to_have_value(original["title"])
            expect(description).to_have_value(original["description"])
            expect(due).to_have_value(original["due_date"])
            page.get_by_role("button", name="Save changes", exact=True).click()
            expect(page.locator("#task-notice")).to_have_text("No changes to save.")
            assert patches == []
            title.fill("Discarded edit")
            page.get_by_role("button", name="Cancel editing", exact=True).click()
            expect(editor).to_be_hidden()
            expect(edit).to_be_focused()
            assert patches == []
            edit.click()
            expect(title).to_have_value("Editable task")
            title.fill("")
            page.get_by_role("button", name="Save changes", exact=True).click()
            expect(title).to_be_focused()
            assert patches == [], "Native required validation must prevent submission"
            title.fill("   ")
            page.get_by_role("button", name="Save changes", exact=True).click()
            expect(page.get_by_role("alert")).to_contain_text("Edit not confirmed")
            expect(title).to_have_value("   ")
            expect(row).to_contain_text("Editable task - done")
            assert client.get("/api/v1/tasks").json() == [original]
            title.fill("Edited task")
            description.fill("Edited description\nSecond line")
            page.get_by_role("radio", name="High", exact=True).check()
            due.fill("2027-03-04")
            with page.expect_response(
                lambda response: response.url.endswith("/api/v1/tasks")
                and response.request.method == "GET"
            ):
                page.get_by_role("button", name="Refresh tasks", exact=True).click()
            expect(title).to_have_value("Edited task")
            expect(description).to_have_value("Edited description\nSecond line")
            expect(creation).to_have_value("Independent creation draft")
            held = []

            def hold_acknowledgement(route):
                result = route.fetch()
                assert result.status == 200
                held.append((route, result))

            page.route(f"**/api/v1/tasks/{task_id}", hold_acknowledgement, times=1)
            page.get_by_role("button", name="Save changes", exact=True).click()
            expect(page.locator("#task-edit-save")).to_be_disabled()
            expect(page.get_by_role("button", name="Cancel editing", exact=True)).to_be_disabled()
            expect(page.get_by_role("button", name="Add task", exact=True)).to_be_disabled()
            expect(page.get_by_role("button", name="Apply filters", exact=True)).to_be_disabled()
            expect(page.get_by_role("button", name=f"Reopen task #{task_id}", exact=True)).to_be_disabled()
            expect(row).to_contain_text("Editable task - done")
            expect(row).to_contain_text("Original description")
            editor.evaluate("(form) => form.requestSubmit()")
            assert len(patches) == 2, "A pending edit must block duplicate submissions"
            assert len(held) == 1
            held[0][0].fulfill(response=held[0][1])
            expect(editor).to_be_hidden()
            expect(row).to_contain_text("Edited task - done")
            expect(row).to_contain_text("Edited description\nSecond line")
            expect(row).to_contain_text("Priority: high. Due date: 2027-03-04.")
            expect(edit).to_be_focused()
            expect(page.get_by_role("alert")).to_be_empty()
            assert patches[-1] == {
                "title": "Edited task", "description": "Edited description\nSecond line",
                "priority": "high", "due_date": "2027-03-04",
                "expected_values": {
                    key: original[key] for key in ("title", "description", "priority", "due_date")
                },
            }
            updated = client.get("/api/v1/tasks").json()[0]
            assert updated == {
                **original,
                **{key: value for key, value in patches[-1].items() if key != "expected_values"},
                "updated_at": updated["updated_at"],
            }
            expect(creation).to_have_value("Independent creation draft")
            page.reload()
            expect(row).to_contain_text("Priority: high. Due date: 2027-03-04.")

        with running_backend(tmp_path, port=port) as client:
            page.get_by_role("button", name="Refresh tasks", exact=True).click()
            expect(page.locator("#task-connection")).to_contain_text("connected.")
            assert client.get("/api/v1/tasks").json() == [updated]
            edit.click()
            description.fill("")
            due.fill("")
            # A different client's change to an untouched field must survive.
            external = client.patch(f"/api/v1/tasks/{task_id}", json={"priority": "normal"})
            assert external.status_code == 200, external.text
            page.get_by_role("button", name="Save changes", exact=True).click()
            expect(editor).to_be_hidden()
            expect(row).to_contain_text("No description.")
            expect(row).to_contain_text("Priority: normal. Due date: None.")
            assert patches[-1] == {
                "description": "", "clear_due_date": True,
                "expected_values": {
                    "description": updated["description"], "due_date": updated["due_date"],
                },
            }
            cleared = client.get("/api/v1/tasks").json()[0]
            assert cleared == {
                **updated, "description": "", "due_date": None, "priority": "normal",
                "updated_at": cleared["updated_at"],
            }
            # An edit can remove the task from the active search without losing focus.
            search = page.get_by_label("Search tasks", exact=True)
            search.fill("Edited task")
            search.press("Enter")
            expect(row).to_be_visible()
            edit.click()
            title.fill("Renamed outside search")
            page.get_by_role("button", name="Save changes", exact=True).click()
            expect(editor).to_be_hidden()
            expect(row).to_have_count(0)
            expect(page.locator("#task-empty")).to_be_visible()
            expect(page.get_by_role("button", name="Refresh tasks", exact=True)).to_be_focused()
            expect(search).to_have_value("Edited task")
            final = client.get("/api/v1/tasks").json()[0]
            assert final == {
                **cleared, "title": "Renamed outside search", "updated_at": final["updated_at"],
            }
        with running_backend(tmp_path, port=port) as client:
            page.reload()
            expect(row).to_contain_text("Renamed outside search - done")
            expect(row).to_contain_text("Priority: normal. Due date: None.")
            assert client.get("/api/v1/tasks").json() == [final]
            assert len(patches) == 4
            assert errors == []
        page.close()


def test_monitor_edit_draft_outage_and_lost_acknowledgement(tmp_path: Path) -> None:
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright, playwright.chromium.launch() as browser:
        page = browser.new_page()
        patches = []
        page.on(
            "request", lambda request: patches.append(request.post_data_json)
            if request.method == "PATCH" else None,
        )
        with running_backend(tmp_path) as client:
            port = client.base_url.port
            assert port is not None
            response = client.post("/api/v1/tasks", json={"title": "Outage edit task"})
            assert response.status_code == 201, response.text
            original = response.json()
            task_id = original["id"]
            page.goto(f"{client.base_url}/monitor")
            row = page.locator(f'[data-task-id="{task_id}"]')
            page.get_by_role("button", name=f"Edit task #{task_id}", exact=True).click()
            title = page.get_by_label("Edit title (required)", exact=True)
            title.fill("Retained edit draft")
            creation = page.get_by_label("Task title (required)", exact=True)
            creation.fill("Retained creation draft")
            search = page.get_by_label("Search tasks", exact=True)
            search.fill("edit")
            search.press("Enter")
            expect(row).to_be_visible()
        page.get_by_role("button", name="Save changes", exact=True).click()
        expect(page.get_by_role("alert")).to_contain_text("Edit not confirmed")
        expect(page.locator("#task-connection")).to_contain_text("unavailable", timeout=10000)
        expect(row).to_contain_text("Outage edit task - pending")
        expect(title).to_have_value("Retained edit draft")
        expect(creation).to_have_value("Retained creation draft")
        expect(search).to_have_value("edit")
        assert len(patches) == 1
        with running_backend(tmp_path, port=port) as client:
            expect(page.locator("#task-connection")).to_contain_text("connected.", timeout=15000)
            expect(title).to_have_value("Retained edit draft")
            expect(creation).to_have_value("Retained creation draft")
            assert client.get("/api/v1/tasks").json() == [original]
            assert len(patches) == 1, "Reconnection must not retry edits"
            page.get_by_role("button", name="Save changes", exact=True).click()
            expect(page.locator("#task-editor")).to_be_hidden()
            expect(row).to_contain_text("Retained edit draft - pending")
            expect(page.get_by_role("alert")).to_be_empty()
            assert len(patches) == 2
            page.get_by_role("button", name=f"Edit task #{task_id}", exact=True).click()
            description = page.get_by_label("Edit description", exact=True)
            description.fill("Saved despite missing acknowledgement")

            def drop_acknowledgement(route):
                result = route.fetch()
                assert result.status == 200
                route.abort("connectionfailed")

            page.route(f"**/api/v1/tasks/{task_id}", drop_acknowledgement, times=1)
            page.get_by_role("button", name="Save changes", exact=True).click()
            expect(page.get_by_role("alert")).to_contain_text("Edit not confirmed")
            expect(row).to_contain_text("Saved despite missing acknowledgement")
            expect(description).to_have_value("Saved despite missing acknowledgement")
            expect(page.locator("#task-editor")).to_be_visible()
            expect(creation).to_have_value("Retained creation draft")
            assert len(patches) == 3
            saved = client.get("/api/v1/tasks").json()[0]
            assert saved == {
                **original, "title": "Retained edit draft",
                "description": "Saved despite missing acknowledgement",
                "updated_at": saved["updated_at"],
            }
        expect(page.locator("#task-connection")).to_contain_text("unavailable", timeout=10000)
        with running_backend(tmp_path, port=port) as client:
            expect(page.locator("#task-connection")).to_contain_text("connected.", timeout=15000)
            expect(description).to_have_value("Saved despite missing acknowledgement")
            assert len(patches) == 3
            assert client.get("/api/v1/tasks").json() == [saved]
            # Retrying a committed but unacknowledged edit must not overwrite
            # newer values or change its timestamp.
            page.get_by_role("button", name="Save changes", exact=True).click()
            expect(page.get_by_role("alert")).to_contain_text("Edit conflict:")
            assert len(patches) == 4
            assert client.get("/api/v1/tasks").json() == [saved]
            page.get_by_role("button", name="Keep draft against reviewed values", exact=True).click()
            page.get_by_role("button", name="Save changes", exact=True).click()
            expect(page.locator("#task-notice")).to_have_text("No changes to save.")
            assert len(patches) == 4
            page.get_by_role("button", name="Cancel editing", exact=True).click()
            page.reload()
            expect(row).to_contain_text(saved["description"])
            expect(page.locator("#task-editor")).to_be_hidden()
        page.close()


def test_monitor_filters_search_drafts_and_outage_recovery(tmp_path: Path) -> None:
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright, playwright.chromium.launch() as browser:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        with running_backend(tmp_path) as client:
            port = client.base_url.port
            assert port is not None
            saved = []
            for title, description in (
                ("Alpha pending", ""),
                ("Alpha finished", ""),
                ("Beta pending", "Description needle"),
                ("Literal %_ marker", ""),
            ):
                created = client.post(
                    "/api/v1/tasks", json={"title": title, "description": description}
                )
                assert created.status_code == 201, created.text
                saved.append(created.json())
            completed = client.post(f"/api/v1/tasks/{saved[1]['id']}/complete")
            assert completed.status_code == 200, completed.text
            baseline = client.get("/api/v1/export")
            assert baseline.status_code == 200, baseline.text
            page.goto(f"{client.base_url}/monitor")
            rows = page.locator("#task-list li")
            expect(rows).to_have_count(4)
            draft = page.get_by_label("Task title (required)")
            draft.fill("Unsaved creation draft")
            search = page.get_by_label("Search tasks", exact=True)
            apply = page.get_by_role("button", name="Apply filters", exact=True)

            def choose(status: str, term: str, expected_ids: list[int]) -> None:
                page.get_by_role("radio", name=status, exact=True).check()
                search.fill(term)
                search.press("Enter")
                expect(rows).to_have_count(len(expected_ids))
                expect(page.locator("#task-connection")).to_contain_text("connected.")
                assert rows.evaluate_all(
                    "(items) => items.map(item => Number(item.dataset.taskId))"
                ) == expected_ids
                expect(draft).to_have_value("Unsaved creation draft")

            choose("Pending", "", [saved[3]["id"], saved[2]["id"], saved[0]["id"]])
            choose("Done", "", [saved[1]["id"]])
            choose("All", "Alpha", [saved[1]["id"], saved[0]["id"]])
            choose("Pending", "Alpha", [saved[0]["id"]])
            page.get_by_role(
                "button", name=f"Complete task #{saved[0]['id']}", exact=True
            ).click()
            expect(rows).to_have_count(0)
            expect(page.locator("#task-empty")).to_be_visible()
            expect(page.get_by_role("button", name="Refresh tasks", exact=True)).to_be_focused()
            choose("Done", "Alpha", [saved[1]["id"], saved[0]["id"]])
            page.get_by_role(
                "button", name=f"Reopen task #{saved[0]['id']}", exact=True
            ).click()
            expect(rows).to_have_count(1)
            expect(rows).to_have_attribute("data-task-id", str(saved[1]["id"]))
            choose("All", "Description needle", [saved[2]["id"]])
            choose("All", "%_", [saved[3]["id"]])
            choose("All", "no matching task", [])
            expect(page.locator("#task-empty")).to_be_visible()
            choose("All", "   ", [task["id"] for task in reversed(saved)])
            expect(page.locator("#task-empty")).to_be_hidden()
            choose("Done", "Alpha", [saved[1]["id"]])
            page.get_by_role("button", name="Refresh tasks", exact=True).click()
            expect(page.locator("#task-connection")).to_contain_text("connected.")
            expect(rows).to_have_count(1)
            expect(search).to_have_value("Alpha")
            expect(page.get_by_role("radio", name="Done", exact=True)).to_be_checked()
            expect(draft).to_have_value("Unsaved creation draft")
            before_outage = client.get("/api/v1/export")
            assert before_outage.status_code == 200, before_outage.text
            for original, actual in zip(
                baseline.json()["tasks"], before_outage.json()["tasks"], strict=True
            ):
                if original["id"] == saved[0]["id"]:
                    assert actual == {**original, "updated_at": actual["updated_at"]}
                else:
                    assert actual == original
            assert before_outage.json()["events"] == baseline.json()["events"]

        page.get_by_role("radio", name="Pending", exact=True).check()
        search.fill("Beta")
        apply.click()
        expect(page.locator("#task-connection")).to_contain_text("unavailable", timeout=10000)
        expect(page.locator("#task-connection")).to_contain_text("previous view")
        expect(rows).to_have_count(1)
        expect(rows).to_have_attribute("data-task-id", str(saved[1]["id"]))
        expect(page.locator("#task-empty")).to_be_hidden()
        expect(draft).to_have_value("Unsaved creation draft")
        expect(search).to_have_value("Beta")
        expect(page.get_by_role("radio", name="Pending", exact=True)).to_be_checked()

        with running_backend(tmp_path, port=port) as client:
            expect(page.locator("#task-connection")).to_contain_text("connected.", timeout=15000)
            expect(rows).to_have_count(1)
            expect(rows).to_have_attribute("data-task-id", str(saved[2]["id"]))
            expect(search).to_have_value("Beta")
            expect(page.get_by_role("radio", name="Pending", exact=True)).to_be_checked()
            expect(draft).to_have_value("Unsaved creation draft")
            # An unapplied search draft must not change the active view on polling.
            search.fill("Not applied yet")
            with page.expect_response(
                lambda response: response.url.endswith("?status=pending&search=Beta")
            ):
                page.get_by_role("button", name="Refresh tasks", exact=True).click()
            expect(page.locator("#task-connection")).to_contain_text('matching "Beta"')
            expect(rows).to_have_attribute("data-task-id", str(saved[2]["id"]))
            expect(search).to_have_value("Not applied yet")
            final = client.get("/api/v1/export")
            assert final.status_code == 200, final.text
            assert final.json()["tasks"] == before_outage.json()["tasks"]
            assert final.json()["events"] == before_outage.json()["events"]
            choose("Pending", "Absent task", [])
            expect(page.locator("#task-empty")).to_be_visible()
        expect(page.locator("#task-connection")).to_contain_text("unavailable", timeout=15000)
        expect(page.locator("#task-empty")).to_be_hidden()
        expect(draft).to_have_value("Unsaved creation draft")
        with running_backend(tmp_path, port=port) as client:
            expect(page.locator("#task-connection")).to_contain_text("connected.", timeout=15000)
            expect(page.locator("#task-empty")).to_be_visible()
            expect(rows).to_have_count(0)
            expect(search).to_have_value("Absent task")
            expect(page.get_by_role("radio", name="Pending", exact=True)).to_be_checked()
            expect(draft).to_have_value("Unsaved creation draft")
            # Saving resets only the creation form, not the applied view.
            page.get_by_role("button", name="Add task", exact=True).click()
            expect(page.locator("#task-notice")).to_contain_text("Saved task #")
            expect(draft).to_have_value("")
            expect(page.locator("#task-empty")).to_be_visible()
            expect(rows).to_have_count(0)
            expect(search).to_have_value("Absent task")
            expect(page.get_by_role("radio", name="Pending", exact=True)).to_be_checked()
            exported = client.get("/api/v1/export")
            assert exported.status_code == 200, exported.text
            assert len(exported.json()["tasks"]) == 5
            assert [
                task["title"] for task in exported.json()["tasks"]
                if task["id"] not in {original["id"] for original in saved}
            ] == ["Unsaved creation draft"]
        page.close()


def test_monitor_filter_change_ignores_outdated_response(tmp_path: Path) -> None:
    from playwright.sync_api import expect, sync_playwright

    with running_backend(tmp_path) as client:
        created = client.post("/api/v1/tasks", json={"title": "Alpha pending"})
        assert created.status_code == 201, created.text
        completed = client.post("/api/v1/tasks", json={"title": "Alpha done"})
        assert completed.status_code == 201, completed.text
        done = client.post(f"/api/v1/tasks/{completed.json()['id']}/complete")
        assert done.status_code == 200, done.text
        with sync_playwright() as playwright, playwright.chromium.launch() as browser:
            page = browser.new_page()
            page.goto(f"{client.base_url}/monitor")
            expect(page.locator("#task-list li")).to_have_count(2)
            held = []
            page.route("**/api/v1/tasks?search=Alpha", lambda route: held.append(route), times=1)
            search = page.get_by_label("Search tasks", exact=True)
            search.fill("Alpha")
            search.press("Enter")
            expect(page.get_by_role("button", name="Refresh tasks", exact=True)).to_be_disabled()
            page.get_by_role("radio", name="Done", exact=True).check()
            page.get_by_role("button", name="Apply filters", exact=True).click()
            page.evaluate("""() => {
                window.renderedCounts = [];
                const list = document.getElementById('task-list');
                new MutationObserver(() => window.renderedCounts.push(list.children.length))
                    .observe(list, { childList: true });
            }""")
            assert len(held) == 1
            held[0].fulfill(response=held[0].fetch())
            expect(page.locator("#task-list li")).to_have_count(1)
            expect(page.locator("#task-list li")).to_have_attribute(
                "data-task-id", str(completed.json()["id"])
            )
            expect(page.locator("#task-connection")).to_contain_text('done tasks matching "Alpha"')
            expect(page.locator("#task-empty")).to_be_hidden()
            assert page.evaluate("window.renderedCounts") == [1]
            page.close()


def test_dispatch_rate_limit_preserves_data_and_recovers(tmp_path: Path) -> None:
    envelope = {
        "protocol_version": "1.0.0",
        "source_lang": "python",
        "node": "ATLAS",
        "event": "RATE_RECOVERY_TEST",
        "timestamp": 1.0,
        "payload": {},
    }
    with running_backend(tmp_path) as client:
        accepted = {}
        started = time.monotonic()
        for sequence in range(120):
            sent_envelope = {**envelope, "payload": {"sequence": sequence}}
            sent = client.post("/api/v1/unified/dispatch", json=sent_envelope)
            assert sent.status_code == 200, sent.text
            assert sent.json()["status"] == "ACCEPTED"
            assert sent.json()["persisted"] is True
            accepted[sent.json()["event_id"]] = sent_envelope
        assert len(accepted) == 120
        assert time.monotonic() - started < 60, "Burst exceeded the real rate window"
        exported = client.get("/api/v1/export")
        assert exported.status_code == 200, exported.text
        baseline = exported.json()
        assert baseline["tasks"] == []
        assert len(baseline["events"]) == 120
        assert len({event["id"] for event in baseline["events"]}) == 120
        for event in baseline["events"]:
            assert event["topic"] == "unified-dispatch"
            assert json.loads(event["message"]) == accepted[event["id"]]

        rejected_envelope = {**envelope, "payload": {"sequence": "rejected"}}
        rejected = client.post("/api/v1/unified/dispatch", json=rejected_envelope)
        assert rejected.status_code == 429, rejected.text
        assert rejected.json() == {"detail": "Unified dispatch rate limit exceeded."}
        retry_after = int(rejected.headers["Retry-After"])
        assert 1 <= retry_after <= 60
        retry_at = time.monotonic() + retry_after
        state = client.get("/api/v1/unified/state")
        assert state.status_code == 200, state.text
        latest = state.json()["last_dispatch"]
        assert latest["event_id"] == baseline["events"][-1]["id"]
        assert latest["envelope"] == accepted[latest["event_id"]]

        created = client.post(
            "/api/v1/tasks", json={"title": "Task writes work during dispatch throttling"}
        )
        assert created.status_code == 201, created.text
        tasks = client.get("/api/v1/tasks")
        assert tasks.status_code == 200, tasks.text
        assert tasks.json() == [created.json()]
        unchanged = client.get("/api/v1/export")
        assert unchanged.status_code == 200, unchanged.text
        assert unchanged.json()["tasks"] == [created.json()]
        assert unchanged.json()["events"] == baseline["events"]

        # Honor the actual Retry-After, without changing production limits,
        # mocking the clock, or restarting away the in-memory rate history.
        time.sleep(max(0, retry_at - time.monotonic()))
        recovered_envelope = {**envelope, "payload": {"sequence": "recovered"}}
        with client.stream(
            "GET",
            "/api/v1/unified/stream",
            headers={"Last-Event-ID": str(latest["event_id"])},
        ) as response:
            recovered = client.post("/api/v1/unified/dispatch", json=recovered_envelope)
            assert recovered.status_code == 200, recovered.text
            assert recovered.json()["status"] == "ACCEPTED"
            assert recovered.json()["persisted"] is True
            assert recovered.json()["live_subscribers_notified"] >= 1
            received = next(stream_events(response))
            assert received["event"] == "dispatch"
            assert int(received["id"]) == recovered.json()["event_id"]
            record = json.loads(received["data"])
            assert record["event_id"] > latest["event_id"]
            assert record["envelope"] == recovered_envelope
        assert read_dispatch(client, latest["event_id"]) == record
        final = client.get("/api/v1/export")
        assert final.status_code == 200, final.text
        assert final.json()["tasks"] == [created.json()]
        assert final.json()["events"] == [
            *baseline["events"],
            {
                "id": record["event_id"],
                "topic": "unified-dispatch",
                "message": json.dumps(
                    recovered_envelope, ensure_ascii=False, separators=(",", ":")
                ),
                "created_at": record["created_at"],
            },
        ]
        state = client.get("/api/v1/unified/state")
        assert state.status_code == 200, state.text
        assert state.json()["last_dispatch"] == record


@pytest.mark.parametrize("cursor", ["expired", "future"])
def test_stream_cursor_errors_reset_and_reconnect(tmp_path: Path, cursor: str) -> None:
    timestamp = "2026-11-12T00:00:00+00:00"
    envelope = {
        "protocol_version": "1.0.0",
        "source_lang": "python",
        "node": "HISTORIAN",
        "event": "CURSOR_RECOVERY_TEST",
        "timestamp": 1.0,
        "payload": {},
    }
    # Restore history beyond the production 500-event replay window without
    # weakening the dispatch rate limit or waiting for multiple rate windows.
    history = [
        {
            "id": sequence,
            "topic": "unified-dispatch",
            "message": json.dumps({**envelope, "payload": {"sequence": sequence}}),
            "created_at": timestamp,
        }
        for sequence in range(1, 502)
    ]
    latest = {
        "event_id": 501,
        "created_at": timestamp,
        "envelope": {**envelope, "payload": {"sequence": 501}},
    }
    with running_backend(tmp_path) as client:
        restored = client.post(
            "/api/v1/restore",
            json={
                "backup": {
                    "schema_version": 1,
                    "exported_at": timestamp,
                    "tasks": [],
                    "events": history,
                }
            },
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["events_restored"] == 501
        for invalid, detail in (
            ("not-an-integer", "Last-Event-ID must be an integer."),
            ("-1", "Last-Event-ID must be non-negative."),
        ):
            rejected = client.get(
                "/api/v1/unified/stream", headers={"Last-Event-ID": invalid}
            )
            assert rejected.status_code == 400, rejected.text
            assert rejected.json() == {"detail": detail}
        with client.stream(
            "GET",
            "/api/v1/unified/stream",
            headers={"Last-Event-ID": "0" if cursor == "expired" else "502"},
        ) as response:
            reset = next(stream_events(response))
            assert reset["event"] == "reset"
            assert int(reset["id"]) == latest["event_id"]
            assert json.loads(reset["data"]) == latest
        unchanged = client.get("/api/v1/export")
        assert unchanged.status_code == 200, unchanged.text
        assert unchanged.json()["tasks"] == []
        assert unchanged.json()["events"] == history
        state = client.get("/api/v1/unified/state")
        assert state.status_code == 200, state.text
        assert state.json()["last_dispatch"] == latest

        received_records = []
        with client.stream(
            "GET", "/api/v1/unified/stream", headers={"Last-Event-ID": reset["id"]}
        ) as response:
            events = stream_events(response)
            for sequence in (502, 503):
                sent_envelope = {**envelope, "payload": {"sequence": sequence}}
                sent = client.post("/api/v1/unified/dispatch", json=sent_envelope)
                assert sent.status_code == 200, sent.text
                assert sent.json()["persisted"] is True
                assert sent.json()["live_subscribers_notified"] >= 1
                received = next(events)
                assert received["event"] == "dispatch"
                assert int(received["id"]) == sent.json()["event_id"] == sequence
                record = json.loads(received["data"])
                assert record["event_id"] == sequence
                assert record["envelope"] == sent_envelope
                received_records.append(record)

        with client.stream(
            "GET", "/api/v1/unified/stream", headers={"Last-Event-ID": reset["id"]}
        ) as response:
            events = stream_events(response)
            for record in received_records:
                replayed = next(events)
                assert replayed["event"] == "dispatch"
                assert int(replayed["id"]) == record["event_id"]
                assert json.loads(replayed["data"]) == record
            sent_envelope = {**envelope, "payload": {"sequence": 504}}
            sent = client.post("/api/v1/unified/dispatch", json=sent_envelope)
            assert sent.status_code == 200, sent.text
            assert sent.json()["persisted"] is True
            received = next(events)
            assert received["event"] == "dispatch"
            assert int(received["id"]) == sent.json()["event_id"] == 504
            record = json.loads(received["data"])
            assert record["event_id"] == 504
            assert record["envelope"] == sent_envelope
            received_records.append(record)

        final = client.get("/api/v1/export")
        assert final.status_code == 200, final.text
        assert final.json()["tasks"] == []
        assert final.json()["events"][:501] == history
        assert final.json()["events"][501:] == [
            {
                "id": record["event_id"],
                "topic": "unified-dispatch",
                "message": json.dumps(
                    record["envelope"], ensure_ascii=False, separators=(",", ":")
                ),
                "created_at": record["created_at"],
            }
            for record in received_records
        ]
        state = client.get("/api/v1/unified/state")
        assert state.status_code == 200, state.text
        assert state.json()["last_dispatch"] == received_records[-1]


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
