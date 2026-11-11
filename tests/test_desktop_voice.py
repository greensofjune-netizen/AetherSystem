import json
import os
import subprocess
import threading
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest

from aether_engine import desktop_voice
from aether_engine.desktop_voice import DesktopVoice


@pytest.fixture
def voice(monkeypatch: pytest.MonkeyPatch) -> DesktopVoice:
    monkeypatch.setattr(desktop_voice.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    return DesktopVoice()


@pytest.fixture
def process(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    child = MagicMock()
    child.returncode = 0
    child.poll.return_value = 0
    child.communicate.return_value = (b'{"ok":true,"text":"hello"}', b"")
    monkeypatch.setattr(
        desktop_voice.subprocess, "Popen", MagicMock(return_value=child)
    )
    return child


def test_dictation_success_and_fixed_command(
    voice: DesktopVoice, process: MagicMock
) -> None:
    assert voice.dictation() == {"ok": True, "text": "hello"}
    args, kwargs = cast(MagicMock, desktop_voice.subprocess.Popen).call_args
    assert Path(args[0][0]).name == "galileo-voice"
    assert Path(args[0][0]).parent == Path(desktop_voice.__file__).resolve().parent
    assert args[0][1] == "--stop-fd"
    assert kwargs["pass_fds"] == (int(args[0][2]),)
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert "shell" not in kwargs
    process.communicate.assert_called_once_with(timeout=55)
    process.stdout.close.assert_called_once()
    process.stderr.close.assert_called_once()
    assert voice._dictation is None
    assert voice._stop_fd is None


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"not json", "invalid response"),
        (b"\xff", "invalid response"),
        (b"[]", "invalid response"),
        (b'{"ok":1}', "invalid response"),
        (b'{"ok":true,"text":null}', "No speech"),
        (b'{"ok":true,"text":" "}', "No speech"),
        (b'{"ok":false}', "invalid response"),
        (b'{"ok":false,"error":"Speech permission denied."}', "permission denied"),
        (b'{"ok":false,"error":"On-device unavailable."}', "unavailable"),
    ],
)
def test_dictation_protocol_errors(
    voice: DesktopVoice, process: MagicMock, payload: bytes, message: str
) -> None:
    process.communicate.return_value = (payload, b"")
    result = voice.dictation()
    assert result["ok"] is False
    assert message in result["error"]


def test_missing_helper(voice: DesktopVoice, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "is_file", lambda self: False)
    assert "unavailable" in voice.dictation()["error"]


@pytest.mark.parametrize("operation", ["dictation", "speak"])
def test_launch_error(voice: DesktopVoice, process: MagicMock, operation: str) -> None:
    cast(MagicMock, desktop_voice.subprocess.Popen).side_effect = OSError(
        "permission denied"
    )
    result = voice.dictation() if operation == "dictation" else voice.speak("hi")
    assert "Unable to start" in result["error"]
    assert voice._dictation is None
    assert voice._speaking is None


@pytest.mark.parametrize("operation", ["dictation", "speak"])
@pytest.mark.parametrize(
    "failure", [subprocess.TimeoutExpired("helper", 55), OSError("broken pipe")]
)
def test_communication_failure_terminates_and_reaps(
    voice: DesktopVoice, process: MagicMock, operation: str, failure: Exception
) -> None:
    process.poll.return_value = None
    process.communicate.side_effect = failure
    process.wait.side_effect = [subprocess.TimeoutExpired("helper", 1), 0]
    result = voice.dictation() if operation == "dictation" else voice.speak("hi")
    assert result["ok"] is False
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    assert process.wait.call_count == 2
    assert voice._dictation is None
    assert voice._speaking is None


@pytest.mark.parametrize("operation", ["dictation", "speak"])
def test_nonzero_exit(voice: DesktopVoice, process: MagicMock, operation: str) -> None:
    process.returncode = -15
    result = voice.dictation() if operation == "dictation" else voice.speak("hi")
    assert result["ok"] is False


def test_speak_uses_stdin_not_arguments(
    voice: DesktopVoice, process: MagicMock
) -> None:
    text = '-v Alex; $(touch never) "quoted" é\nsecond line'
    assert voice.speak(text) == {"ok": True}
    args, kwargs = cast(MagicMock, desktop_voice.subprocess.Popen).call_args
    assert args == (["/usr/bin/say"],)
    assert kwargs["stdin"] == subprocess.PIPE
    assert "shell" not in kwargs
    process.communicate.assert_called_once_with(input=text.encode(), timeout=120)
    process.stdin.close.assert_called_once()


@pytest.mark.parametrize("text", ["", " \n", None, 123, "\ud800", "é" * 120_001])
def test_speak_validation(
    voice: DesktopVoice, process: MagicMock, text: object
) -> None:
    assert voice.speak(text)["ok"] is False  # type: ignore[arg-type]
    cast(MagicMock, desktop_voice.subprocess.Popen).assert_not_called()


def test_speak_exact_byte_limit(voice: DesktopVoice, process: MagicMock) -> None:
    assert voice.speak("é" * 120_000)["ok"] is True


def test_unavailable_platform(
    voice: DesktopVoice, process: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(desktop_voice.sys, "platform", "linux")
    assert "macOS" in voice.dictation()["error"]
    assert "macOS" in voice.speak("hi")["error"]
    cast(MagicMock, desktop_voice.subprocess.Popen).assert_not_called()


def test_stop_dictation_preserves_partial_and_rejects_overlap(
    voice: DesktopVoice, process: MagicMock
) -> None:
    entered = threading.Event()
    finish = threading.Event()
    results: list[desktop_voice.VoiceResult] = []
    process.poll.return_value = None

    def communicate(*, timeout: int) -> tuple[bytes, bytes]:
        entered.set()
        assert finish.wait(3)
        process.poll.return_value = 0
        return json.dumps({"ok": True, "text": "partial words"}).encode(), b""

    process.communicate.side_effect = communicate
    worker = threading.Thread(target=lambda: results.append(voice.dictation()))
    worker.start()
    try:
        assert entered.wait(3)
        assert "already active" in voice.dictation()["error"]
        descriptor = voice._stop_fd
        assert descriptor is not None
        assert voice.stop_dictation() == {"ok": True}
        with pytest.raises(OSError):
            os.fstat(descriptor)
        assert voice.stop_dictation() == {"ok": True}
        process.terminate.assert_not_called()
        process.kill.assert_not_called()
    finally:
        finish.set()
        worker.join(3)
    assert not worker.is_alive()
    assert results == [{"ok": True, "text": "partial words"}]


def test_stop_speaking_and_close(voice: DesktopVoice, process: MagicMock) -> None:
    entered = threading.Event()
    finish = threading.Event()
    results: list[desktop_voice.VoiceResult] = []
    process.poll.return_value = None

    def communicate(*, input: bytes, timeout: int) -> tuple[bytes, bytes]:
        entered.set()
        assert finish.wait(3)
        process.returncode = -15
        process.poll.return_value = -15
        return b"", b""

    process.communicate.side_effect = communicate
    worker = threading.Thread(target=lambda: results.append(voice.speak("hi")))
    worker.start()
    try:
        assert entered.wait(3)
        assert "already active" in voice.speak("again")["error"]
        assert voice.stop_speaking() == {"ok": True}
        process.terminate.assert_called_once()
    finally:
        finish.set()
        worker.join(3)
    assert not worker.is_alive()
    assert results[0]["ok"] is False
    voice.close()
    voice.close()
    assert "closed" in voice.dictation()["error"]
    assert "closed" in voice.speak("hi")["error"]


def test_close_terminates_only_tracked_children(
    voice: DesktopVoice, process: MagicMock
) -> None:
    speaking = MagicMock()
    speaking.poll.return_value = None
    process.poll.return_value = None
    voice._dictation = process
    voice._speaking = speaking
    read_fd, write_fd = os.pipe()
    voice._stop_fd = write_fd
    try:
        voice.close()
        assert os.read(read_fd, 1) == b""
    finally:
        os.close(read_fd)
    process.terminate.assert_called_once()
    speaking.terminate.assert_called_once()


def test_termination_exit_race(voice: DesktopVoice, process: MagicMock) -> None:
    process.poll.return_value = None
    process.terminate.side_effect = ProcessLookupError()
    voice._speaking = process
    assert voice.stop_speaking() == {"ok": True}
    process.kill.assert_not_called()
