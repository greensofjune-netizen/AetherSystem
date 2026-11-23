import pytest

from aether_engine.information_transport import (
    MAX_PAYLOAD_BYTES,
    load_transport_principles,
    simulate_transport,
)
from aether_engine.los_link import calculate_los_link_budget


def test_transport_round_trip_is_bounded_and_never_transmits():
    result = simulate_transport(
        {"message": "hello", "sequence": 2},
        bit_error_rate=0,
        seed=7,
        chunk_bytes=4,
    )

    assert result["scope"] == "EDUCATIONAL_PACKET_AND_BPSK_CHANNEL_SIMULATION"
    assert result["transmission_performed"] is False
    assert result["decoded_payload_matches"] is True
    assert result["integrity_valid"] is True
    assert result["bit_errors_modeled"] == 0
    assert result["chunk_count"] > 1
    assert result["limitations"]


def test_transport_detects_modeled_corruption():
    result = simulate_transport(
        {"message": "hello"},
        bit_error_rate=0.5,
        seed=12,
    )

    assert result["bit_errors_modeled"] > 0
    assert result["integrity_valid"] is False
    assert result["decoded_payload_matches"] is False
    assert result["source_sha256"] != result["received_sha256"]


@pytest.mark.parametrize("rate", [-0.01, 1.01, True, "0.1"])
def test_transport_rejects_invalid_error_rates(rate):
    with pytest.raises(ValueError, match="Bit error rate"):
        simulate_transport({"ok": True}, bit_error_rate=rate)


def test_transport_rejects_oversized_or_unserializable_data():
    with pytest.raises(ValueError, match="1-65536"):
        simulate_transport("x" * MAX_PAYLOAD_BYTES)
    with pytest.raises(ValueError, match="JSON serializable"):
        simulate_transport(object())


def test_los_estimate_exposes_shared_lifecycle_without_transmission():
    result = calculate_los_link_budget(34.0, -117.6, 10, 34.1, -117.5, 10)

    lifecycle = result["information_transport"]
    assert lifecycle["scope"] == "EDUCATIONAL_SHARED_LIFECYCLE"
    assert lifecycle["transmission_performed"] is False
    assert lifecycle["stages"] == load_transport_principles()["stages"]
    assert result["link_status"] == "NOT_ESTIMATED"


def test_transport_principles_forbid_hardware_transmission():
    principles = load_transport_principles()

    assert principles["schema_version"] == 1
    assert "modulation_model" in principles["stages"]
    assert any(
        "No engine may transmit" in principle
        for principle in principles["principles"]
    )
