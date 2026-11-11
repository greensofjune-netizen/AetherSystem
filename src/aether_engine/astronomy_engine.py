"""Local sky positions from the JPL DE421 ephemeris and Hipparcos catalog."""

from __future__ import annotations

import logging
import math
import os
import sys
from datetime import datetime, timezone
from functools import lru_cache
from numbers import Integral
from pathlib import Path
from threading import Lock
from typing import Any

import pandas as pd
from skyfield.api import Loader, Star, wgs84
from skyfield.data import hipparcos

LOGGER = logging.getLogger(__name__)
_REQUIRED_CATALOG_COLUMNS = {"magnitude", "ra_hours", "dec_degrees"}
load: Any = None
_loader_lock = Lock()


def _skyfield_cache_directory() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "AetherEngine" / "skyfield"
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "AetherEngine" / "skyfield"
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")).expanduser()
    return root / "aether-engine" / "skyfield"


def _get_loader() -> Any:
    global load
    if load is not None:
        return load
    with _loader_lock:
        if load is None:
            cache_directory = _skyfield_cache_directory()
            cache_directory.mkdir(parents=True, exist_ok=True)
            load = Loader(str(cache_directory), verbose=False)
    return load


class FactualAstronomyEngine:
    """Calculate visible Hipparcos-star positions for a fixed Earth observer.

    Skyfield caches downloaded data in a per-user cache directory outside the
    project. The JPL ephemeris and Hipparcos catalog are fetched on first use.
    """

    def __init__(self, lat: float = 34.0975, lon: float = -117.6484) -> None:
        self._validate_coordinates(lat, lon)
        self.lat = float(lat)
        self.lon = float(lon)
        self.ts: Any = None
        self.ephemeris: Any = None
        self.earth: Any = None
        self.observer_location: Any = None
        self.star_dataframe: pd.DataFrame | None = None
        self._load_lock = Lock()

    @staticmethod
    def _validate_coordinates(lat: float, lon: float) -> None:
        if (
            isinstance(lat, bool)
            or not isinstance(lat, (int, float))
            or not math.isfinite(lat)
            or not -90 <= lat <= 90
        ):
            raise ValueError("Latitude must be a finite number between -90 and 90.")
        if (
            isinstance(lon, bool)
            or not isinstance(lon, (int, float))
            or not math.isfinite(lon)
            or not -180 <= lon <= 180
        ):
            raise ValueError("Longitude must be a finite number between -180 and 180.")

    def _ensure_loaded(self) -> None:
        if self.star_dataframe is not None:
            return
        with self._load_lock:
            if self.star_dataframe is not None:
                return

            LOGGER.info("Loading Skyfield timescale and DE421 ephemeris.")
            loader = _get_loader()
            timescale = loader.timescale(builtin=True)
            ephemeris = loader("de421.bsp")
            earth = ephemeris["earth"]
            observer_location = earth + wgs84.latlon(self.lat, self.lon)

            LOGGER.info("Loading the Hipparcos star catalog.")
            with loader.open(hipparcos.URL) as catalog_file:
                star_dataframe = hipparcos.load_dataframe(catalog_file)
            missing_columns = _REQUIRED_CATALOG_COLUMNS - set(star_dataframe.columns)
            if missing_columns:
                raise RuntimeError(
                    "Hipparcos catalog is missing required columns: "
                    + ", ".join(sorted(missing_columns))
                )
            star_dataframe = star_dataframe.dropna(
                subset=["magnitude", "ra_hours", "dec_degrees"]
            )

            self.ts = timescale
            self.ephemeris = ephemeris
            self.earth = earth
            self.observer_location = observer_location
            self.star_dataframe = star_dataframe

    def get_bright_visible_stars(
        self, max_magnitude: float = 4.5
    ) -> pd.DataFrame:
        """Return a copy of catalog stars at or brighter than a magnitude limit."""
        if (
            isinstance(max_magnitude, bool)
            or not isinstance(max_magnitude, (int, float))
            or not math.isfinite(max_magnitude)
        ):
            raise ValueError("Maximum magnitude must be a finite number.")
        self._ensure_loaded()
        if self.star_dataframe is None:
            raise RuntimeError("Astronomy catalog failed to initialize.")
        visible_mask = self.star_dataframe["magnitude"] <= max_magnitude
        return self.star_dataframe.loc[visible_mask].copy()

    def compute_local_sky(
        self, time_utc: datetime, max_magnitude: float = 4.0
    ) -> list[dict[str, int | float]]:
        """Return bright stars above the local horizon for a UTC instant.

        A naive datetime is interpreted as UTC for compatibility with callers
        that use ``datetime.utcnow()``; aware datetimes are converted to UTC.
        """
        if not isinstance(time_utc, datetime):
            raise TypeError("Observation time must be a datetime.")
        if (
            isinstance(max_magnitude, bool)
            or not isinstance(max_magnitude, (int, float))
            or not math.isfinite(max_magnitude)
        ):
            raise ValueError("Maximum magnitude must be a finite number.")
        instant = (
            time_utc.replace(tzinfo=timezone.utc)
            if time_utc.tzinfo is None
            else time_utc.astimezone(timezone.utc)
        )
        self._ensure_loaded()
        bright_stars = self.get_bright_visible_stars(max_magnitude=max_magnitude)
        if bright_stars.empty:
            return []

        star_positions = Star.from_dataframe(bright_stars)
        astrometric = self.observer_location.at(self.ts.from_datetime(instant)).observe(
            star_positions
        )
        altitude, azimuth, _ = astrometric.apparent().altaz()
        bright_stars["altitude_deg"] = altitude.degrees
        bright_stars["azimuth_deg"] = azimuth.degrees
        above_horizon = bright_stars.loc[bright_stars["altitude_deg"] > 0]

        results: list[dict[str, int | float]] = []
        for hip_id, row in above_horizon.iterrows():
            if not isinstance(hip_id, Integral):
                raise RuntimeError("Hipparcos catalog contains a non-integer star ID.")
            results.append(
                {
                    "hip_id": int(hip_id),
                    "magnitude": float(row["magnitude"]),
                    "ra_hours": float(row["ra_hours"]),
                    "dec_degrees": float(row["dec_degrees"]),
                    "alt_deg": round(float(row["altitude_deg"]), 2),
                    "az_deg": round(float(row["azimuth_deg"]), 2),
                }
            )
        return sorted(results, key=lambda star: star["magnitude"])


@lru_cache(maxsize=32)
def get_default_astronomy_engine() -> FactualAstronomyEngine:
    """Return the process-wide lazily initialized astronomy engine."""
    return FactualAstronomyEngine()


@lru_cache(maxsize=32)
def get_astronomy_engine(lat: float, lon: float) -> FactualAstronomyEngine:
    """Return a cached engine for observer coordinates."""
    return FactualAstronomyEngine(lat, lon)
