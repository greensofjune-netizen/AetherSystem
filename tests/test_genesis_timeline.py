import pytest

from aether_engine.genesis_timeline import (
    EPOCHS,
    LIFECYCLE,
    simulate_display_position,
    snapshot,
)


def test_genesis_snapshot_preserves_five_stage_lifecycle_and_boundaries():
    data = snapshot()

    assert [entry["stage"] for entry in data["lifecycle"]] == [1, 2, 3, 4, 5]
    assert all(
        entry["status"] != "PENDING_INDEPENDENT_VALIDATION"
        for entry in LIFECYCLE[:4]
    )
    assert LIFECYCLE[4]["status"] == "PENDING_INDEPENDENT_VALIDATION"
    assert data["scope"] == "EDUCATIONAL_TIMELINE_NOT_LIVE_TELEMETRY"
    assert len(EPOCHS) == 6
    assert all(epoch["source_url"].startswith("https://") for epoch in EPOCHS)
    assert any("MODEL_DEPENDENT" == epoch["claim_status"] for epoch in EPOCHS)
    assert "not a physical law" in " ".join(data["limitations"]).lower()
    assert "independent" in " ".join(data["limitations"]).lower()


def test_genesis_simulator_is_bounded_monotonic_and_educational_only():
    samples = [simulate_display_position(index / 20) for index in range(21)]

    assert samples[0]["position"] == 0.0
    assert samples[-1]["position"] == 1.0
    assert all(sample["not_a_prediction"] is True for sample in samples)
    assert all(
        sample["scope"] == "EDUCATIONAL_LOG_TIME_DISPLAY_ONLY" for sample in samples
    )
    assert all(
        left["display_age_seconds"] < right["display_age_seconds"]
        for left, right in zip(samples, samples[1:])
    )


@pytest.mark.parametrize("position", [-0.01, 1.01, True, "0.5", float("nan")])
def test_genesis_simulator_rejects_out_of_range_or_non_numeric_positions(position):
    with pytest.raises(ValueError, match="position"):
        simulate_display_position(position)
