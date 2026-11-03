import getpass
import json
import os
import shlex
import shutil
import socket
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

from aether_engine.database import AetherStore
from backup_replication import BackupReplicator, main


def test_local_backup_contains_real_project_data_and_is_private(
    tmp_path: Path, capsys
) -> None:
    database = tmp_path / "project.sqlite3"
    store = AetherStore(database)
    store.add_task("Actual task", "Actual description", "high", "2026-12-01")
    store.add_event("test", "Actual event")

    replicator = BackupReplicator(
        database, backup_dir=tmp_path / "local-backups"
    )
    backup = replicator.generate_local_backup()

    payload = json.loads(backup.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["tasks"][0]["title"] == "Actual task"
    assert payload["tasks"][0]["priority"] == "high"
    assert payload["events"][0]["message"] == "Actual event"
    assert backup.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "local-backups").stat().st_mode & 0o777 == 0o700
    assert "Local Aether backup created" in capsys.readouterr().out


def test_missing_database_does_not_create_empty_backup(tmp_path: Path) -> None:
    database = tmp_path / "missing.sqlite3"
    replicator = BackupReplicator(database, backup_dir=tmp_path / "backups")

    with pytest.raises(FileNotFoundError, match="Database file does not exist"):
        replicator.generate_local_backup()

    assert not (tmp_path / "backups").exists()


def test_non_aether_database_is_rejected_without_modification(
    tmp_path: Path,
) -> None:
    database = tmp_path / "other.sqlite3"
    database.write_bytes(b"not an sqlite database")
    original = database.read_bytes()
    replicator = BackupReplicator(database, backup_dir=tmp_path / "backups")

    with pytest.raises(sqlite3.DatabaseError):
        replicator.generate_local_backup()

    assert database.read_bytes() == original
    assert not (tmp_path / "backups").exists()


def test_replication_uses_explicit_ssh_target_and_existing_backup(
    tmp_path: Path, capsys
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    database = tmp_path / "project.sqlite3"
    AetherStore(database).add_task("Replicate me")
    replicator = BackupReplicator(
        database,
        "backup-user",
        "backup.example.net",
        "/srv/backups/aether",
        backup_dir=tmp_path / "local",
        identity_file=tmp_path / "ssh-key",
        runner=fake_run,
    )

    backup = replicator.generate_local_backup()
    assert replicator.replicate_off_machine(backup)

    command, options = calls[0]
    assert command[:5] == [
        "scp",
        "-p",
        "-o",
        "BatchMode=yes",
        "-i",
    ]
    assert command[5] == str(tmp_path / "ssh-key")
    assert command[-2] == str(backup.resolve())
    assert command[-1] == (
        f"backup-user@backup.example.net:/srv/backups/aether/{backup.name}"
    )
    assert options["check"] is True
    assert options["timeout"] == 120
    assert "Off-machine backup copy complete" in capsys.readouterr().out


def test_remote_transfer_failure_is_reported(tmp_path: Path, capsys) -> None:
    def failed_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(
            1, command, stderr="connection unavailable"
        )

    database = tmp_path / "project.sqlite3"
    AetherStore(database)
    replicator = BackupReplicator(
        database,
        "backup-user",
        "backup.example.net",
        "/srv/backups",
        backup_dir=tmp_path / "local",
        runner=failed_run,
    )

    backup = replicator.generate_local_backup()
    assert not replicator.replicate_off_machine(backup)
    assert "connection unavailable" in capsys.readouterr().err


def test_remote_destination_shell_metacharacters_are_quoted(
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    database = tmp_path / "project.sqlite3"
    AetherStore(database)
    remote_dir = "/srv/backup; touch /tmp/unexpected"
    replicator = BackupReplicator(
        database,
        "backup-user",
        "backup.example.net",
        remote_dir,
        backup_dir=tmp_path / "local",
        runner=fake_run,
    )
    backup = replicator.generate_local_backup()

    assert replicator.replicate_off_machine(backup)
    expected_path = f"{remote_dir}/{backup.name}"
    assert commands[0][-1] == (
        f"backup-user@backup.example.net:{shlex.quote(expected_path)}"
    )
    assert shlex.split(commands[0][-1]) == [
        f"backup-user@backup.example.net:{expected_path}"
    ]


def test_remote_options_are_validated_and_local_mode_never_transfers(
    tmp_path: Path, capsys
) -> None:
    with pytest.raises(ValueError, match="provided together"):
        BackupReplicator(tmp_path / "db.sqlite3", remote_user="user")
    with pytest.raises(ValueError, match="unsupported characters"):
        BackupReplicator(
            tmp_path / "db.sqlite3",
            "user;bad",
            "host.example",
            "/backup",
        )
    with pytest.raises(ValueError, match="absolute POSIX path"):
        BackupReplicator(
            tmp_path / "db.sqlite3",
            "user",
            "host.example",
            "~/backup",
        )
    with pytest.raises(ValueError, match="absolute POSIX path"):
        BackupReplicator(
            tmp_path / "db.sqlite3",
            "user",
            "host.example",
            "/backup/\0invalid",
        )

    database = tmp_path / "project.sqlite3"
    AetherStore(database)
    assert main(
        ["--database", str(database), "--backup-dir", str(tmp_path / "local")]
    ) == 0
    output = capsys.readouterr().out
    assert "Local-only mode" in output


@pytest.mark.skipif(
    os.name == "nt",
    reason="the loopback OpenSSH integration fixture requires a Unix sshd",
)
def test_scp_transfer_to_loopback_sshd(tmp_path: Path) -> None:
    sshd = shutil.which("sshd")
    ssh = shutil.which("ssh")
    ssh_keygen = shutil.which("ssh-keygen")
    scp = shutil.which("scp")
    if not all((sshd, ssh, ssh_keygen, scp)):
        pytest.skip("OpenSSH server/client tools are not installed")

    client_key = tmp_path / "client_key"
    host_key = tmp_path / "host_key"
    authorized_keys = tmp_path / "authorized_keys"
    for key_path in (client_key, host_key):
        subprocess.run(
            [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(key_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    authorized_keys.write_text(
        client_key.with_suffix(".pub").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]

    config = tmp_path / "sshd_config"
    config.write_text(
        "\n".join(
            (
                f"Port {port}",
                "ListenAddress 127.0.0.1",
                f"HostKey {host_key}",
                f"PidFile {tmp_path / 'sshd.pid'}",
                f"AuthorizedKeysFile {authorized_keys}",
                "PubkeyAuthentication yes",
                "PasswordAuthentication no",
                "KbdInteractiveAuthentication no",
                "PermitRootLogin yes",
                "UsePAM no",
                "StrictModes no",
                "Subsystem sftp internal-sftp",
                "LogLevel ERROR",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        [sshd, "-t", "-f", str(config)],
        check=True,
        capture_output=True,
        text=True,
    )
    server_log = (tmp_path / "sshd.log").open("w+", encoding="utf-8")
    server = subprocess.Popen(
        [sshd, "-D", "-e", "-f", str(config)],
        stdout=subprocess.DEVNULL,
        stderr=server_log,
        text=True,
    )
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if server.poll() is not None:
                server_log.flush()
                server_log.seek(0)
                pytest.fail(f"Local sshd exited before accepting connections:\n{server_log.read()}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            pytest.fail("Local sshd did not start listening.")

        database = tmp_path / "project.sqlite3"
        store = AetherStore(database)
        store.add_task("SCP integration task")
        backup_directory = tmp_path / "local-backups"
        remote_directory = tmp_path / "remote-backups"
        remote_directory.mkdir()
        username = getpass.getuser()

        def real_scp_runner(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
            command = [
                command[0],
                "-P",
                str(port),
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                *command[1:],
            ]
            return subprocess.run(command, **kwargs)

        replicator = BackupReplicator(
            database,
            username,
            "127.0.0.1",
            str(remote_directory),
            backup_dir=backup_directory,
            identity_file=client_key,
            runner=real_scp_runner,
        )
        backup = replicator.generate_local_backup()

        assert replicator.replicate_off_machine(backup)
        copied_backup = remote_directory / backup.name
        assert copied_backup.is_file()
        copied_payload = json.loads(copied_backup.read_text(encoding="utf-8"))
        assert copied_payload["tasks"][0]["title"] == "SCP integration task"
    finally:
        server.terminate()
        server.wait(timeout=5)
        server_log.close()
