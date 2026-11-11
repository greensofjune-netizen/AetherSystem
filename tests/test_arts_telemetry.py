import asyncio

import pytest

from aether_engine import arts_telemetry


def _session_plan(mode="THEATRE"):
    return arts_telemetry.prepare_arts_session(
        mode,
        "Opening night",
        tx_lat=34.0975,
        tx_lon=-117.6484,
        tx_height_m=20.0,
        rx_lat=34.1012,
        rx_lon=-117.6420,
        rx_height_m=15.0,
    )


@pytest.mark.parametrize(
    ("mode", "media_type"),
    [("MUSIC", "audio"), ("ART", "video"), ("THEATRE", "audio-video")],
)
def test_session_plans_are_matrix_ready_but_do_not_start_a_relay(
    mode, media_type
):
    plan = _session_plan(mode.lower())

    assert plan["mode"] == mode
    assert plan["profile"]["media_type"] == media_type
    assert plan["status"] == "SESSION_PLAN_READY"
    assert plan["media_relay_started"] is False
    assert plan["link_budget"]["frequency_ghz"] == 60.0
    assert "atmospheric attenuation" in plan["radio_model_limitations"]


def test_session_plan_rejects_unknown_mode_and_invalid_title():
    with pytest.raises(ValueError, match="MUSIC, ART, or THEATRE"):
        _session_plan("NEWS")

    with pytest.raises(ValueError, match="title"):
        arts_telemetry.prepare_arts_session(
            "MUSIC",
            "  ",
            tx_lat=34.0,
            tx_lon=-117.0,
            tx_height_m=20.0,
            rx_lat=34.1,
            rx_lon=-117.1,
            rx_height_m=15.0,
        )


def test_session_plan_publishes_to_matrix_node(monkeypatch):
    calls = []

    async def publish(event_name, payload):
        calls.append((event_name, payload))
        return {"status": "ACCEPTED"}

    monkeypatch.setattr(arts_telemetry, "publish_telemetry_to_aether", publish)
    plan = _session_plan()
    result = asyncio.run(arts_telemetry.publish_arts_session(plan))

    assert result == {"status": "ACCEPTED"}
    assert calls == [("ARTS_SESSION_PLANNED", plan)]


def test_session_publisher_rejects_started_or_invalid_plans(monkeypatch):
    async def publish(*_args):
        return {}

    monkeypatch.setattr(arts_telemetry, "publish_telemetry_to_aether", publish)
    plan = _session_plan()
    plan["media_relay_started"] = True

    with pytest.raises(ValueError, match="non-started"):
        asyncio.run(arts_telemetry.publish_arts_session(plan))


def test_stage_cue_is_published_for_review_without_actuation(monkeypatch):
    calls = []

    async def publish(event_name, payload):
        calls.append((event_name, payload))
        return {"status": "ACCEPTED"}

    monkeypatch.setattr(arts_telemetry, "publish_telemetry_to_aether", publish)
    result = asyncio.run(
        arts_telemetry.request_stage_cue("/theatre/act1/spotlight", "WARM_AMBER_85")
    )

    assert result == {"status": "ACCEPTED"}
    assert calls == [
        (
            "ARTS_STAGE_CUE_REQUESTED",
            {
                "cue": "/theatre/act1/spotlight",
                "value": "WARM_AMBER_85",
                "status": "REQUIRES_OPERATOR_APPROVAL",
                "actuated": False,
            },
        )
    ]


@pytest.mark.parametrize(
    ("cue_address", "cue_value"),
    [
        ("not-an-absolute-path", 1),
        ("/theatre/../override", 1),
        ("/theatre/spotlight;run", 1),
        ("/theatre/spotlight", float("inf")),
        ("/theatre/spotlight", True),
        ("/theatre/spotlight", ""),
        ("/theatre/spotlight", "x" * 129),
    ],
)
def test_stage_cue_request_rejects_invalid_values(cue_address, cue_value):
    with pytest.raises(ValueError):
        asyncio.run(arts_telemetry.request_stage_cue(cue_address, cue_value))
