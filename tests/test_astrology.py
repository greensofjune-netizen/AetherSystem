from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest

from aether_engine import astrology, galileo, server


def chart_request(**updates: object) -> astrology.NatalChartRequest:
    values: dict[str, object] = {
        "name": "John Doe",
        "birth_date": "1990-01-01",
        "birth_time": "12:00",
        "timezone": "Etc/UTC",
        "latitude": 37.7749,
        "longitude": -122.4194,
    }
    values.update(updates)
    return astrology.NatalChartRequest.model_validate(values)


def test_chart_returns_tropical_positions_whole_sign_houses_and_core_numbers():
    chart = astrology.calculate_natal_chart(chart_request())
    placements = chart["astrology"]

    assert placements["zodiac"] == "Tropical"
    assert placements["house_system"] == "Whole Sign"
    assert placements["ascendant"]["sign"] in astrology.SIGNS
    assert placements["midheaven"]["sign"] in astrology.SIGNS
    assert len(placements["planets"]) == 10
    assert len(placements["houses"]) == 12
    assert {planet["house"] for planet in placements["planets"]} <= set(range(1, 13))
    assert placements["planets"][0]["sign"] == "Capricorn"
    assert placements["houses"][0]["sign"] == placements["ascendant"]["sign"]
    assert chart["numerology"] == {
        "system": "Pythagorean",
        "master_numbers": [11, 22, 33],
        "life_path": 3,
        "birthday": 1,
        "expression": 8,
        "soul_urge": 8,
        "personality": 9,
        "maturity": 11,
    }
    assert "John Doe" not in repr(chart)


@pytest.mark.parametrize(
    ("birth_date", "birth_time", "message"),
    [
        ("2024-03-10", "02:30", "did not occur"),
    ],
)
def test_chart_rejects_nonexistent_local_times(
    birth_date: str, birth_time: str, message: str
):
    entry = chart_request(
        birth_date=birth_date,
        birth_time=birth_time,
        timezone="America/New_York",
    )
    with pytest.raises(ValueError, match=message):
        astrology.calculate_natal_chart(entry)


def test_chart_uses_selected_occurrence_of_repeated_local_time():
    first = astrology.calculate_natal_chart(
        chart_request(
            birth_date="2024-11-03",
            birth_time="01:30",
            timezone="America/New_York",
            fold=0,
        )
    )
    second = astrology.calculate_natal_chart(
        chart_request(
            birth_date="2024-11-03",
            birth_time="01:30",
            timezone="America/New_York",
            fold=1,
        )
    )

    assert (
        first["astrology"]["ascendant"]["longitude"]
        != second["astrology"]["ascendant"]["longitude"]
    )


def test_chart_rejects_invalid_time_zone_and_non_latin_numerology_names():
    with pytest.raises(ValueError, match="valid IANA time zone"):
        astrology.calculate_natal_chart(chart_request(timezone="Not/A_Zone"))
    with pytest.raises(ValueError, match="Latin letters"):
        astrology.calculate_natal_chart(chart_request(name="東京"))


def test_numerology_preserves_master_numbers():
    numbers = astrology._numerology("A", date(1989, 1, 1))
    birthday = astrology._numerology("A", date(2000, 2, 29))

    assert numbers["life_path"] == 11
    assert numbers["birthday"] == 1
    assert birthday["birthday"] == 29


def test_chart_endpoint_is_available_in_galileo_and_aether_api(tmp_path, monkeypatch):
    monkeypatch.setenv("AETHER_DATABASE_PATH", str(tmp_path / "historian.sqlite3"))
    payload = {
        "name": "John Doe",
        "birth_date": "1990-01-01",
        "birth_time": "12:00",
        "timezone": "Etc/UTC",
        "latitude": 37.7749,
        "longitude": -122.4194,
    }
    app = galileo.create_app(tmp_path, token="test-session")

    async def check_galileo() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
            base_url="http://127.0.0.1",
        ) as client:
            await client.get("/?token=test-session")
            response = await client.post("/api/astrology/chart", json=payload)
            assert response.status_code == 200, response.text
            assert response.headers["cache-control"] == "no-store"
            assert response.json()["numerology"]["expression"] == 8
            assert app.state.store.list() == []

    asyncio.run(check_galileo())

    response = server.app
    request_result = asyncio.run(_post_main_api(response, payload))
    assert request_result.status_code == 200, request_result.text
    assert request_result.json()["astrology"]["house_system"] == "Whole Sign"
    assert server.CoPilotHistorian(server.get_store()).history() == []


async def _post_main_api(app, payload: dict[str, object]) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
        base_url="http://127.0.0.1",
    ) as client:
        return await client.post("/api/v1/astrology/chart", json=payload)
