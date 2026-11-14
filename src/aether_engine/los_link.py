"""Estimate radio line-of-sight geometry and publish MATRIX telemetry."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field

AETHER_DISPATCH_URL = "http://127.0.0.1:8000/api/v1/unified/dispatch"
EARTH_RADIUS_KM = 6371.0
EFFECTIVE_K_FACTOR = 4.0 / 3.0
_EVENT_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_MAX_RESPONSE_BYTES = 64 * 1024


class _StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PathProfilePoint(_StrictInput):
    distance_fraction: float = Field(ge=0, le=1)
    terrain_elevation_m: float = Field(ge=-12_000, le=10_000)
    building_height_m: float = Field(default=0, ge=0, le=1_000)


class WeatherConditions(_StrictInput):
    rain_rate_mm_h: float = Field(ge=0, le=500)
    rain_path_km: float = Field(ge=0, le=20_000)
    polarization: Literal["H", "V"] = "H"
    other_weather_loss_db: float = Field(default=0, ge=0, le=1_000)


class AntennaPattern(_StrictInput):
    peak_gain_dbi: float = Field(ge=-100, le=100)
    azimuth_deg: float = Field(ge=0, le=360)
    elevation_deg: float = Field(ge=-90, le=90)
    azimuth_beamwidth_deg: float = Field(gt=0, le=360)
    elevation_beamwidth_deg: float = Field(gt=0, le=180)
    feedline_loss_db: float = Field(default=0, ge=0, le=100)


class RadioLinkParameters(_StrictInput):
    tx_power_dbm: float = Field(ge=-100, le=100)
    rx_sensitivity_dbm: float = Field(ge=-200, le=50)
    tx_antenna: AntennaPattern
    rx_antenna: AntennaPattern


class _ITUFit(NamedTuple):
    a: tuple[float, ...]
    b: tuple[float, ...]
    c: tuple[float, ...]
    slope: float
    offset: float


_P838_FITS = {
    "H": (
        _ITUFit(
            (-5.33980, -0.35351, -0.23789, -0.94158),
            (-0.10008, 1.26970, 0.86036, 0.64552),
            (1.13098, 0.45400, 0.15354, 0.16817),
            -0.18961,
            0.71147,
        ),
        _ITUFit(
            (-0.14318, 0.29591, 0.32177, -5.37610, 16.1721),
            (1.82442, 0.77564, 0.63773, -0.96230, -3.29980),
            (0.55187, 0.19822, 0.13164, 1.47828, 3.43990),
            0.67849,
            -1.95537,
        ),
    ),
    "V": (
        _ITUFit(
            (-3.80595, -3.44965, -0.39902, 0.50167),
            (0.56934, -0.22911, 0.73042, 1.07319),
            (0.81061, 0.51059, 0.11899, 0.27195),
            -0.16398,
            0.63297,
        ),
        _ITUFit(
            (-0.07771, 0.56727, -0.20238, -48.2991, 48.5833),
            (2.33840, 0.95545, 1.14520, 0.791669, 0.791459),
            (0.76284, 0.54039, 0.26809, 0.116226, 0.116479),
            -0.053739,
            0.83433,
        ),
    ),
}


def _itu_fit_value(frequency_ghz: float, fit: _ITUFit) -> float:
    log_frequency = math.log10(frequency_ghz)
    return sum(
        a * math.exp(-((log_frequency - b) / c) ** 2)
        for a, b, c in zip(fit.a, fit.b, fit.c, strict=True)
    ) + fit.slope * log_frequency + fit.offset


def _rain_specific_attenuation_db_km(
    frequency_ghz: float, rain_rate_mm_h: float, polarization: Literal["H", "V"]
) -> float:
    if rain_rate_mm_h == 0:
        return 0.0
    if not 1 <= frequency_ghz <= 100:
        raise ValueError("ITU-R P.838 rain attenuation requires 1-100 GHz.")
    k_fit, alpha_fit = _P838_FITS[polarization]
    k = 10 ** _itu_fit_value(frequency_ghz, k_fit)
    alpha = _itu_fit_value(frequency_ghz, alpha_fit)
    return k * rain_rate_mm_h**alpha


def _knife_edge_loss_db(v: float) -> float:
    if v <= -0.78:
        return 0.0
    return 6.9 + 20.0 * math.log10(
        math.sqrt((v - 0.1) ** 2 + 1.0) + v - 0.1
    )


def _bearing_degrees(
    start_lat: float, start_lon: float, end_lat: float, end_lon: float
) -> float:
    phi1, phi2 = math.radians(start_lat), math.radians(end_lat)
    delta_lon = math.radians(end_lon - start_lon)
    bearing = math.degrees(
        math.atan2(
            math.sin(delta_lon) * math.cos(phi2),
            math.cos(phi1) * math.sin(phi2)
            - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lon),
        )
    )
    return bearing % 360.0


def _antenna_gain_toward(
    antenna: AntennaPattern, target_azimuth_deg: float, target_elevation_deg: float
) -> float:
    azimuth_offset = abs(
        (target_azimuth_deg - antenna.azimuth_deg + 180.0) % 360.0 - 180.0
    )
    elevation_offset = abs(target_elevation_deg - antenna.elevation_deg)
    off_axis_loss = min(
        30.0,
        12.0 * (azimuth_offset / antenna.azimuth_beamwidth_deg) ** 2
        + 12.0 * (elevation_offset / antenna.elevation_beamwidth_deg) ** 2,
    )
    return antenna.peak_gain_dbi - off_axis_loss


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None


def calculate_los_link_budget(
    tx_lat: float,
    tx_lon: float,
    tx_height_m: float,
    rx_lat: float,
    rx_lon: float,
    rx_height_m: float,
    freq_ghz: float = 5.8,
    *,
    path_profile: Sequence[PathProfilePoint] | None = None,
    weather: WeatherConditions | None = None,
    radio: RadioLinkParameters | None = None,
) -> dict[str, Any]:
    """Estimate a point-to-point radio path using a 4/3-Earth model.

    Optional user-supplied profiles, weather, and equipment parameters add
    deterministic estimates; they are not live data or field measurements.
    """
    values = (tx_lat, tx_lon, tx_height_m, rx_lat, rx_lon, rx_height_m, freq_ghz)
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in values
    ):
        raise ValueError("Coordinates, antenna heights, and frequency must be finite numbers.")
    if not -90 <= tx_lat <= 90 or not -90 <= rx_lat <= 90:
        raise ValueError("Latitude must be between -90 and 90 degrees.")
    if not -180 <= tx_lon <= 180 or not -180 <= rx_lon <= 180:
        raise ValueError("Longitude must be between -180 and 180 degrees.")
    if tx_height_m < 0 or rx_height_m < 0:
        raise ValueError("Antenna heights must be non-negative.")
    if freq_ghz <= 0:
        raise ValueError("Frequency must be greater than zero.")
    if path_profile is not None:
        if not 2 <= len(path_profile) <= 512:
            raise ValueError("Path profile must contain between 2 and 512 points.")
        if (
            path_profile[0].distance_fraction != 0
            or path_profile[-1].distance_fraction != 1
            or any(
                left.distance_fraction >= right.distance_fraction
                for left, right in zip(path_profile, path_profile[1:])
            )
        ):
            raise ValueError(
                "Path profile fractions must increase from exactly 0 to exactly 1."
            )
        if any(
            point.building_height_m != 0
            for point in (path_profile[0], path_profile[-1])
        ):
            raise ValueError("Building heights are supported only at intermediate points.")
    if weather is not None and not isinstance(weather, WeatherConditions):
        raise ValueError("weather must be a WeatherConditions model.")
    if radio is not None and not isinstance(radio, RadioLinkParameters):
        raise ValueError("radio must be a RadioLinkParameters model.")

    phi1, phi2 = math.radians(tx_lat), math.radians(rx_lat)
    dphi = math.radians(rx_lat - tx_lat)
    dlambda = math.radians(rx_lon - tx_lon)
    haversine = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    haversine = min(1.0, max(0.0, haversine))
    distance_km = (
        2.0
        * EARTH_RADIUS_KM
        * math.atan2(math.sqrt(haversine), math.sqrt(1.0 - haversine))
    )

    horizon_tx_km = 3.57 * math.sqrt(EFFECTIVE_K_FACTOR * max(tx_height_m, 0.1))
    horizon_rx_km = 3.57 * math.sqrt(EFFECTIVE_K_FACTOR * max(rx_height_m, 0.1))
    max_los_range_km = horizon_tx_km + horizon_rx_km

    effective_radius_m = EARTH_RADIUS_KM * 1000.0 * EFFECTIVE_K_FACTOR
    midpoint_bulge_m = (distance_km * 1000.0) ** 2 / (8.0 * effective_radius_m)
    fresnel_radius_m = 17.32 * math.sqrt(
        max(distance_km, 0.001) / (4.0 * freq_ghz)
    )
    fresnel_clearance_m = 0.6 * fresnel_radius_m
    required_average_height_m = midpoint_bulge_m + fresnel_clearance_m
    average_antenna_height_m = (tx_height_m + rx_height_m) / 2.0
    path_loss_db = (
        20.0 * math.log10(max(distance_km, 0.001))
        + 20.0 * math.log10(freq_ghz)
        + 92.45
    )
    profile_min_clearance_m: float | None = None
    profile_min_fresnel_margin_m: float | None = None
    dominant_obstacle_type = "NONE"
    dominant_obstacle_v: float | None = None
    diffraction_loss_db = 0.0
    tx_ground_m = path_profile[0].terrain_elevation_m if path_profile else 0.0
    rx_ground_m = path_profile[-1].terrain_elevation_m if path_profile else 0.0
    if path_profile is not None:
        if distance_km == 0:
            raise ValueError("Path profiles require distinct transmitter and receiver coordinates.")
        distance_m = distance_km * 1000.0
        wavelength_m = 299_792_458.0 / (freq_ghz * 1_000_000_000.0)
        tx_absolute_height_m = tx_ground_m + tx_height_m
        rx_absolute_height_m = rx_ground_m + rx_height_m
        profile_clearances: list[float] = []
        profile_fresnel_margins: list[float] = []
        obstacle_candidates: list[tuple[float, str]] = []
        for point in path_profile[1:-1]:
            d1 = distance_m * point.distance_fraction
            d2 = distance_m - d1
            curvature_bulge_m = d1 * d2 / (2.0 * effective_radius_m)
            obstacle_height_m = (
                point.terrain_elevation_m
                + point.building_height_m
                + curvature_bulge_m
            )
            path_height_m = (
                tx_absolute_height_m
                + (rx_absolute_height_m - tx_absolute_height_m)
                * point.distance_fraction
            )
            clearance_m = path_height_m - obstacle_height_m
            fresnel_radius_m = math.sqrt(wavelength_m * d1 * d2 / distance_m)
            profile_clearances.append(clearance_m)
            profile_fresnel_margins.append(clearance_m - 0.6 * fresnel_radius_m)
            diffraction_v = -clearance_m * math.sqrt(
                2.0 * distance_m / (wavelength_m * d1 * d2)
            )
            obstacle_type = (
                "BUILDING" if point.building_height_m > 0 else "TERRAIN"
            )
            obstacle_candidates.append((diffraction_v, obstacle_type))
        if profile_clearances:
            profile_min_clearance_m = min(profile_clearances)
            profile_min_fresnel_margin_m = min(profile_fresnel_margins)
            dominant_obstacle_v, candidate_type = max(obstacle_candidates)
            if dominant_obstacle_v > -0.78:
                dominant_obstacle_type = candidate_type
                diffraction_loss_db = _knife_edge_loss_db(dominant_obstacle_v)

    rain_loss_db = 0.0
    other_weather_loss_db = 0.0
    if weather is not None:
        if weather.rain_path_km > distance_km:
            raise ValueError("Rain path length cannot exceed the radio path distance.")
        rain_specific_loss_db_km = _rain_specific_attenuation_db_km(
            freq_ghz, weather.rain_rate_mm_h, weather.polarization
        )
        rain_loss_db = rain_specific_loss_db_km * weather.rain_path_km
        other_weather_loss_db = weather.other_weather_loss_db
    weather_loss_db = rain_loss_db + other_weather_loss_db
    total_path_loss_db = path_loss_db + diffraction_loss_db + weather_loss_db

    tx_antenna_gain_dbi: float | None = None
    rx_antenna_gain_dbi: float | None = None
    received_signal_strength_dbm: float | None = None
    link_margin_db: float | None = None
    link_status = "NOT_ESTIMATED"
    if radio is not None:
        tx_bearing = _bearing_degrees(tx_lat, tx_lon, rx_lat, rx_lon)
        rx_bearing = _bearing_degrees(rx_lat, rx_lon, tx_lat, tx_lon)
        distance_for_elevation_m = max(distance_km * 1000.0, 0.001)
        curvature_drop_m = (
            distance_for_elevation_m**2 / (2.0 * effective_radius_m)
        )
        tx_target_elevation_deg = math.degrees(
            math.atan2(
                rx_ground_m + rx_height_m
                - tx_ground_m
                - tx_height_m
                - curvature_drop_m,
                distance_for_elevation_m,
            )
        )
        rx_target_elevation_deg = math.degrees(
            math.atan2(
                tx_ground_m + tx_height_m
                - rx_ground_m
                - rx_height_m
                - curvature_drop_m,
                distance_for_elevation_m,
            )
        )
        tx_antenna_gain_dbi = _antenna_gain_toward(
            radio.tx_antenna, tx_bearing, tx_target_elevation_deg
        )
        rx_antenna_gain_dbi = _antenna_gain_toward(
            radio.rx_antenna, rx_bearing, rx_target_elevation_deg
        )
        received_signal_strength_dbm = (
            radio.tx_power_dbm
            - radio.tx_antenna.feedline_loss_db
            + tx_antenna_gain_dbi
            + rx_antenna_gain_dbi
            - radio.rx_antenna.feedline_loss_db
            - total_path_loss_db
        )
        link_margin_db = (
            received_signal_strength_dbm - radio.rx_sensitivity_dbm
        )
        link_status = (
            "POSITIVE_MARGIN_ESTIMATE"
            if link_margin_db >= 0
            else "NEGATIVE_MARGIN_ESTIMATE"
        )

    estimated_clear = (
        distance_km <= max_los_range_km
        and (
            profile_min_fresnel_margin_m >= 0
            if profile_min_fresnel_margin_m is not None
            else average_antenna_height_m >= required_average_height_m
        )
    )

    model_warnings = [
        "Prediction only; no live terrain, building, or weather data is fetched.",
        "Multipath, vegetation, clutter, interference, polarization mismatch, and receiver noise are not modeled.",
    ]
    if path_profile is None:
        model_warnings.append("No terrain/building profile supplied; obstruction loss is zero.")
    else:
        model_warnings.append(
            "Profile diffraction uses only the dominant single knife edge; profile samples are user supplied and unverified."
        )
    if weather is None:
        model_warnings.append("No weather supplied; weather attenuation is zero.")
    else:
        model_warnings.append(
            "Rain attenuation uses ITU-R P.838-3 with the supplied uniform rain rate and path length; other weather loss is user supplied."
        )
    if radio is None:
        model_warnings.append(
            "No equipment parameters supplied; received signal strength and link margin are omitted."
        )
    else:
        model_warnings.append(
            "Antenna gain uses a clipped quadratic beamwidth approximation, not measured antenna patterns."
        )

    return {
        "distance_km": round(distance_km, 3),
        "max_radio_horizon_km": round(max_los_range_km, 2),
        "earth_bulge_m": round(midpoint_bulge_m, 2),
        "fresnel_60pct_clearance_m": round(fresnel_clearance_m, 2),
        "required_mast_height_m": round(required_average_height_m, 2),
        "average_antenna_height_m": round(average_antenna_height_m, 2),
        "antenna_height_margin_m": round(
            average_antenna_height_m - required_average_height_m, 2
        ),
        "free_space_path_loss_db": round(path_loss_db, 2),
        "profile_min_clearance_m": (
            round(profile_min_clearance_m, 2)
            if profile_min_clearance_m is not None
            else None
        ),
        "profile_min_60pct_fresnel_margin_m": (
            round(profile_min_fresnel_margin_m, 2)
            if profile_min_fresnel_margin_m is not None
            else None
        ),
        "dominant_obstacle_type": dominant_obstacle_type,
        "dominant_obstacle_v": (
            round(dominant_obstacle_v, 3)
            if dominant_obstacle_v is not None
            else None
        ),
        "knife_edge_diffraction_loss_db": round(diffraction_loss_db, 2),
        "rain_attenuation_db": round(rain_loss_db, 2),
        "other_weather_loss_db": round(other_weather_loss_db, 2),
        "weather_attenuation_db": round(weather_loss_db, 2),
        "total_path_loss_db": round(total_path_loss_db, 2),
        "tx_antenna_gain_dbi": (
            round(tx_antenna_gain_dbi, 2)
            if tx_antenna_gain_dbi is not None
            else None
        ),
        "rx_antenna_gain_dbi": (
            round(rx_antenna_gain_dbi, 2)
            if rx_antenna_gain_dbi is not None
            else None
        ),
        "received_signal_strength_dbm": (
            round(received_signal_strength_dbm, 2)
            if received_signal_strength_dbm is not None
            else None
        ),
        "rx_sensitivity_dbm": (
            radio.rx_sensitivity_dbm if radio is not None else None
        ),
        "link_margin_db": round(link_margin_db, 2) if link_margin_db is not None else None,
        "link_status": link_status,
        "frequency_ghz": float(freq_ghz),
        "los_status": (
            "CLEAR_LOS_ESTIMATE"
            if estimated_clear
            else "OBSTRUCTED_OR_OUT_OF_RANGE"
        ),
        "model_warnings": model_warnings,
    }


def _validate_dispatch_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Aether dispatch URL must be an HTTP(S) URL without credentials.")

    try:
        is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        is_loopback = parsed.hostname.lower() == "localhost"
    if not is_loopback and parsed.scheme != "https":
        raise ValueError("HTTPS is required for non-loopback Aether dispatch URLs.")


def _post_telemetry(
    url: str, token: str, envelope: Mapping[str, Any], timeout_seconds: float
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(envelope, separators=(",", ":")).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **({"X-Aether-Token": token} if token else {}),
        },
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(_RejectRedirects())
        with opener.open(request, timeout=timeout_seconds) as response:
            body = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(body) > _MAX_RESPONSE_BYTES:
                raise RuntimeError("Aether dispatch response exceeded the size limit.")
    except urllib.error.HTTPError as error:
        detail = error.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Aether dispatch returned HTTP {error.code}: {detail}"
        ) from error

    try:
        result = json.loads(body)
    except json.JSONDecodeError as error:
        raise RuntimeError("Aether dispatch returned invalid JSON.") from error
    if not isinstance(result, dict):
        raise RuntimeError("Aether dispatch returned a non-object JSON response.")
    return result


async def publish_telemetry_to_aether(
    event_name: str,
    payload: Mapping[str, Any],
    *,
    dispatch_url: str | None = None,
    timeout_seconds: float = 3.0,
) -> dict[str, Any]:
    """Publish a validated event through the unified MATRIX dispatch path."""
    if not isinstance(event_name, str) or not _EVENT_PATTERN.fullmatch(event_name):
        raise ValueError("event_name must be a canonical uppercase event identifier.")
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping.")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("timeout_seconds must be a finite positive number.")

    url = (
        dispatch_url
        if dispatch_url is not None
        else os.environ.get("AETHER_DISPATCH_URL", AETHER_DISPATCH_URL)
    )
    token = os.environ.get("AETHER_API_TOKEN", "")
    _validate_dispatch_url(url)
    envelope = {
        "protocol_version": "1.0.0",
        "source_lang": "python",
        "node": "MATRIX",
        "event": event_name,
        "timestamp": time.time(),
        "payload": dict(payload),
    }
    return await asyncio.to_thread(
        _post_telemetry, url, token, envelope, timeout_seconds
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tx-lat", type=float, default=34.0975)
    parser.add_argument("--tx-lon", type=float, default=-117.6484)
    parser.add_argument("--tx-height-m", type=float, default=25.0)
    parser.add_argument("--rx-lat", type=float, default=34.1425)
    parser.add_argument("--rx-lon", type=float, default=-117.6510)
    parser.add_argument("--rx-height-m", type=float, default=18.0)
    parser.add_argument("--freq-ghz", type=float, default=5.8)
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = calculate_los_link_budget(
            tx_lat=args.tx_lat,
            tx_lon=args.tx_lon,
            tx_height_m=args.tx_height_m,
            rx_lat=args.rx_lat,
            rx_lon=args.rx_lon,
            rx_height_m=args.rx_height_m,
            freq_ghz=args.freq_ghz,
        )
    except ValueError as error:
        parser.error(str(error))

    print(json.dumps(report, indent=2))
    if args.no_publish:
        return 0

    try:
        result = asyncio.run(
            publish_telemetry_to_aether("LOS_LINK_BUDGET_CALCULATED", report)
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Telemetry publish failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
