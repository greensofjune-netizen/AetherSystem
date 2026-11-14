import asyncio
import io
import json
import math
import urllib.error

import pytest

from aether_engine import los_link


def _radio_parameters(tx_azimuth=90, rx_azimuth=270):
    return los_link.RadioLinkParameters(
        tx_power_dbm=20,
        rx_sensitivity_dbm=-90,
        tx_antenna=los_link.AntennaPattern(
            peak_gain_dbi=15,
            azimuth_deg=tx_azimuth,
            elevation_deg=0,
            azimuth_beamwidth_deg=60,
            elevation_beamwidth_deg=30,
            feedline_loss_db=1,
        ),
        rx_antenna=los_link.AntennaPattern(
            peak_gain_dbi=15,
            azimuth_deg=rx_azimuth,
            elevation_deg=0,
            azimuth_beamwidth_deg=60,
            elevation_beamwidth_deg=30,
            feedline_loss_db=1,
        ),
    )


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
    assert report["total_path_loss_db"] == report["free_space_path_loss_db"]
    assert report["received_signal_strength_dbm"] is None
    assert report["link_margin_db"] is None


def test_profile_models_terrain_and_building_obstruction():
    args = {
        "tx_lat": 34.0,
        "tx_lon": -117.0,
        "tx_height_m": 10.0,
        "rx_lat": 34.0,
        "rx_lon": -116.99,
        "rx_height_m": 10.0,
        "freq_ghz": 5.8,
    }
    flat_profile = [
        los_link.PathProfilePoint(distance_fraction=0, terrain_elevation_m=0),
        los_link.PathProfilePoint(distance_fraction=0.5, terrain_elevation_m=0),
        los_link.PathProfilePoint(distance_fraction=1, terrain_elevation_m=0),
    ]
    flat = los_link.calculate_los_link_budget(**args, path_profile=flat_profile)
    terrain_profile = [
        flat_profile[0],
        los_link.PathProfilePoint(distance_fraction=0.5, terrain_elevation_m=20),
        flat_profile[-1],
    ]
    terrain = los_link.calculate_los_link_budget(
        **args, path_profile=terrain_profile
    )
    building_profile = [
        flat_profile[0],
        los_link.PathProfilePoint(
            distance_fraction=0.5,
            terrain_elevation_m=0,
            building_height_m=30,
        ),
        flat_profile[-1],
    ]
    building = los_link.calculate_los_link_budget(
        **args, path_profile=building_profile
    )

    assert flat["knife_edge_diffraction_loss_db"] == 0
    assert terrain["dominant_obstacle_type"] == "TERRAIN"
    assert terrain["profile_min_clearance_m"] < 0
    assert terrain["knife_edge_diffraction_loss_db"] > 0
    assert building["dominant_obstacle_type"] == "BUILDING"
    assert building["knife_edge_diffraction_loss_db"] > terrain["knife_edge_diffraction_loss_db"]
    assert building["los_status"] == "OBSTRUCTED_OR_OUT_OF_RANGE"


def test_weather_uses_manual_rain_and_other_loss_inputs():
    args = {
        "tx_lat": 34,
        "tx_lon": -117,
        "tx_height_m": 10,
        "rx_lat": 34,
        "rx_lon": -116.99,
        "rx_height_m": 10,
        "freq_ghz": 10,
    }
    horizontal = los_link.calculate_los_link_budget(
        **args,
        weather=los_link.WeatherConditions(
            rain_rate_mm_h=25,
            rain_path_km=0.5,
            polarization="H",
            other_weather_loss_db=2,
        ),
    )
    vertical = los_link.calculate_los_link_budget(
        **args,
        weather=los_link.WeatherConditions(
            rain_rate_mm_h=25,
            rain_path_km=0.5,
            polarization="V",
            other_weather_loss_db=2,
        ),
    )

    assert horizontal["rain_attenuation_db"] == pytest.approx(0.35, abs=0.05)
    assert vertical["rain_attenuation_db"] == pytest.approx(0.28, abs=0.05)
    assert horizontal["rain_attenuation_db"] > vertical["rain_attenuation_db"]
    assert horizontal["weather_attenuation_db"] == pytest.approx(
        horizontal["rain_attenuation_db"] + 2
    )
    assert horizontal["total_path_loss_db"] == pytest.approx(
        horizontal["free_space_path_loss_db"]
        + horizontal["weather_attenuation_db"]
    )


def test_radio_parameters_produce_rssi_and_orientation_degrades_gain():
    args = {
        "tx_lat": 34.0,
        "tx_lon": -117.0,
        "tx_height_m": 10.0,
        "rx_lat": 34.0,
        "rx_lon": -116.99,
        "rx_height_m": 10.0,
        "freq_ghz": 5.8,
    }
    aligned = los_link.calculate_los_link_budget(
        **args, radio=_radio_parameters()
    )
    misaligned = los_link.calculate_los_link_budget(
        **args, radio=_radio_parameters(tx_azimuth=0)
    )

    assert aligned["tx_antenna_gain_dbi"] == 15
    assert aligned["rx_antenna_gain_dbi"] == 15
    assert aligned["received_signal_strength_dbm"] is not None
    assert aligned["link_margin_db"] == pytest.approx(
        aligned["received_signal_strength_dbm"] - (-90)
    )
    assert aligned["link_status"] == "POSITIVE_MARGIN_ESTIMATE"
    assert aligned["received_signal_strength_dbm"] - misaligned["received_signal_strength_dbm"] == pytest.approx(27)


@pytest.mark.parametrize(
    ("profile", "message"),
    [
        (
            [
                los_link.PathProfilePoint(distance_fraction=0, terrain_elevation_m=0),
                los_link.PathProfilePoint(distance_fraction=0.8, terrain_elevation_m=0),
                los_link.PathProfilePoint(distance_fraction=0.7, terrain_elevation_m=0),
                los_link.PathProfilePoint(distance_fraction=1, terrain_elevation_m=0),
            ],
            "must increase",
        ),
    ],
)
def test_link_budget_rejects_invalid_path_profiles(profile, message):
    with pytest.raises(ValueError, match=message):
        los_link.calculate_los_link_budget(
            tx_lat=34,
            tx_lon=-117,
            tx_height_m=10,
            rx_lat=34,
            rx_lon=-116.99,
            rx_height_m=10,
            path_profile=profile,
        )


def test_link_budget_rejects_weather_path_longer_than_radio_path():
    with pytest.raises(ValueError, match="cannot exceed"):
        los_link.calculate_los_link_budget(
            tx_lat=34,
            tx_lon=-117,
            tx_height_m=10,
            rx_lat=34,
            rx_lon=-116.99,
            rx_height_m=10,
            weather=los_link.WeatherConditions(
                rain_rate_mm_h=10,
                rain_path_km=2,
            ),
        )


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
