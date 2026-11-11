"""Local macOS speech processes; no audio or transcripts are written to disk."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import TypedDict


class VoiceResult(TypedDict, total=False):
    ok: bool
    text: str
    error: str


def _error(message: str) -> VoiceResult:
    return {"ok": False, "error": message}


class DesktopVoice:
    """Thread-safe bridge for pywebview; instantiate once and close on shutdown.

    ``galileo-voice`` must be compiled and bundled alongside this module. Dictation
    listens for 15 seconds; a private pipe ends capture and preserves partial results.
    Read-aloud uses only /usr/bin/say, passing UTF-8 text through standard input.
    """

    def __init__(self) -> None:
        self._helper = Path(__file__).resolve().with_name("galileo-voice")
        self._lock = threading.RLock()
        self._dictation: subprocess.Popen[bytes] | None = None
        self._stop_fd: int | None = None
        self._speaking: subprocess.Popen[bytes] | None = None
        self._closed = False

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except ProcessLookupError:
                return
            process.wait(timeout=1)

    def dictation(self) -> VoiceResult:
        """Finish within 60 seconds, returning a transcript or explicit error."""
        with self._lock:
            if self._closed:
                return _error("Voice support is closed.")
            if sys.platform != "darwin":
                return _error("Native dictation is only available on macOS.")
            if self._dictation is not None:
                return _error("Dictation is already active.")
            if not self._helper.is_file():
                return _error("Bundled galileo-voice helper is unavailable.")
            read_fd: int | None = None
            write_fd: int | None = None
            try:
                read_fd, write_fd = os.pipe()
                process = subprocess.Popen(
                    [str(self._helper), "--stop-fd", str(read_fd)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    pass_fds=(read_fd,),
                )
            except OSError as exc:
                if write_fd is not None:
                    os.close(write_fd)
                return _error(f"Unable to start native dictation: {exc}")
            finally:
                if read_fd is not None:
                    os.close(read_fd)
            self._dictation = process
            self._stop_fd = write_fd
        try:
            try:
                output, _ = process.communicate(timeout=55)
            except subprocess.TimeoutExpired:
                return _error(
                    "Dictation timed out. Check Speech and microphone access."
                )
            except OSError as exc:
                return _error(f"Native dictation communication failed: {exc}")
            if process.returncode != 0:
                return _error("Native dictation was interrupted or the helper failed.")
            try:
                result = json.loads(output)
            except (ValueError, UnicodeDecodeError):
                return _error("Native dictation returned an invalid response.")
            if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
                return _error("Native dictation returned an invalid response.")
            if result["ok"]:
                text = result.get("text")
                if not isinstance(text, str) or not text.strip():
                    return _error("No speech was recognized.")
                return {"ok": True, "text": text.strip()}
            error = result.get("error")
            if not isinstance(error, str) or not error.strip():
                return _error("Native dictation returned an invalid response.")
            return _error(error)
        finally:
            with self._lock:
                self._terminate(process)
                if self._dictation is process:
                    self._dictation = None
                    if self._stop_fd is not None:
                        os.close(self._stop_fd)
                        self._stop_fd = None
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()

    def stop_dictation(self) -> VoiceResult:
        """Finish recognition, rather than discarding the transcript by killing."""
        with self._lock:
            # EOF is queued even if the helper has not installed its listener yet.
            if self._stop_fd is not None:
                os.close(self._stop_fd)
                self._stop_fd = None
        return {"ok": True}

    def speak(self, text: str) -> VoiceResult:
        """Read text aloud synchronously, with a two-minute process deadline."""
        if not isinstance(text, str) or not text.strip():
            return _error("Read-aloud requires non-empty text.")
        try:
            encoded = text.encode("utf-8")
        except UnicodeEncodeError:
            return _error("Read-aloud text must be valid UTF-8.")
        if len(encoded) > 240_000:
            return _error("Read-aloud text exceeds the 240,000-byte UTF-8 limit.")
        with self._lock:
            if self._closed:
                return _error("Voice support is closed.")
            if sys.platform != "darwin":
                return _error("Native read-aloud is only available on macOS.")
            if self._speaking is not None:
                return _error("Read-aloud is already active.")
            try:
                process = subprocess.Popen(
                    ["/usr/bin/say"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as exc:
                return _error(f"Unable to start native read-aloud: {exc}")
            self._speaking = process
        try:
            try:
                process.communicate(input=encoded, timeout=120)
            except subprocess.TimeoutExpired:
                return _error("Read-aloud exceeded its two-minute time limit.")
            except OSError as exc:
                return _error(f"Native read-aloud communication failed: {exc}")
            if process.returncode != 0:
                return _error("Read-aloud was stopped or failed.")
            return {"ok": True}
        finally:
            with self._lock:
                self._terminate(process)
                if self._speaking is process:
                    self._speaking = None
                if process.stdin is not None:
                    process.stdin.close()

    def stop_speaking(self) -> VoiceResult:
        with self._lock:
            if self._speaking is not None:
                self._terminate(self._speaking)
        return {"ok": True}

    def close(self) -> None:
        """Prevent new work and terminate only this instance's tracked children."""
        with self._lock:
            self._closed = True
            if self._stop_fd is not None:
                os.close(self._stop_fd)
                self._stop_fd = None
            for process in (self._dictation, self._speaking):
                if process is not None:
                    self._terminate(process)
