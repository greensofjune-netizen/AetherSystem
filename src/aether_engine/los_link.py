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
from typing import Any

AETHER_DISPATCH_URL = "http://127.0.0.1:8000/api/v1/unified/dispatch"
EARTH_RADIUS_KM = 6371.0
EFFECTIVE_K_FACTOR = 4.0 / 3.0
_EVENT_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_MAX_RESPONSE_BYTES = 64 * 1024


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
) -> dict[str, float | str]:
    """Estimate a point-to-point radio path using a 4/3-Earth model.

    This midpoint estimate does not include terrain profiles, buildings,
    vegetation, weather, antenna patterns, or measured signal strength.
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
    estimated_clear = (
        distance_km <= max_los_range_km
        and average_antenna_height_m >= required_average_height_m
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
        "frequency_ghz": float(freq_ghz),
        "los_status": (
            "CLEAR_LOS_ESTIMATE"
            if estimated_clear
            else "OBSTRUCTED_OR_OUT_OF_RANGE"
        ),
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
