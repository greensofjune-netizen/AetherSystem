import io
import json
import plistlib
import shlex
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from aether_engine.database import AetherStore
from aether_engine.galileo import ConversationStore
from automator import bridge, install


def test_backup_both_databases_and_restore_snapshots(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    aether = AetherStore(project / ".aether-engine.sqlite3")
    aether.add_task("Back up this task")
    galileo_dir = tmp_path / "Galileo"
    galileo = ConversationStore(galileo_dir)
    conversation = galileo.create("Test")
    galileo.save_exchange(conversation["id"], "Hello", "Hi", "Test")

    aether_backup, galileo_backup = bridge.backup_databases(project, galileo_dir)
    payload = json.loads(aether_backup.read_text(encoding="utf-8"))
    assert payload["tasks"][0]["title"] == "Back up this task"
    with sqlite3.connect(galileo_backup) as database:
        assert database.execute(
            "SELECT content FROM messages ORDER BY id"
        ).fetchall() == [("Hello",), ("Hi",)]
        assert database.execute("PRAGMA quick_check").fetchone() == ("ok",)
    assert aether_backup.stat().st_mode & 0o777 == 0o600
    assert galileo_backup.stat().st_mode & 0o777 == 0o600
    assert galileo_backup.parent.stat().st_mode & 0o777 == 0o700


def test_backup_missing_or_invalid_source_does_not_create_empty_backup(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    galileo = tmp_path / "galileo"
    galileo.mkdir()
    with pytest.raises(FileNotFoundError):
        bridge.backup_databases(project, galileo)
    assert not (project / ".aether-engine.sqlite3").exists()
    with sqlite3.connect(project / ".aether-engine.sqlite3"):
        pass
    ConversationStore(galileo)
    with pytest.raises(ValueError, match="Aether database"):
        bridge.backup_databases(project, galileo)
    assert not list((galileo / "Backups").glob("galileo-backup-*"))


def test_backup_rejects_symlinked_source(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    database = tmp_path / "other.sqlite3"
    AetherStore(database)
    (project / ".aether-engine.sqlite3").symlink_to(database)
    galileo = tmp_path / "galileo"
    ConversationStore(galileo)
    with pytest.raises(FileNotFoundError, match="symlink"):
        bridge.backup_databases(project, galileo)


def test_backup_reports_aether_failure_without_leaving_galileo_snapshot(
    tmp_path, monkeypatch
):
    project = tmp_path / "project"
    project.mkdir()
    AetherStore(project / ".aether-engine.sqlite3")
    galileo = tmp_path / "galileo"
    ConversationStore(galileo)

    def fail(*args, **kwargs):
        raise OSError("Backup storage unavailable")

    monkeypatch.setattr(bridge, "write_backup", fail)
    with pytest.raises(OSError, match="Backup storage unavailable"):
        bridge.backup_databases(project, galileo)
    assert not list((galileo / "Backups").glob("galileo-backup-*"))


def test_prompt_selected_input_requires_confirmation(monkeypatch):
    monkeypatch.setattr(bridge.sys, "stdin", io.TextIOWrapper(io.BytesIO(b"chosen text")))
    dialogs = []
    monkeypatch.setattr(
        bridge, "dialog",
        lambda text, **kwargs: dialogs.append((text, kwargs)) or "Continue",
    )
    assert bridge.read_prompt() == "chosen text"
    assert dialogs[0][1] == {"confirm": True}


def test_prompt_without_selection_uses_dialog(monkeypatch):
    monkeypatch.setattr(bridge.sys, "stdin", io.TextIOWrapper(io.BytesIO()))
    monkeypatch.setattr(bridge, "dialog", lambda text, **kwargs: "  my question  ")
    assert bridge.read_prompt() == "my question"


@pytest.mark.parametrize("exit_code", [0, 1])
def test_project_tests_confirm_and_report_readiness_results(
    tmp_path, monkeypatch, exit_code
):
    dialogs = []

    def dialog(message, **kwargs):
        dialogs.append((message, kwargs))
        return "Continue"

    def run(command, **kwargs):
        assert len(dialogs) == 1
        assert dialogs[0][1] == {"confirm": True}
        assert "backend readiness" in dialogs[0][0]
        assert "backup recovery" in dialogs[0][0]
        assert "damaged-backup rejection" in dialogs[0][0]
        assert "failure containment" in dialogs[0][0]
        assert "concurrent writes/restart" in dialogs[0][0]
        assert "crash recovery" in dialogs[0][0]
        assert "cursor recovery" in dialogs[0][0]
        assert "rate-limit recovery" in dialogs[0][0]
        assert "60-second rate window" in dialogs[0][0]
        assert "browser task recovery" in dialogs[0][0]
        assert "complete/reopen" in dialogs[0][0]
        assert "filters/search" in dialogs[0][0]
        assert "details/editing" in dialogs[0][0]
        assert "uncertain-save recovery" in dialogs[0][0]
        assert "Playwright" in dialogs[0][0]
        assert command == [str(Path(sys.executable)), "-m", "pytest", "-q"]
        assert kwargs["cwd"] == tmp_path
        assert kwargs["capture_output"] is True
        return subprocess.CompletedProcess(command, exit_code, "readiness result", "")

    monkeypatch.setattr(bridge, "dialog", dialog)
    monkeypatch.setattr(bridge.subprocess, "run", run)
    if exit_code:
        with pytest.raises(RuntimeError, match="Project tests failed"):
            bridge.run("test", project=tmp_path)
    else:
        bridge.run("test", project=tmp_path)
    assert f"Tests exited with code {exit_code}" in dialogs[-1][0]
    assert "readiness result" in dialogs[-1][0]


def test_project_tests_cancellation_does_not_run_tests(tmp_path, monkeypatch):
    def cancel(*args, **kwargs):
        raise InterruptedError("Cancelled by user.")

    def unexpected_run(*args, **kwargs):
        pytest.fail("Tests must not run after confirmation is cancelled.")

    monkeypatch.setattr(bridge, "dialog", cancel)
    monkeypatch.setattr(bridge.subprocess, "run", unexpected_run)
    with pytest.raises(InterruptedError, match="Cancelled"):
        bridge.run("test", project=tmp_path)


def test_workflow_install_does_not_overwrite(tmp_path):
    if sys.platform != "darwin":
        pytest.skip("Automator is macOS-only")
    paths = install.install(tmp_path / "Services", Path(sys.executable))
    assert len(paths) == 5
    for path in paths:
        with (path / "Contents" / "document.wflow").open("rb") as source:
            workflow = plistlib.load(source)
        assert workflow["actions"][0]["action"]["BundleIdentifier"] == "com.apple.RunShellScript"
        assert "bridge.py" in workflow["actions"][0]["action"]["ActionParameters"]["COMMAND_STRING"]
    with pytest.raises(FileExistsError):
        install.install(tmp_path / "Services", Path(sys.executable))


def test_aristotle_launcher_targets_bundle_without_python(tmp_path):
    if sys.platform != "darwin":
        pytest.skip("Automator is macOS-only")
    app = tmp_path / "pilot's build" / "Matrix Aristotle.app"
    executable = app / "Contents" / "MacOS" / "Matrix Aristotle"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    services = tmp_path / "Services"
    services.mkdir()
    existing = services / "Galileo - Launch.workflow"
    existing.mkdir()
    paths = install.install(services, tmp_path / "missing-python", app_bundle=app)
    assert paths == [services / "Aristotle - Launch.workflow"]
    with (paths[0] / "Contents" / "document.wflow").open("rb") as source:
        workflow = plistlib.load(source)
    command = workflow["actions"][0]["action"]["ActionParameters"]["COMMAND_STRING"]
    assert command == f"exec /usr/bin/open {shlex.quote(str(app))} </dev/null"
    with (paths[0] / "Contents" / "Info.plist").open("rb") as source:
        info = plistlib.load(source)
    assert info["CFBundleIdentifier"] == "net.aethersystem.aristotle.automator.launch"
    assert existing.is_dir()
    with pytest.raises(FileExistsError):
        install.install(services, Path(sys.executable), app_bundle=app)


def test_aristotle_launcher_rejects_missing_bundle_before_install(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    services = tmp_path / "Services"
    with pytest.raises(ValueError, match="executable Matrix Aristotle.app"):
        install.install(
            services, Path(sys.executable), app_bundle=tmp_path / "Matrix Aristotle.app"
        )
    assert not services.exists()


@pytest.mark.parametrize("selected", [False, True])
def test_macos_automator_runs_generated_workflow(tmp_path, selected):
    if sys.platform != "darwin":
        pytest.skip("Automator is macOS-only")
    output = tmp_path / "proof.txt"
    workflow = tmp_path / "Test.workflow"
    install.create_workflow(workflow, "Test", "launch", selected, Path(sys.executable))
    for path in [workflow / "Contents" / "document.wflow",
                 workflow / "Contents" / "Resources" / "document.wflow"]:
        with path.open("rb") as source:
            data = plistlib.load(source)
        command = "cat" if selected else "printf 'automator-ok'"
        data["actions"][0]["action"]["ActionParameters"]["COMMAND_STRING"] = (
            f"{command} > '{output}'"
        )
        with path.open("wb") as target:
            plistlib.dump(data, target)
    command = ["/usr/bin/automator"]
    if selected:
        command.extend(["-i", "-"])
    result = subprocess.run(
        [*command, str(workflow)],
        input="automator-ok\n" if selected else None,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text().strip() == "automator-ok"
