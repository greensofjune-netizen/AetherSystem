"""Plan arts relay sessions and publish operator-review telemetry."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any

from .los_link import calculate_los_link_budget, publish_telemetry_to_aether

ARTS_MODE_PROFILES = {
    "MUSIC": {
        "description": "Lossless concert or studio audio session",
        "media_type": "audio",
    },
    "ART": {
        "description": "High-resolution gallery or visual-installation session",
        "media_type": "video",
    },
    "THEATRE": {
        "description": "Stage production with operator-reviewed lighting cues",
        "media_type": "audio-video",
    },
}
_CUE_ADDRESS_PATTERN = re.compile(r"/[A-Za-z0-9_/-]{1,127}\Z")
_MATRIX_ARTS_EVENTS = {
    "LOS_LINK_BUDGET_CALCULATED",
    "ARTS_SESSION_PLANNED",
    "ARTS_STAGE_CUE_REQUESTED",
}


def latest_matrix_arts_telemetry(
    database_path: str | Path,
) -> dict[str, Any] | None:
    """Read the latest arts/link event from the shared event database."""
    path = Path(database_path).expanduser()
    if path.is_symlink():
        raise ValueError("Aether database cannot be a symlink.")
    if not path.is_file():
        return None

    try:
        with sqlite3.connect(
            f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5
        ) as connection:
            connection.row_factory = sqlite3.Row
            events = connection.execute(
                "SELECT id, message, created_at FROM events "
                "WHERE topic = ? ORDER BY id DESC LIMIT 500",
                ("unified-dispatch",),
            ).fetchall()
    except sqlite3.Error as error:
        raise RuntimeError(f"Could not read Aether dispatch telemetry: {error}") from error

    for event in events:
        try:
            envelope = json.loads(event["message"])
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Unified dispatch event {event['id']} is invalid JSON."
            ) from error
        if not isinstance(envelope, dict):
            raise RuntimeError(
                f"Unified dispatch event {event['id']} is not a JSON object."
            )
        event_name = envelope.get("event")
        if (
            envelope.get("node") != "MATRIX"
            or not isinstance(event_name, str)
            or event_name not in _MATRIX_ARTS_EVENTS
        ):
            continue
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Unified dispatch event {event['id']} has an invalid payload."
            )
        return {
            "event_id": event["id"],
            "created_at": event["created_at"],
            "event": event_name,
            "payload": payload,
        }
    return None


def prepare_arts_session(
    mode: str,
    title: str,
    *,
    tx_lat: float,
    tx_lon: float,
    tx_height_m: float,
    rx_lat: float,
    rx_lon: float,
    rx_height_m: float,
    freq_ghz: float = 60.0,
) -> dict[str, Any]:
    """Create a session plan with an estimate, without starting media or cues."""
    mode_key = mode.strip().upper()
    if mode_key not in ARTS_MODE_PROFILES:
        raise ValueError("mode must be MUSIC, ART, or THEATRE.")
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError("title must contain 1 to 200 non-whitespace characters.")

    link_budget = calculate_los_link_budget(
        tx_lat=tx_lat,
        tx_lon=tx_lon,
        tx_height_m=tx_height_m,
        rx_lat=rx_lat,
        rx_lon=rx_lon,
        rx_height_m=rx_height_m,
        freq_ghz=freq_ghz,
    )
    return {
        "mode": mode_key,
        "title": title.strip(),
        "profile": dict(ARTS_MODE_PROFILES[mode_key]),
        "link_budget": link_budget,
        "status": "SESSION_PLAN_READY",
        "media_relay_started": False,
        "radio_model_limitations": (
            "Geometric estimate only; excludes terrain, weather, and 60 GHz "
            "atmospheric attenuation."
        ),
    }


async def publish_arts_session(plan: dict[str, Any]) -> dict[str, Any]:
    """Publish a planned arts session as MATRIX telemetry."""
    if plan.get("status") != "SESSION_PLAN_READY" or plan.get(
        "media_relay_started"
    ) is not False:
        raise ValueError("Only a non-started arts session plan can be published.")
    return await publish_telemetry_to_aether("ARTS_SESSION_PLANNED", plan)


async def request_stage_cue(
    cue_address: str, cue_value: float | str
) -> dict[str, Any]:
    """Publish a stage-cue request for human review; no lighting packet is sent."""
    if (
        not isinstance(cue_address, str)
        or not _CUE_ADDRESS_PATTERN.fullmatch(cue_address)
        or ".." in cue_address
    ):
        raise ValueError("cue_address must be a bounded absolute OSC-style path.")
    if isinstance(cue_value, bool) or not isinstance(cue_value, (int, float, str)):
        raise ValueError("cue_value must be a finite number or short string.")
    if isinstance(cue_value, (int, float)) and not math.isfinite(cue_value):
        raise ValueError("numeric cue_value must be finite.")
    if isinstance(cue_value, str) and (
        not cue_value.strip() or len(cue_value) > 128
    ):
        raise ValueError("string cue_value must contain 1 to 128 characters.")

    payload = {
        "cue": cue_address,
        "value": cue_value,
        "status": "REQUIRES_OPERATOR_APPROVAL",
        "actuated": False,
    }
    return await publish_telemetry_to_aether("ARTS_STAGE_CUE_REQUESTED", payload)
