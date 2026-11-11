from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from aether_engine import astronomy_engine


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, 0), (0, 181), (float("nan"), 0), (0, float("inf")), (True, 0)],
)
def test_engine_rejects_invalid_coordinates(latitude, longitude):
    with pytest.raises(ValueError):
        astronomy_engine.FactualAstronomyEngine(latitude, longitude)


def test_skyfield_downloads_are_cached_outside_the_project(monkeypatch, tmp_path):
    monkeypatch.setattr(astronomy_engine.sys, "platform", "darwin")
    monkeypatch.setattr(astronomy_engine.Path, "home", lambda: tmp_path)

    assert astronomy_engine._skyfield_cache_directory() == (
        tmp_path / "Library" / "Caches" / "AetherEngine" / "skyfield"
    )


def test_engine_filters_catalog_and_computes_visible_stars(monkeypatch):
    source = pd.DataFrame(
        {
            "magnitude": [1.0, 2.0, 5.0],
            "ra_hours": [6.0, 12.0, 18.0],
            "dec_degrees": [10.0, -20.0, 30.0],
        },
        index=pd.Index([100, 200, 300], name="hip"),
    )
    converted_times = []

    class FakeAngle:
        def __init__(self, degrees):
            self.degrees = np.array(degrees)

    class FakeObservation:
        def apparent(self):
            return self

        def altaz(self):
            return FakeAngle([20.0, -5.0]), FakeAngle([180.0, 90.0]), None

    class FakeObserver:
        def at(self, instant):
            return self

        def observe(self, _stars):
            return FakeObservation()

    class FakeEarth:
        def __add__(self, _location):
            return FakeObserver()

    class FakeTimescale:
        def from_datetime(self, instant):
            converted_times.append(instant)
            return instant

    class FakeLoader:
        def timescale(self, **_kwargs):
            return FakeTimescale()

        def __call__(self, _filename):
            return FakeEphemeris()

        def open(self, _url):
            return FakeCatalogFile(source)

    class FakeCatalogFile:
        def __init__(self, dataframe):
            self.dataframe = dataframe

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class FakeEphemeris:
        def __getitem__(self, _name):
            return FakeEarth()

    monkeypatch.setattr(astronomy_engine, "load", FakeLoader())
    monkeypatch.setattr(astronomy_engine, "wgs84", FakeWgs84())
    monkeypatch.setattr(
        astronomy_engine.hipparcos,
        "load_dataframe",
        lambda catalog_file: catalog_file.dataframe,
    )
    monkeypatch.setattr(
        astronomy_engine.Star,
        "from_dataframe",
        lambda dataframe: dataframe.index.tolist(),
    )

    engine = astronomy_engine.FactualAstronomyEngine()
    visible = engine.compute_local_sky(datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert [star["hip_id"] for star in visible] == [100]
    assert visible[0]["alt_deg"] == 20.0
    assert visible[0]["az_deg"] == 180.0
    assert converted_times == [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    assert engine.get_bright_visible_stars(2.0).index.tolist() == [100, 200]

class FakeWgs84:
    @staticmethod
    def latlon(*_args):
        return object()
