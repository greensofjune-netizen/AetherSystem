import asyncio
import io
import json
import math
import urllib.error

import pytest

from aether_engine import los_link


def test_link_budget_estimates_distance_clearance_and_path_loss():
    report = los_link.calculate_los_link_budget(
        tx_lat=34.0975,
        tx_lon=-117.6484,
        tx_height_m=25.0,
        rx_lat=34.1425,
        rx_lon=-117.6510,
        rx_height_m=18.0,
        freq_ghz=5.8,
    )

    assert 4.9 < report["distance_km"] < 5.2
    assert report["max_radio_horizon_km"] > report["distance_km"]
    assert report["earth_bulge_m"] > 0
    assert report["fresnel_60pct_clearance_m"] > 0
    assert report["free_space_path_loss_db"] == pytest.approx(
        20 * math.log10(report["distance_km"])
        + 20 * math.log10(5.8)
        + 92.45,
        abs=0.02,
    )
    assert report["los_status"] == "CLEAR_LOS_ESTIMATE"


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"tx_lat": 91}, "Latitude"),
        ({"rx_lon": 181}, "Longitude"),
        ({"tx_height_m": -1}, "non-negative"),
        ({"freq_ghz": 0}, "greater than zero"),
        ({"rx_lat": float("nan")}, "finite numbers"),
        ({"tx_lon": True}, "finite numbers"),
    ],
)
def test_link_budget_rejects_invalid_inputs(updates, message):
    values = {
        "tx_lat": 34.0,
        "tx_lon": -117.0,
        "tx_height_m": 25.0,
        "rx_lat": 34.1,
        "rx_lon": -117.1,
        "rx_height_m": 18.0,
        "freq_ghz": 5.8,
    }

    with pytest.raises(ValueError, match=message):
        los_link.calculate_los_link_budget(**(values | updates))


def test_publisher_sends_valid_matrix_envelope_and_shared_token(monkeypatch):
    monkeypatch.setenv("AETHER_API_TOKEN", "test-token")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=-1):
            return b'{"status":"ACCEPTED","event_id":42}'

    class FakeOpener:
        def open(self, request, *, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

    monkeypatch.setattr(
        los_link.urllib.request, "build_opener", lambda *_handlers: FakeOpener()
    )
    result = asyncio.run(
        los_link.publish_telemetry_to_aether(
            "LOS_LINK_BUDGET_CALCULATED",
            {"distance_km": 5.0},
            dispatch_url="https://matrix.example/api/v1/unified/dispatch",
        )
    )

    request = captured["request"]
    envelope = json.loads(request.data)
    assert request.get_header("X-aether-token") == "test-token"
    assert captured["timeout"] == 3.0
    assert envelope["node"] == "MATRIX"
    assert envelope["source_lang"] == "python"
    assert envelope["event"] == "LOS_LINK_BUDGET_CALCULATED"
    assert envelope["payload"] == {"distance_km": 5.0}
    assert result["event_id"] == 42


def test_publisher_rejects_insecure_remote_token_transport(monkeypatch):
    monkeypatch.setenv("AETHER_API_TOKEN", "test-token")

    with pytest.raises(ValueError, match="HTTPS is required"):
        asyncio.run(
            los_link.publish_telemetry_to_aether(
                "LOS_LINK_BUDGET_CALCULATED",
                {},
                dispatch_url="http://matrix.example/api/v1/unified/dispatch",
            )
        )


def test_publisher_surfaces_dispatch_http_errors(monkeypatch):
    class RejectingOpener:
        def open(self, _request, *, timeout):
            raise urllib.error.HTTPError(
                "http://127.0.0.1:8000/api/v1/unified/dispatch",
                401,
                "Unauthorized",
                {},
                io.BytesIO(b'{"detail":"token required"}'),
            )

    monkeypatch.delenv("AETHER_API_TOKEN", raising=False)
    monkeypatch.setattr(
        los_link.urllib.request,
        "build_opener",
        lambda *_handlers: RejectingOpener(),
    )

    with pytest.raises(RuntimeError, match="HTTP 401"):
        asyncio.run(
            los_link.publish_telemetry_to_aether(
                "LOS_LINK_BUDGET_CALCULATED", {}
            )
        )


def test_cli_supports_offline_estimate(capsys):
    assert los_link.main(["--no-publish"]) == 0
    assert '"distance_km"' in capsys.readouterr().out
