import json

import pytest

from aether_engine import local_ai_runtime


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body

    def read(self, _limit):
        return self.body


class FakeConnection:
    def __init__(self, response):
        self.response = response
        self.request_args = None
        self.closed = False

    def request(self, method, path, *, body, headers):
        self.request_args = (method, path, json.loads(body), headers)

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def test_preload_loads_installed_model_without_pulling_or_generating(monkeypatch):
    connection = FakeConnection(
        FakeResponse(
            200,
            json.dumps(
                {"model": local_ai_runtime.DEFAULT_LOCAL_MODEL, "done": True}
            ).encode(),
        )
    )
    monkeypatch.setattr(
        local_ai_runtime.http.client,
        "HTTPConnection",
        lambda host, port, timeout: connection,
    )

    local_ai_runtime.preload_local_model(local_ai_runtime.DEFAULT_LOCAL_MODEL)

    method, path, payload, headers = connection.request_args
    assert (method, path) == ("POST", "/api/generate")
    assert payload == {
        "model": local_ai_runtime.DEFAULT_LOCAL_MODEL,
        "prompt": "",
        "stream": False,
        "keep_alive": "10m",
        "options": {"num_predict": 0},
    }
    assert headers == {"Content-Type": "application/json"}
    assert connection.closed


def test_shared_default_is_compact_vision_model():
    assert local_ai_runtime.DEFAULT_LOCAL_MODEL == "qwen3.5:4b"


def test_preload_surfaces_ollama_model_error(monkeypatch):
    connection = FakeConnection(
        FakeResponse(500, b'{"error":"model does not fit in available memory"}')
    )
    monkeypatch.setattr(
        local_ai_runtime.http.client,
        "HTTPConnection",
        lambda host, port, timeout: connection,
    )

    with pytest.raises(
        local_ai_runtime.LocalModelUnavailableError,
        match="model does not fit in available memory",
    ):
        local_ai_runtime.preload_local_model(local_ai_runtime.DEFAULT_LOCAL_MODEL)
    assert connection.closed
