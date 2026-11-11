"""Local natal-chart and Pythagorean numerology calculations."""

from __future__ import annotations

import math
import unicodedata
from datetime import date, datetime, time, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import ephem
from pydantic import BaseModel, ConfigDict, Field, field_validator

SIGNS = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)
MASTER_NUMBERS = {11, 22, 33}
PLANETS = (
    ("Sun", ephem.Sun, "☉"),
    ("Moon", ephem.Moon, "☽"),
    ("Mercury", ephem.Mercury, "☿"),
    ("Venus", ephem.Venus, "♀"),
    ("Mars", ephem.Mars, "♂"),
    ("Jupiter", ephem.Jupiter, "♃"),
    ("Saturn", ephem.Saturn, "♄"),
    ("Uranus", ephem.Uranus, "♅"),
    ("Neptune", ephem.Neptune, "♆"),
    ("Pluto", ephem.Pluto, "♇"),
)


class NatalChartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    birth_date: date
    birth_time: time
    fold: Literal[0, 1] = 0
    timezone: str = Field(min_length=1, max_length=80)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)

    @field_validator("name", "timezone")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("This field cannot be blank.")
        return value.strip()


def _reduce_number(value: int) -> int:
    while value > 9 and value not in MASTER_NUMBERS:
        value = sum(int(digit) for digit in str(value))
    return value


def _name_letters(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).upper()
    letters: list[str] = []
    for character in normalized:
        if "A" <= character <= "Z":
            letters.append(character)
        elif character.isalpha() and not unicodedata.combining(character):
            raise ValueError(
                "Use a name written with Latin letters for Pythagorean numerology."
            )
    if not letters:
        raise ValueError("Enter a name containing Latin letters.")
    return "".join(letters)


def _letter_value(letter: str) -> int:
    return (ord(letter) - ord("A")) % 9 + 1


def _numerology(name: str, birth_date: date) -> dict[str, int | str | list[int]]:
    letters = _name_letters(name)
    month = _reduce_number(birth_date.month)
    day = _reduce_number(birth_date.day)
    year = _reduce_number(birth_date.year)
    life_path = _reduce_number(month + day + year)
    expression = _reduce_number(sum(_letter_value(letter) for letter in letters))
    vowels = sum(
        _letter_value(letter)
        for letter in letters
        if letter in {"A", "E", "I", "O", "U"}
    )
    consonants = sum(
        _letter_value(letter)
        for letter in letters
        if letter not in {"A", "E", "I", "O", "U"}
    )
    return {
        "system": "Pythagorean",
        "master_numbers": sorted(MASTER_NUMBERS),
        "life_path": life_path,
        "birthday": birth_date.day,
        "expression": _reduce_number(expression),
        "soul_urge": _reduce_number(vowels),
        "personality": _reduce_number(consonants),
        "maturity": _reduce_number(life_path + expression),
    }


def _julian_day(instant: datetime) -> float:
    return instant.timestamp() / 86400 + 2440587.5


def _obliquity(julian_day: float) -> float:
    centuries = (julian_day - 2451545.0) / 36525
    arcseconds = (
        84381.448
        - 46.8150 * centuries
        - 0.00059 * centuries**2
        + 0.001813 * centuries**3
    )
    return math.radians(arcseconds / 3600)


def _sign_position(longitude: float) -> tuple[str, float, int]:
    degrees = longitude % 360
    sign_index = int(degrees // 30)
    return SIGNS[sign_index], degrees % 30, sign_index


def _angles(
    instant: datetime, latitude: float, longitude: float, obliquity: float
) -> tuple[float, float]:
    julian_day = _julian_day(instant)
    centuries = (julian_day - 2451545.0) / 36525
    gmst = (
        280.46061837
        + 360.98564736629 * (julian_day - 2451545.0)
        + 0.000387933 * centuries**2
        - centuries**3 / 38710000
    )
    sidereal_degrees = math.radians((gmst + longitude) % 360)
    latitude_radians = math.radians(latitude)

    midheaven = (
        math.degrees(
            math.atan2(
                math.sin(sidereal_degrees),
                math.cos(sidereal_degrees) * math.cos(obliquity),
            )
        )
        % 360
    )

    a = math.cos(latitude_radians) * math.cos(sidereal_degrees)
    b = math.cos(latitude_radians) * math.sin(sidereal_degrees) * math.cos(
        obliquity
    ) + math.sin(latitude_radians) * math.sin(obliquity)
    ascendant = math.degrees(math.atan2(-a, b)) % 360

    def hour_angle(ecliptic_longitude: float) -> float:
        longitude_radians = math.radians(ecliptic_longitude)
        right_ascension = math.atan2(
            math.sin(longitude_radians) * math.cos(obliquity),
            math.cos(longitude_radians),
        )
        return (sidereal_degrees - right_ascension + math.pi) % (2 * math.pi) - math.pi

    if hour_angle(ascendant) > 0:
        ascendant = (ascendant + 180) % 360
    return ascendant, midheaven


def _local_birth_instant(entry: NatalChartRequest) -> datetime:
    if entry.birth_time.tzinfo is not None:
        raise ValueError("Enter a local birth time without a UTC offset.")
    if not 1800 <= entry.birth_date.year <= 2200:
        raise ValueError("Birth dates must be between 1800 and 2200.")
    try:
        zone = ZoneInfo(entry.timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(
            "Enter a valid IANA time zone, such as America/Los_Angeles."
        ) from error

    local_time = datetime.combine(entry.birth_date, entry.birth_time)
    candidates = []
    for fold in (0, 1):
        candidate = local_time.replace(tzinfo=zone, fold=fold)
        if (
            candidate.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
            == local_time
        ):
            candidates.append(candidate)
    if not candidates:
        raise ValueError(
            "That local birth time did not occur because of a daylight-saving change."
        )
    chosen = next(
        (candidate for candidate in candidates if candidate.fold == entry.fold), None
    )
    if chosen is None:
        chosen = candidates[0]
    return chosen.astimezone(timezone.utc)


def calculate_natal_chart(entry: NatalChartRequest) -> dict[str, object]:
    """Calculate a tropical, geocentric chart with whole-sign houses."""
    instant = _local_birth_instant(entry)
    julian_day = _julian_day(instant)
    obliquity = _obliquity(julian_day)
    ascendant, midheaven = _angles(instant, entry.latitude, entry.longitude, obliquity)
    asc_sign, asc_degree, asc_index = _sign_position(ascendant)
    mc_sign, mc_degree, _ = _sign_position(midheaven)
    ephemeris_date = ephem.Date(instant.replace(tzinfo=None))

    positions: list[dict[str, object]] = []
    for name, body_type, glyph in PLANETS:
        body = body_type()
        body.compute(ephemeris_date)
        right_ascension = float(body.ra)
        declination = float(body.dec)
        ecliptic_longitude = (
            math.degrees(
                math.atan2(
                    math.sin(right_ascension) * math.cos(obliquity)
                    + math.tan(declination) * math.sin(obliquity),
                    math.cos(right_ascension),
                )
            )
            % 360
        )
        sign, degree, sign_index = _sign_position(ecliptic_longitude)
        positions.append(
            {
                "planet": name,
                "glyph": glyph,
                "sign": sign,
                "degree": round(degree, 2),
                "longitude": round(ecliptic_longitude, 2),
                "house": (sign_index - asc_index) % 12 + 1,
            }
        )

    houses = [
        {"house": number, "sign": SIGNS[(asc_index + number - 1) % 12]}
        for number in range(1, 13)
    ]
    return {
        "astrology": {
            "zodiac": "Tropical",
            "house_system": "Whole Sign",
            "ascendant": {
                "sign": asc_sign,
                "degree": round(asc_degree, 2),
                "longitude": round(ascendant, 2),
            },
            "midheaven": {
                "sign": mc_sign,
                "degree": round(mc_degree, 2),
                "longitude": round(midheaven, 2),
            },
            "planets": positions,
            "houses": houses,
        },
        "numerology": _numerology(entry.name, entry.birth_date),
    }
